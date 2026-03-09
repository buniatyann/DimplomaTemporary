"""NetlistGraphBuilder facade for converting netlists to PyTorch Geometric graphs."""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict, deque
from typing import Any

import torch
from torch_geometric.data import Data

from backend.core.exceptions import GraphBuildError
from backend.core.history import History
from backend.core.outcome import StageOutcome
from backend.netlist_graph_builder.edge_encoder import EdgeEncoder
from backend.netlist_graph_builder.models import CircuitGraph, NodeFeatures
from backend.netlist_graph_builder.node_encoder import FEATURE_DIM, VOCAB_SIZE, NodeEncoder

logger = logging.getLogger(__name__)

STAGE = "netlist_graph_builder"

# Types considered rare for structural features
_RARE_TYPES = frozenset({"UNKNOWN", "LATCH", "MUX"})

# Yosys internal cell types → canonical gate types
_YOSYS_TYPE_MAP: dict[str, str] = {
    "$_AND_": "AND", "$_NAND_": "NAND",
    "$_OR_": "OR", "$_NOR_": "NOR",
    "$_XOR_": "XOR", "$_XNOR_": "XNOR",
    "$_NOT_": "NOT", "$_BUF_": "BUF",
    "$_MUX_": "MUX",
    "$_DFF_P_": "DFF", "$_DFF_N_": "DFF",
    "$_DFF_PP0_": "DFF", "$_DFF_PP1_": "DFF",
    "$_DFF_PN0_": "DFF", "$_DFF_PN1_": "DFF",
    "$_DFFE_PP_": "DFF", "$_DFFE_PN_": "DFF",
    "$_DLATCH_P_": "LATCH", "$_DLATCH_N_": "LATCH",
    "$DFF": "DFF", "$DFFE": "DFF",
    "$DLATCH": "LATCH",
    "$AND": "AND", "$OR": "OR", "$NOT": "NOT",
    "$XOR": "XOR", "$XNOR": "XNOR",
    "$MUX": "MUX",
}


def _normalize_yosys_type(raw_type: str) -> str:
    """Normalize a Yosys cell type to canonical gate type."""
    # Direct match
    if raw_type in _YOSYS_TYPE_MAP:
        return _YOSYS_TYPE_MAP[raw_type]
    # Upper-case direct match
    upper = raw_type.upper()
    if upper in _YOSYS_TYPE_MAP:
        return _YOSYS_TYPE_MAP[upper]
    # Strip $ and _ prefixes/suffixes for matching
    stripped = raw_type.lstrip("$").strip("_").upper()
    # Common prefixes: DFF_X1, AND2_X1, NAND3, LEDA 250nm cells (nnd2s1, hi1s1), etc.
    for prefix in ("DFF", "AND", "NAND", "NND", "OR", "NOR", "XOR", "XNOR",
                    "NOT", "BUF", "INV", "HI1", "MUX", "LATCH"):
        if stripped.startswith(prefix):
            if prefix in ("INV", "HI1"):
                return "NOT"
            if prefix == "NND":
                return "NAND"
            return prefix

    return stripped if stripped else "UNKNOWN"


