"""NetlistGraphBuilder facade for converting netlists to PyTorch Geometric graphs."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

import torch
from torch_geometric.data import Data

from trojan_detector.backend.core.exceptions import GraphBuildError
from trojan_detector.backend.core.history import History
from trojan_detector.backend.core.outcome import StageOutcome
from trojan_detector.backend.netlist_graph_builder.edge_encoder import EdgeEncoder
from trojan_detector.backend.netlist_graph_builder.models import CircuitGraph, NodeFeatures
from trojan_detector.backend.netlist_graph_builder.node_encoder import NodeEncoder
from trojan_detector.backend.netlist_synthesizer.models import SynthesisResult

logger = logging.getLogger(__name__)

STAGE = "netlist_graph_builder"


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
        self, synthesis_result: SynthesisResult
    ) -> StageOutcome[CircuitGraph]:
        """Build a circuit graph from a synthesis result.

        Args:
            synthesis_result: SynthesisResult from netlist_synthesizer.

        Returns:
            StageOutcome wrapping a CircuitGraph.
        """
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
        netnames = module_data.get("netnames", {})

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
            node_types.append(cell_type.upper())
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

        # Encode node features
        fan_in_list = [fan_in.get(i, 0) for i in range(len(node_map))]
        fan_out_list = [fan_out.get(i, 0) for i in range(len(node_map))]
        x = self._node_encoder.encode_batch(node_types, fan_in_list, fan_out_list)

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
            additional_features=["fan_in", "fan_out"],
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
        self, synthesis_results: list[SynthesisResult]
    ) -> list[CircuitGraph]:
        """Build circuit graphs for multiple synthesis results."""
        graphs = []
        for result in synthesis_results:
            graph = self._build_from_json(result.json_netlist)
            graphs.append(graph)
        return graphs
