"""SCOAP + Cone of Influence algorithmic analysis for hardware trojan detection.

Computes three families of metrics purely from circuit graph topology (O(N+E)):

  SCOAP (Sandia Controllability/Observability Analysis Program)
      CC0 — cost to force a node to logic-0 (higher = harder = more suspicious)
      CC1 — cost to force a node to logic-1 (high CC1 = rare-activation = trojan trigger)
      CO  — cost to observe a node at a primary output (high CO = hidden payload)

  Cone of Influence (CoI)
      Forward CoI — which primary outputs does this node drive?
      Backward CoI — which primary inputs can activate this node?
      Nodes with tiny backward CoI and security-critical forward CoI are classic trojans.

  Subgraph Isolation
      How weakly connected is this node to the rest of the circuit?
      Nearly-isolated subgraphs with few I/O connections are trojan-structure candidates.

All algorithms use integer arithmetic, Kahn's topological sort, and Python arbitrary-
precision integer bitmasks for CoI propagation.  No external dependencies beyond torch.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque

import torch

from backend.netlist_graph_builder.models import CircuitGraph
from backend.netlist_graph_builder.node_encoder import VOCAB_SIZE
from backend.trojan_classifier.models import AlgorithmicResult, NodeAlgorithmicInfo

logger = logging.getLogger(__name__)

# ── Gate type indices (must match DEFAULT_VOCABULARY in node_encoder.py) ────
_INPUT   = 0
_OUTPUT  = 1
_WIRE    = 2
_DFF     = 3
_AND     = 4
_OR      = 5
_NOT     = 6
_NAND    = 7
_NOR     = 8
_XOR     = 9
_XNOR    = 10
_BUF     = 11
_MUX     = 12
_LATCH   = 13
_UNKNOWN = 14

_SEQ_TYPES = frozenset({_DFF, _LATCH})   # treated as pseudo-primary inputs
_IO_TYPES  = frozenset({_INPUT, _OUTPUT})

# Cap for raw SCOAP values — prevents overflow on deep circuits while keeping
# the relative ordering meaningful after normalization.
_INF = 10_000

# Threshold above which a node's algo_suspicion_score counts as "suspicious"
# for the graph-level summary.
_NODE_SUSPICION_THRESHOLD = 0.5


class AlgorithmicAnalyzer:
    """SCOAP + Cone of Influence + subgraph isolation analysis.

    Usage::

        analyzer = AlgorithmicAnalyzer()
        result   = analyzer.analyze(circuit_graph)   # AlgorithmicResult
    """

    def analyze(self, circuit_graph: CircuitGraph) -> AlgorithmicResult:
        """Analyze a circuit graph and return per-node algorithmic metrics.

        Args:
            circuit_graph: CircuitGraph from netlist_graph_builder.

        Returns:
            AlgorithmicResult with per-node SCOAP scores, CoI info,
            isolation scores, and a graph-level suspicion summary.
        """
        data = circuit_graph.graph_data
        if data is None or data.x is None or data.x.shape[0] == 0:
            return AlgorithmicResult()

        num_nodes: int = data.x.shape[0]
        edge_index: torch.Tensor = data.edge_index
        num_edges: int = int(edge_index.shape[1])

        adj_out, adj_in = self._build_adj(edge_index, num_nodes)
        gate_types = self._extract_gate_types(data.x)
        topo_order = self._topological_sort(adj_out, adj_in, gate_types, num_nodes)

        cc0_raw, cc1_raw = self._compute_scoap_cc(
            adj_in, gate_types, topo_order, num_nodes
        )
        co_raw = self._compute_scoap_co(
            adj_out, adj_in, gate_types, cc0_raw, cc1_raw, topo_order, num_nodes
        )

        fwd_mask, bwd_mask = self._compute_coi_bitmasks(
            adj_out, adj_in, gate_types, topo_order, num_nodes
        )

        wcc_sizes = self._compute_wcc_sizes(adj_out, adj_in, num_nodes)

        # Identify I/O nodes for CoI decoding
        input_nodes  = [n for n in range(num_nodes) if gate_types[n] == _INPUT]
        output_nodes = [n for n in range(num_nodes) if gate_types[n] == _OUTPUT]
        n_inputs  = len(input_nodes)
        n_outputs = len(output_nodes)

        # Normalize SCOAP scores to [0, 1]
        scoap_cap = min(max(max(cc1_raw, default=1), max(co_raw, default=1), 1),
                        10 * num_nodes)
        cc0_norm = self._normalize(cc0_raw, scoap_cap)
        cc1_norm = self._normalize(cc1_raw, scoap_cap)
        co_norm  = self._normalize(co_raw,  scoap_cap)

        max_wcc = max(wcc_sizes) if wcc_sizes else 1

        node_info: dict[str, NodeAlgorithmicInfo] = {}
        algo_scores: list[float] = []

        for n in range(num_nodes):
            gate_name = circuit_graph.node_to_gate.get(n, f"node_{n}")
            gt = gate_types[n]

            # ── Forward CoI: which outputs does node n reach? ──
            coi_out_indices = [i for i in range(n_outputs) if (fwd_mask[n] >> i) & 1]
            coi_out_names   = [
                circuit_graph.node_to_gate.get(output_nodes[i], f"output_{i}")
                for i in coi_out_indices
            ]

            # ── Backward CoI: which inputs can activate node n? ──
            coi_in_indices = [i for i in range(n_inputs) if (bwd_mask[n] >> i) & 1]
            coi_in_names   = [
                circuit_graph.node_to_gate.get(input_nodes[i], f"input_{i}")
                for i in coi_in_indices
            ]

            # ── Subgraph isolation ──
            wcc_fraction  = wcc_sizes[n] / max_wcc
            output_driven = bin(fwd_mask[n]).count("1")
            io_isolation  = 1.0 - (output_driven / max(n_outputs, 1))
            subgraph_iso  = 0.5 * (1.0 - min(wcc_fraction, 1.0)) + 0.5 * io_isolation

            coi_sparsity = io_isolation  # same thing, named for clarity in score formula

            # ── Combined algorithmic suspicion score ──
            # I/O nodes are not trojan suspects by definition.
            #
            # CoI sparsity and subgraph isolation are only informative for small
            # circuits (< 200 nodes).  In large synthesized circuits (AES, RSA, etc.)
            # most internal nodes drive few primary outputs and live in the main WCC,
            # so these metrics saturate and lose discriminative power.  For large
            # circuits, rely solely on SCOAP CC1 + CO.
            if gt in _IO_TYPES:
                algo_score = 0.0
            elif num_nodes < 200:
                algo_score = min(
                    0.35 * cc1_norm[n]
                    + 0.30 * co_norm[n]
                    + 0.20 * subgraph_iso
                    + 0.15 * coi_sparsity,
                    1.0,
                )
            else:
                # Large circuit: SCOAP only (cc1=0.55, co=0.45)
                algo_score = min(0.55 * cc1_norm[n] + 0.45 * co_norm[n], 1.0)

            algo_scores.append(algo_score)

            node_info[gate_name] = NodeAlgorithmicInfo(
                node_index=n,
                gate_name=gate_name,
                scoap_cc0_raw=cc0_raw[n],
                scoap_cc1_raw=cc1_raw[n],
                scoap_co_raw=co_raw[n],
                scoap_cc0=round(cc0_norm[n], 6),
                scoap_cc1=round(cc1_norm[n], 6),
                scoap_co=round(co_norm[n], 6),
                coi_input_count=len(coi_in_names),
                coi_output_count=len(coi_out_names),
                coi_inputs=coi_in_names,
                coi_outputs=coi_out_names,
                subgraph_isolation=round(subgraph_iso, 6),
                algo_suspicion_score=round(algo_score, 6),
            )

        # ── Graph-level summary ──
        non_io_count = sum(1 for n in range(num_nodes) if gate_types[n] not in _IO_TYPES)
        suspicious_count = sum(
            1 for s in algo_scores if s > _NODE_SUSPICION_THRESHOLD
        )
        graph_algo_score = suspicious_count / max(non_io_count, 1)

        # Top-5% lists (excluding I/O nodes)
        inner_cc1 = [cc1_norm[n] for n in range(num_nodes) if gate_types[n] not in _IO_TYPES]
        inner_co  = [co_norm[n]  for n in range(num_nodes) if gate_types[n] not in _IO_TYPES]
        cutoff_cc1 = sorted(inner_cc1, reverse=True)[max(int(0.05 * len(inner_cc1)), 1) - 1] if inner_cc1 else 1.0
        cutoff_co  = sorted(inner_co,  reverse=True)[max(int(0.05 * len(inner_co)),  1) - 1] if inner_co  else 1.0

        high_cc1_nodes = [
            circuit_graph.node_to_gate.get(n, f"node_{n}")
            for n in range(num_nodes)
            if gate_types[n] not in _IO_TYPES and cc1_norm[n] >= cutoff_cc1
        ]
        high_co_nodes = [
            circuit_graph.node_to_gate.get(n, f"node_{n}")
            for n in range(num_nodes)
            if gate_types[n] not in _IO_TYPES and co_norm[n] >= cutoff_co
        ]
        isolated_nodes = [
            circuit_graph.node_to_gate.get(n, f"node_{n}")
            for n in range(num_nodes)
            if gate_types[n] not in _IO_TYPES
            and node_info[circuit_graph.node_to_gate.get(n, f"node_{n}")].subgraph_isolation > 0.7
        ]
        zero_coi_output_nodes = [
            circuit_graph.node_to_gate.get(n, f"node_{n}")
            for n in range(num_nodes)
            if gate_types[n] not in _IO_TYPES and fwd_mask[n] == 0
        ]

        logger.debug(
            "AlgorithmicAnalyzer: %d nodes, %d edges, graph_algo_score=%.4f, "
            "suspicious=%d/%d, zero_coi=%d, isolated=%d",
            num_nodes, num_edges, graph_algo_score,
            suspicious_count, non_io_count,
            len(zero_coi_output_nodes), len(isolated_nodes),
        )

        return AlgorithmicResult(
            node_info=node_info,
            graph_algo_score=round(graph_algo_score, 6),
            high_cc1_nodes=high_cc1_nodes,
            high_co_nodes=high_co_nodes,
            isolated_nodes=isolated_nodes,
            zero_coi_output_nodes=zero_coi_output_nodes,
            analysis_node_count=num_nodes,
            analysis_edge_count=num_edges,
        )

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _build_adj(
        edge_index: torch.Tensor, num_nodes: int
    ) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
        """Build forward and backward adjacency lists from edge_index.  O(E)."""
        adj_out: dict[int, list[int]] = defaultdict(list)
        adj_in:  dict[int, list[int]] = defaultdict(list)
        src_list = edge_index[0].tolist()
        dst_list = edge_index[1].tolist()
        for s, d in zip(src_list, dst_list):
            adj_out[s].append(d)
            adj_in[d].append(s)

        return adj_out, adj_in

    @staticmethod
    def _extract_gate_types(x: torch.Tensor) -> list[int]:
        """Extract gate type index per node from the one-hot feature block.  O(N)."""
        return x[:, :VOCAB_SIZE].argmax(dim=1).tolist()

    @staticmethod
    def _topological_sort(
        adj_out: dict[int, list[int]],
        adj_in:  dict[int, list[int]],
        gate_types: list[int],
        num_nodes: int,
    ) -> list[int]:
        """Kahn's BFS topological sort with sequential boundary cutting.

        DFF/LATCH nodes are treated as pseudo-primary inputs (in-degree forced
        to 0) so that sequential circuits produce a valid topological order for
        the combinational SCOAP propagation pass.  O(N + E).
        """
        in_deg = [0] * num_nodes
        for n in range(num_nodes):
            if gate_types[n] in _SEQ_TYPES:
                in_deg[n] = 0  # sequential node = source
            else:
                in_deg[n] = len(adj_in.get(n, []))

        queue: deque[int] = deque(n for n in range(num_nodes) if in_deg[n] == 0)
        order: list[int] = []

        while queue:
            n = queue.popleft()
            order.append(n)
            for succ in adj_out.get(n, []):
                in_deg[succ] -= 1
                if in_deg[succ] == 0:
                    queue.append(succ)

        # Append any remaining nodes (cycles in combinational logic — unusual but safe)
        if len(order) < num_nodes:
            in_order = set(order)
            for n in range(num_nodes):
                if n not in in_order:
                    order.append(n)

        return order

    @staticmethod
    def _compute_scoap_cc(
        adj_in: dict[int, list[int]],
        gate_types: list[int],
        topo_order: list[int],
        num_nodes: int,
    ) -> tuple[list[int], list[int]]:
        """Compute CC0 and CC1 per node in topological order.  O(N + E).

        Rules follow the standard SCOAP definitions:
            INPUT / SEQ: CC0 = CC1 = 1  (freely assignable)
            NOT:  CC1 = CC0(driver) + 1;  CC0 = CC1(driver) + 1
            AND:  CC1 = sum(CC1) + 1;     CC0 = min(CC0) + 1
            NAND: CC0 = sum(CC1) + 1;     CC1 = min(CC0) + 1
            OR:   CC0 = sum(CC0) + 1;     CC1 = min(CC1) + 1
            NOR:  CC1 = sum(CC0) + 1;     CC0 = min(CC1) + 1
            XOR:  CC1 = min(cc1a+cc0b, cc0a+cc1b) + 1
            XNOR: CC1 = min(cc1a+cc1b, cc0a+cc0b) + 1
            MUX:  see code below
            BUF/WIRE/OUTPUT: inherit from single driver
        """
        cc0 = [_INF] * num_nodes
        cc1 = [_INF] * num_nodes

        for n in topo_order:
            gt    = gate_types[n]
            preds = adj_in.get(n, [])

            if gt == _INPUT or gt in _SEQ_TYPES:
                cc0[n] = 1
                cc1[n] = 1

            elif gt in (_OUTPUT, _WIRE, _BUF):
                if preds:
                    p = preds[0]
                    cc0[n] = min(cc0[p] + 1, _INF)
                    cc1[n] = min(cc1[p] + 1, _INF)
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _NOT:
                if preds:
                    p = preds[0]
                    cc0[n] = min(cc1[p] + 1, _INF)
                    cc1[n] = min(cc0[p] + 1, _INF)
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _AND:
                if preds:
                    cc1[n] = min(sum(cc1[p] for p in preds) + 1, _INF)
                    cc0[n] = min(cc0[p] for p in preds) + 1
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _NAND:
                if preds:
                    cc0[n] = min(sum(cc1[p] for p in preds) + 1, _INF)
                    cc1[n] = min(cc0[p] for p in preds) + 1
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _OR:
                if preds:
                    cc0[n] = min(sum(cc0[p] for p in preds) + 1, _INF)
                    cc1[n] = min(cc1[p] for p in preds) + 1
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _NOR:
                if preds:
                    cc1[n] = min(sum(cc0[p] for p in preds) + 1, _INF)
                    cc0[n] = min(cc1[p] for p in preds) + 1
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _XOR:
                if len(preds) >= 2:
                    a, b = preds[0], preds[1]
                    cc1[n] = min(min(cc1[a] + cc0[b], cc0[a] + cc1[b]) + 1, _INF)
                    cc0[n] = min(min(cc1[a] + cc1[b], cc0[a] + cc0[b]) + 1, _INF)
                elif preds:
                    cc1[n] = min(cc1[preds[0]] + 1, _INF)
                    cc0[n] = min(cc0[preds[0]] + 1, _INF)
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _XNOR:
                if len(preds) >= 2:
                    a, b = preds[0], preds[1]
                    cc1[n] = min(min(cc1[a] + cc1[b], cc0[a] + cc0[b]) + 1, _INF)
                    cc0[n] = min(min(cc1[a] + cc0[b], cc0[a] + cc1[b]) + 1, _INF)
                elif preds:
                    cc1[n] = min(cc1[preds[0]] + 1, _INF)
                    cc0[n] = min(cc0[preds[0]] + 1, _INF)
                else:
                    cc0[n] = cc1[n] = 1

            elif gt == _MUX:
                # Convention: preds[0]=select, preds[1]=data_a, preds[2]=data_b
                # out=a when s=0; out=b when s=1
                if len(preds) >= 3:
                    s, a, b = preds[0], preds[1], preds[2]
                    cc1[n] = min(min(cc1[a] + cc0[s], cc1[b] + cc1[s]) + 1, _INF)
                    cc0[n] = min(min(cc0[a] + cc0[s], cc0[b] + cc1[s]) + 1, _INF)
                elif preds:
                    cc1[n] = min(min(cc1[p] for p in preds) + 1, _INF)
                    cc0[n] = min(min(cc0[p] for p in preds) + 1, _INF)
                else:
                    cc0[n] = cc1[n] = 1

            else:  # _UNKNOWN and unmapped types
                cc0[n] = cc1[n] = 1

        return cc0, cc1

    @staticmethod
    def _compute_scoap_co(
        adj_out: dict[int, list[int]],
        adj_in:  dict[int, list[int]],
        gate_types: list[int],
        cc0: list[int],
        cc1: list[int],
        topo_order: list[int],
        num_nodes: int,
    ) -> list[int]:
        """Compute CO (observability) per node in reverse topological order.  O(N + E).

        CO(n) = minimum cost to observe node n at any primary output.
        Primary outputs have CO = 0.  Propagates backward through gates using
        side-input controllability to compute the enabling cost at each stage.
        """
        co = [_INF] * num_nodes

        # Primary outputs: CO = 0
        for n in range(num_nodes):
            if gate_types[n] == _OUTPUT:
                co[n] = 0

        for n in reversed(topo_order):
            succs = adj_out.get(n, [])
            if not succs:
                continue

            best = _INF
            for s in succs:
                gt_s     = gate_types[s]
                siblings = [p for p in adj_in.get(s, []) if p != n]

                if gt_s in (_OUTPUT, _WIRE, _BUF, _NOT):
                    incr = 1

                elif gt_s in (_AND, _NAND):
                    # Need all siblings = 1 to propagate n through AND/NAND
                    sib_cost = sum(cc1[p] for p in siblings)
                    incr = min(sib_cost + 1, _INF)

                elif gt_s in (_OR, _NOR):
                    # Need all siblings = 0 to propagate n through OR/NOR
                    sib_cost = sum(cc0[p] for p in siblings)
                    incr = min(sib_cost + 1, _INF)

                elif gt_s in (_XOR, _XNOR):
                    # Any sibling value propagates (XOR is transparent)
                    incr = 1

                elif gt_s == _MUX:
                    # Need select in the right state; conservative estimate
                    incr = 2

                else:
                    incr = 1

                candidate = min(co[s] + incr, _INF) if co[s] < _INF else _INF
                best = min(best, candidate)

            co[n] = best

        return co

    @staticmethod
    def _compute_coi_bitmasks(
        adj_out: dict[int, list[int]],
        adj_in:  dict[int, list[int]],
        gate_types: list[int],
        topo_order: list[int],
        num_nodes: int,
    ) -> tuple[list[int], list[int]]:
        """Compute CoI bitmasks using Python arbitrary-precision integers.  O(N + E).

        fwd_mask[n] — bit i set ⟺ output node i is reachable from n
        bwd_mask[n] — bit i set ⟺ input node i can reach n

        Uses Python's native unlimited-precision int for bitwise operations,
        so circuits with > 64 I/O ports are handled correctly without special
        casing.  The constant factor per bitwise OR is ceil(n_ports/64).
        """
        input_nodes  = [n for n in range(num_nodes) if gate_types[n] == _INPUT]
        output_nodes = [n for n in range(num_nodes) if gate_types[n] == _OUTPUT]

        # ── Forward CoI: propagate output-reachability BACKWARD ──
        fwd_mask = [0] * num_nodes
        for bit, out_n in enumerate(output_nodes):
            fwd_mask[out_n] |= (1 << bit)

        for n in reversed(topo_order):
            if fwd_mask[n] == 0:
                continue
            for pred in adj_in.get(n, []):
                fwd_mask[pred] |= fwd_mask[n]

        # ── Backward CoI: propagate input-reachability FORWARD ──
        bwd_mask = [0] * num_nodes
        for bit, in_n in enumerate(input_nodes):
            bwd_mask[in_n] |= (1 << bit)

        for n in topo_order:
            if bwd_mask[n] == 0:
                continue
            for succ in adj_out.get(n, []):
                bwd_mask[succ] |= bwd_mask[n]

        return fwd_mask, bwd_mask

    @staticmethod
    def _compute_wcc_sizes(
        adj_out: dict[int, list[int]],
        adj_in:  dict[int, list[int]],
        num_nodes: int,
    ) -> list[int]:
        """Weakly connected component sizes via iterative BFS.  O(N + E)."""
        visited = [False] * num_nodes
        comp_id  = [-1] * num_nodes
        comp_sizes: list[int] = []
        cid = 0

        for start in range(num_nodes):
            if visited[start]:
                continue
            stack: list[int] = [start]
            visited[start] = True
            members: list[int] = []
            while stack:
                n = stack.pop()
                members.append(n)
                comp_id[n] = cid
                for nb in adj_out.get(n, []) + adj_in.get(n, []):
                    if not visited[nb]:
                        visited[nb] = True
                        stack.append(nb)

            comp_sizes.append(len(members))
            cid += 1

        return [comp_sizes[comp_id[i]] for i in range(num_nodes)]

    @staticmethod
    def _normalize(values: list[int], cap: int) -> list[float]:
        """Cap at `cap`, then min-max normalize to [0, 1].  O(N)."""
        capped = [min(v, cap) for v in values]
        lo = min(capped)
        hi = max(capped)
        span = hi - lo
        if span == 0:
            return [0.0] * len(capped)

        return [(v - lo) / span for v in capped]