class NetlistGraphBuilder:
    """Transforms validated netlist representations into PyTorch Geometric graph structures."""

    def __init__(
        self,
        history: History,
        node_encoder: NodeEncoder | None = None,
        edge_encoder: EdgeEncoder | None = None,
    ) -> None:
        self._history = history
        self._node_encoder = node_encoder or NodeEncoder()
        self._edge_encoder = edge_encoder or EdgeEncoder()

    def process(
        self, synthesis_result: "SynthesisResult"
    ) -> StageOutcome[CircuitGraph]:
        """Build a circuit graph from a synthesis result.

        Args:
            synthesis_result: SynthesisResult from netlist_synthesizer.

        Returns:
            StageOutcome wrapping a CircuitGraph.
        """
        from backend.netlist_synthesizer.models import SynthesisResult as _SR  # noqa: F841

        self._history.begin_stage(STAGE)
        start = time.time()

        try:
            graph = self._build_from_json(synthesis_result.json_netlist)
        except GraphBuildError as e:
            self._history.error(STAGE, str(e), data=e.context)
            self._history.end_stage(STAGE, status="failed")

            return StageOutcome.fail(str(e), stage_name=STAGE)
        except Exception as e:
            msg = f"Unexpected error during graph construction: {e}"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")

            return StageOutcome.fail(msg, stage_name=STAGE)

        duration = time.time() - start

        # Record in history
        self._history.record(STAGE, "node_count", graph.node_count)
        self._history.record(STAGE, "edge_count", graph.edge_count)
        self._history.record(STAGE, "construction_duration", duration)
        self._history.record(STAGE, "vocabulary_size", self._node_encoder.vocab_size)
        self._history.record(STAGE, "feature_dim", self._node_encoder.feature_dim)

        unknown = self._node_encoder.unknown_types
        if unknown:
            self._history.warning(
                STAGE,
                f"Unknown gate types encountered: {unknown}",
                data={"unknown_types": list(unknown)},
            )

            self._history.record(STAGE, "unknown_gate_types", list(unknown))

        self._history.info(
            STAGE,
            f"Graph built: {graph.node_count} nodes, {graph.edge_count} edges",
        )

        self._history.end_stage(STAGE, status="completed")
        return StageOutcome.ok(graph, stage_name=STAGE)

    def _build_from_json(self, json_netlist: dict[str, Any]) -> CircuitGraph:
        """Construct a CircuitGraph from a Yosys JSON netlist."""
        modules = json_netlist.get("modules", {})
        if not modules:
            raise GraphBuildError("JSON netlist contains no modules")

        # Use the first (top-level) module
        module_name = next(iter(modules))
        module_data = modules[module_name]

        cells = module_data.get("cells", {})
        ports = module_data.get("ports", {})

        if not cells and not ports:
            raise GraphBuildError(f"Module '{module_name}' has no cells or ports")

        # Map: node_name -> node_index
        node_map: dict[str, int] = {}
        node_types: list[str] = []
        node_names: list[str] = []

        # Add port nodes (primary inputs/outputs)
        for port_name, port_data in ports.items():
            direction = port_data.get("direction", "")
            idx = len(node_map)
            node_map[port_name] = idx
            canonical = "INPUT" if direction == "input" else "OUTPUT"
            node_types.append(canonical)
            node_names.append(port_name)

        # Add cell nodes
        for cell_name, cell_data in cells.items():
            idx = len(node_map)
            node_map[cell_name] = idx
            cell_type = cell_data.get("type", "UNKNOWN")
            cell_type = _normalize_yosys_type(cell_type)
            node_types.append(cell_type)
            node_names.append(cell_name)

        # Build wire-to-node connectivity
        # Map: bit_id -> list of (node_name, direction)
        bit_to_drivers: dict[int, list[str]] = defaultdict(list)
        bit_to_sinks: dict[int, list[str]] = defaultdict(list)

        # Port connections
        for port_name, port_data in ports.items():
            direction = port_data.get("direction", "")
            bits = port_data.get("bits", [])
            for bit in bits:
                if isinstance(bit, int):
                    if direction == "input":
                        bit_to_drivers[bit].append(port_name)
                    elif direction == "output":
                        bit_to_sinks[bit].append(port_name)

        # Cell connections
        for cell_name, cell_data in cells.items():
            connections = cell_data.get("connections", {})
            port_directions = cell_data.get("port_directions", {})
            for pin_name, bits in connections.items():
                pin_dir = port_directions.get(pin_name, "input")
                for bit in bits:
                    if isinstance(bit, int):
                        if pin_dir == "output":
                            bit_to_drivers[bit].append(cell_name)
                        else:
                            bit_to_sinks[bit].append(cell_name)

        # Build edges: driver -> sink for each shared bit
        edge_sources: list[int] = []
        edge_targets: list[int] = []

        for bit_id in set(bit_to_drivers.keys()) & set(bit_to_sinks.keys()):
            for driver in bit_to_drivers[bit_id]:
                for sink in bit_to_sinks[bit_id]:
                    if driver in node_map and sink in node_map:
                        edge_sources.append(node_map[driver])
                        edge_targets.append(node_map[sink])

        # Compute fan-in and fan-out
        fan_in: dict[int, int] = defaultdict(int)
        fan_out: dict[int, int] = defaultdict(int)
        for src, tgt in zip(edge_sources, edge_targets):
            fan_out[src] += 1
            fan_in[tgt] += 1

        # Encode node features (one-hot + basic, 26-dim with structural slots zeroed)
        fan_in_list = [fan_in.get(i, 0) for i in range(len(node_map))]
        fan_out_list = [fan_out.get(i, 0) for i in range(len(node_map))]
        x = self._node_encoder.encode_batch(node_types, fan_in_list, fan_out_list)

        # Compute and fill structural features [19..25]
        edges_list = list(zip(edge_sources, edge_targets))
        struct_feats = _compute_structural_features(
            node_names, edges_list, node_types,
        )
        x[:, VOCAB_SIZE + 4:] = struct_feats

        # Build edge_index tensor
        if edge_sources:
            edge_index = torch.tensor([edge_sources, edge_targets], dtype=torch.long)
        else:
            edge_index = torch.zeros((2, 0), dtype=torch.long)

        # Create PyTorch Geometric Data object
        data = Data(x=x, edge_index=edge_index)

        # Node-to-gate mapping
        node_to_gate = {i: name for name, i in node_map.items()}

        features_info = NodeFeatures(
            dimensionality=self._node_encoder.feature_dim,
            vocabulary=self._node_encoder.vocabulary,
            additional_features=[
                "fan_in", "fan_out", "depth", "is_seq",
                "degree_centrality", "is_io_adjacent", "neighbor_type_entropy",
                "rare_type_ratio", "local_fanout_anomaly",
                "min_dist_to_input", "min_dist_to_output",
                "twohop_neighborhood_size", "local_clustering_coeff",
                "avg_neighbor_degree", "fanin_fanout_imbalance",
                "combinational_depth",
            ],
        )

        return CircuitGraph(
            graph_data=data,
            node_to_gate=node_to_gate,
            module_name=module_name,
            node_features_info=features_info,
            node_count=len(node_map),
            edge_count=len(edge_sources),
        )

    def build_batch(
        self, synthesis_results: list
    ) -> list[CircuitGraph]:
        """Build circuit graphs for multiple synthesis results."""
        graphs = []
        for result in synthesis_results:
            graph = self._build_from_json(result.json_netlist)
            graphs.append(graph)

        return graphs


# ---------------------------------------------------------------------------
# Structural feature computation (ported from training/train_local.py)
# ---------------------------------------------------------------------------

# Gate type vocabulary for entropy normalization
_TYPE_VOCAB_SIZE = 15


def _compute_structural_features(
    nodes: list[str],
    edges: list[tuple[int, int]],
    node_types: list[str],
) -> torch.Tensor:
    """Compute 12 structural features per node.

    Features:
        0: degree_centrality
        1: is_io_adjacent
        2: neighbor_type_entropy
        3: rare_type_ratio
        4: local_fanout_anomaly
        5: min_dist_to_input
        6: min_dist_to_output
        7: twohop_neighborhood_size
        8: local_clustering_coeff
        9: avg_neighbor_degree
       10: fanin_fanout_imbalance
       11: combinational_depth (longest path from input, normalized)
    """
    n = len(nodes)
    feats = torch.zeros((n, 12), dtype=torch.float)
    if n == 0:
        return feats

    # Build adjacency lists
    adj_out: list[list[int]] = [[] for _ in range(n)]
    adj_in: list[list[int]] = [[] for _ in range(n)]
    for s, t in edges:
        adj_out[s].append(t)
        adj_in[t].append(s)

    # Build undirected neighbor sets for clustering coefficient
    adj_undirected: list[set[int]] = [set() for _ in range(n)]
    for s, t in edges:
        adj_undirected[s].add(t)
        adj_undirected[t].add(s)

    fi = [len(adj_in[i]) for i in range(n)]
    fo = [len(adj_out[i]) for i in range(n)]
    degrees = [fi[i] + fo[i] for i in range(n)]
    max_deg = max(degrees) if degrees else 1

    # Identify I/O nodes
    io_set: set[int] = set()
    input_nodes: list[int] = []
    output_nodes: list[int] = []
    for i, nt in enumerate(node_types):
        if nt == "INPUT":
            io_set.add(i)
            input_nodes.append(i)
        elif nt == "OUTPUT":
            io_set.add(i)
            output_nodes.append(i)

    # Per-type fan-out statistics
    type_fanouts: dict[str, list[int]] = {}
    for i, nt in enumerate(node_types):
        type_fanouts.setdefault(nt, []).append(fo[i])

    type_mean_fo: dict[str, float] = {}
    type_std_fo: dict[str, float] = {}
    for nt, fos in type_fanouts.items():
        mean = sum(fos) / len(fos)
        type_mean_fo[nt] = mean
        var = sum((x - mean) ** 2 for x in fos) / max(len(fos), 1)
        type_std_fo[nt] = max(var ** 0.5, 1.0)

    # Multi-source BFS from all inputs (shortest path)
    dist_from_input = [float("inf")] * n
    if input_nodes:
        q: deque[int] = deque()
        for s in input_nodes:
            dist_from_input[s] = 0
            q.append(s)

        while q:
            u = q.popleft()
            for v in adj_out[u]:
                if dist_from_input[v] > dist_from_input[u] + 1:
                    dist_from_input[v] = dist_from_input[u] + 1
                    q.append(v)

    # Multi-source BFS from all outputs (reverse direction)
    dist_from_output = [float("inf")] * n
    if output_nodes:
        q = deque()
        for s in output_nodes:
            dist_from_output[s] = 0
            q.append(s)

        while q:
            u = q.popleft()
            for v in adj_in[u]:
                if dist_from_output[v] > dist_from_output[u] + 1:
                    dist_from_output[v] = dist_from_output[u] + 1
                    q.append(v)

    # Combinational depth: longest path from any input (topological relaxation)
    comb_depth = [0] * n
    if input_nodes:
        # Use topological order via Kahn's algorithm
        in_degree = [len(adj_in[i]) for i in range(n)]
        topo_q: deque[int] = deque()
        for i in range(n):
            if in_degree[i] == 0:
                topo_q.append(i)
        # For inputs, depth = 0
        for s in input_nodes:
            comb_depth[s] = 0

        while topo_q:
            u = topo_q.popleft()
            for v in adj_out[u]:
                comb_depth[v] = max(comb_depth[v], comb_depth[u] + 1)
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    topo_q.append(v)

    max_comb_depth = max(comb_depth) if comb_depth else 1
    max_comb_depth = max(max_comb_depth, 1)

    max_dist = 50.0

    for i in range(n):
        neighbors = set(adj_out[i]) | set(adj_in[i])

        # 0: degree centrality
        feats[i, 0] = degrees[i] / max(max_deg, 1)

        # 1: is_io_adjacent
        feats[i, 1] = 1.0 if neighbors & io_set else 0.0

        # 2: neighbor type entropy
        if neighbors:
            type_counts: dict[str, int] = {}
            for nb in neighbors:
                nt = node_types[nb]
                type_counts[nt] = type_counts.get(nt, 0) + 1

            total = sum(type_counts.values())
            entropy = 0.0
            for cnt in type_counts.values():
                p = cnt / total
                if p > 0:
                    entropy -= p * math.log2(p)

            feats[i, 2] = entropy / max(math.log2(_TYPE_VOCAB_SIZE), 1.0)

        # 3: rare_type_ratio among neighbors
        if neighbors:
            rare_count = sum(1 for nb in neighbors if node_types[nb] in _RARE_TYPES)
            feats[i, 3] = rare_count / len(neighbors)

        # 4: local fan-out anomaly (z-score, clamped)
        nt = node_types[i]
        mean_fo_val = type_mean_fo.get(nt, 0.0)
        std_fo_val = type_std_fo.get(nt, 1.0)
        z = (fo[i] - mean_fo_val) / std_fo_val
        feats[i, 4] = min(max(z / 3.0, -1.0), 1.0)

        # 5: min distance to input (normalized)
        d_in = dist_from_input[i]
        feats[i, 5] = min(d_in, max_dist) / max_dist if d_in != float("inf") else 1.0

        # 6: min distance to output (normalized)
        d_out = dist_from_output[i]
        feats[i, 6] = min(d_out, max_dist) / max_dist if d_out != float("inf") else 1.0

        # 7: 2-hop neighborhood size (normalized by total nodes)
        twohop = set(neighbors)
        for nb in neighbors:
            twohop.update(adj_out[nb])
            twohop.update(adj_in[nb])
        twohop.discard(i)
        feats[i, 7] = len(twohop) / max(n - 1, 1)

        # 8: local clustering coefficient (undirected, capped for perf)
        und_neighbors = adj_undirected[i]
        k = len(und_neighbors)
        if k >= 2 and k <= 200:  # skip very high-degree nodes (O(k^2))
            triangles = 0
            nb_list = list(und_neighbors)
            for a_idx in range(len(nb_list)):
                for b_idx in range(a_idx + 1, len(nb_list)):
                    if nb_list[b_idx] in adj_undirected[nb_list[a_idx]]:
                        triangles += 1
            feats[i, 8] = (2.0 * triangles) / (k * (k - 1))

        # 9: average neighbor degree (normalized)
        if neighbors:
            avg_nd = sum(degrees[nb] for nb in neighbors) / len(neighbors)
            feats[i, 9] = avg_nd / max(max_deg, 1)

        # 10: fan-in/fan-out imbalance
        feats[i, 10] = abs(fi[i] - fo[i]) / (fi[i] + fo[i] + 1)

        # 11: combinational depth (longest path from input, normalized)
        feats[i, 11] = comb_depth[i] / max_comb_depth

    return feats
