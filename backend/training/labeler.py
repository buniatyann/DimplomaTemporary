"""Trojan node labeling for TrustHub benchmarks.

This module identifies which nodes in a circuit graph correspond to trojan
circuitry by analyzing naming conventions, structural differences between
trojan and golden versions, and TrustHub-specific annotations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import torch

if TYPE_CHECKING:
    from backend.netlist_graph_builder.models import CircuitGraph
    from backend.syntax_parser.models import ParsedModule
    from backend.training.trusthub_dataset import TrustHubBenchmark

logger = logging.getLogger(__name__)


# Common trojan naming patterns in TrustHub benchmarks
TROJAN_NAME_PATTERNS = [
    r"(?i)trojan",       # Case-insensitive "trojan"
    r"(?i)^tj_",         # Tj_ prefix
    r"(?i)_tj$",         # _tj suffix
    r"(?i)^trig",        # Trigger prefix
    r"(?i)trigger",      # Contains "trigger"
    r"(?i)payload",      # Payload logic
    r"(?i)^mal_",        # Malicious prefix
    r"(?i)_mal$",        # Malicious suffix
    r"(?i)^ht_",         # Hardware Trojan prefix
    r"(?i)_ht$",         # Hardware Trojan suffix
    r"(?i)^hack",        # Hack prefix
    r"(?i)leak",         # Leakage logic
    r"(?i)covert",       # Covert channel
    r"(?i)backdoor",     # Backdoor
    r"(?i)^tsc",         # Trojan state counter
    r"(?i)trojanfsm",    # Trojan FSM
    r"(?i)^t[0-9]+_",    # T1_, T2_, etc. prefix
]

# Compiled regex patterns for efficiency
TROJAN_PATTERNS_COMPILED = [re.compile(p) for p in TROJAN_NAME_PATTERNS]


@dataclass
class TrojanLocation:
    """Detailed location information for identified trojan logic.

    Attributes:
        node_index: Index in the circuit graph
        gate_name: Name of the gate/instance
        gate_type: Type of gate (AND, OR, DFF, etc.)
        module_name: Name of the Verilog module containing the gate
        source_file: Path to the source Verilog file
        line_number: Line number in the source file (if available)
        column: Column number (if available)
        confidence: Confidence score for this being trojan logic (0-1)
        detection_method: How this node was identified as trojan
    """
    node_index: int
    gate_name: str
    gate_type: str
    module_name: str
    source_file: Path | None = None
    line_number: int | None = None
    column: int | None = None
    confidence: float = 1.0
    detection_method: str = "pattern_match"

    def to_dict(self) -> dict:
        return {
            "node_index": self.node_index,
            "gate_name": self.gate_name,
            "gate_type": self.gate_type,
            "module_name": self.module_name,
            "source_file": str(self.source_file) if self.source_file else None,
            "line_number": self.line_number,
            "column": self.column,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
        }


class TrojanLabeler:
    """Labels circuit graph nodes as trojan or benign.

    Uses multiple strategies:
    1. Name pattern matching (TrustHub conventions)
    2. Structural comparison with golden reference
    3. Annotation files from TrustHub (if available)
    """

    def __init__(self, custom_patterns: list[str] | None = None) -> None:
        """Initialize the labeler.

        Args:
            custom_patterns: Additional regex patterns to match trojan names.
        """
        self._patterns = list(TROJAN_PATTERNS_COMPILED)
        if custom_patterns:
            self._patterns.extend([re.compile(p) for p in custom_patterns])

    def label_nodes(
        self,
        circuit_graph: CircuitGraph,
        parsed_modules: list[ParsedModule],
        benchmark: TrustHubBenchmark,
    ) -> torch.Tensor:
        """Label each node in the circuit graph as trojan (1) or benign (0).

        Args:
            circuit_graph: The circuit graph to label.
            parsed_modules: Parsed module data with source information.
            benchmark: TrustHub benchmark metadata.

        Returns:
            Tensor of shape (num_nodes,) with binary labels.
        """
        num_nodes = circuit_graph.node_count
        labels = torch.zeros(num_nodes, dtype=torch.long)

        # Build module lookup for source information
        module_lookup = self._build_module_lookup(parsed_modules)

        # Strategy 1: Name pattern matching
        for node_idx, gate_name in circuit_graph.node_to_gate.items():
            if self._matches_trojan_pattern(gate_name):
                labels[node_idx] = 1
                logger.debug(f"Trojan node (pattern): {gate_name}")

        # Strategy 2: Check against benchmark's known trojan nets/modules
        if benchmark.trojan_nets:
            for node_idx, gate_name in circuit_graph.node_to_gate.items():
                if gate_name in benchmark.trojan_nets:
                    labels[node_idx] = 1
                    logger.debug(f"Trojan node (known net): {gate_name}")

        if benchmark.trojan_instances:
            for node_idx, gate_name in circuit_graph.node_to_gate.items():
                if gate_name in benchmark.trojan_instances:
                    labels[node_idx] = 1
                    logger.debug(f"Trojan node (known instance): {gate_name}")

        # Strategy 3: Check module names
        if benchmark.trojan_modules:
            for module in parsed_modules:
                if module.name in benchmark.trojan_modules:
                    # Mark all gates in this module as trojan
                    for gate in module.gates:
                        for node_idx, gate_name in circuit_graph.node_to_gate.items():
                            if gate_name == gate.instance_name:
                                labels[node_idx] = 1

        # Strategy 4: Check for module-level trojan patterns
        for module in parsed_modules:
            if self._matches_trojan_pattern(module.name):
                # Mark all gates in trojan-named modules
                for gate in module.gates:
                    for node_idx, gate_name in circuit_graph.node_to_gate.items():
                        if gate_name == gate.instance_name:
                            labels[node_idx] = 1
                            logger.debug(f"Trojan node (trojan module {module.name}): {gate_name}")

        trojan_count = labels.sum().item()
        logger.info(f"Labeled {trojan_count}/{num_nodes} nodes as trojan ({100*trojan_count/num_nodes:.1f}%)")

        return labels

    def locate_trojans(
        self,
        circuit_graph: CircuitGraph,
        parsed_modules: list[ParsedModule],
        node_suspicion_scores: dict[str, float],
        threshold: float = 0.5,
    ) -> list[TrojanLocation]:
        """Identify and locate suspected trojan nodes with source file information.

        Args:
            circuit_graph: The analyzed circuit graph.
            parsed_modules: Parsed module data with source information.
            node_suspicion_scores: GNN-computed suspicion scores per gate.
            threshold: Minimum suspicion score to report.

        Returns:
            List of TrojanLocation objects for suspected trojan gates.
        """
        locations: list[TrojanLocation] = []

        # Build lookup tables
        module_lookup = self._build_module_lookup(parsed_modules)
        gate_lookup = self._build_gate_lookup(parsed_modules)

        for node_idx, gate_name in circuit_graph.node_to_gate.items():
            score = node_suspicion_scores.get(gate_name, 0.0)

            if score < threshold:
                continue

            # Determine detection method
            if self._matches_trojan_pattern(gate_name):
                method = "name_pattern"
                confidence = max(score, 0.9)  # High confidence for pattern match
            else:
                method = "gnn_attribution"
                confidence = score

            # Find source location
            gate_info = gate_lookup.get(gate_name)
            module_info = None
            source_file = None
            line_number = None

            if gate_info:
                module_name = gate_info.get("module_name", "unknown")
                gate_type = gate_info.get("gate_type", "unknown")
                module_info = module_lookup.get(module_name)

                if module_info:
                    source_file = Path(module_info["source_path"]) if module_info.get("source_path") else None
                    # Try to find line number by searching source file
                    if source_file and source_file.exists():
                        line_number = self._find_instance_line(source_file, gate_name)
            else:
                module_name = "unknown"
                gate_type = "unknown"

            location = TrojanLocation(
                node_index=node_idx,
                gate_name=gate_name,
                gate_type=gate_type,
                module_name=module_name,
                source_file=source_file,
                line_number=line_number,
                confidence=confidence,
                detection_method=method,
            )
            locations.append(location)

        # Sort by confidence (highest first)
        locations.sort(key=lambda x: x.confidence, reverse=True)

        return locations

    def _matches_trojan_pattern(self, name: str) -> bool:
        """Check if a name matches any trojan naming pattern."""
        for pattern in self._patterns:
            if pattern.search(name):
                return True
        return False

    def _build_module_lookup(
        self, parsed_modules: list[ParsedModule]
    ) -> dict[str, dict]:
        """Build a lookup table for module information."""
        lookup = {}
        for module in parsed_modules:
            lookup[module.name] = {
                "source_path": module.source_path,
                "gate_count": len(module.gates),
                "wire_count": len(module.wires),
                "port_count": len(module.ports),
            }
        return lookup

    def _build_gate_lookup(
        self, parsed_modules: list[ParsedModule]
    ) -> dict[str, dict]:
        """Build a lookup table mapping gate names to their information."""
        lookup = {}
        for module in parsed_modules:
            for gate in module.gates:
                lookup[gate.instance_name] = {
                    "module_name": module.name,
                    "gate_type": gate.canonical_type or gate.gate_type,
                    "input_pins": gate.input_pins,
                    "output_pins": gate.output_pins,
                }
        return lookup

    def _find_instance_line(self, source_file: Path, instance_name: str) -> int | None:
        """Search a Verilog file for the line containing an instance.

        Args:
            source_file: Path to the Verilog source file.
            instance_name: Name of the instance to find.

        Returns:
            Line number (1-indexed) or None if not found.
        """
        try:
            with open(source_file, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    # Look for instance name in instantiation patterns
                    # Common patterns: "module_type instance_name (" or ".port(instance_name)"
                    if re.search(rf'\b{re.escape(instance_name)}\s*\(', line):
                        return line_num
                    if re.search(rf'\b{re.escape(instance_name)}\s*;', line):
                        return line_num
                    # Also check for wire/reg declarations
                    if re.search(rf'\b{re.escape(instance_name)}\b', line):
                        return line_num
        except Exception as e:
            logger.debug(f"Could not search {source_file}: {e}")

        return None


class GoldenComparator:
    """Compares trojan and golden versions to identify inserted trojan logic.

    By comparing the circuit graphs of trojan-infected and trojan-free versions,
    we can identify nodes that exist only in the trojan version.
    """

    def find_trojan_nodes(
        self,
        trojan_graph: CircuitGraph,
        golden_graph: CircuitGraph,
    ) -> set[int]:
        """Find nodes present in trojan version but not in golden.

        Args:
            trojan_graph: Circuit graph of trojan-infected version.
            golden_graph: Circuit graph of trojan-free golden version.

        Returns:
            Set of node indices unique to the trojan version.
        """
        golden_gates = set(golden_graph.node_to_gate.values())
        trojan_only_nodes = set()

        for node_idx, gate_name in trojan_graph.node_to_gate.items():
            # Check if this gate exists in golden version
            # Use normalized comparison (ignore minor naming differences)
            base_name = self._normalize_gate_name(gate_name)
            golden_matches = [
                g for g in golden_gates
                if self._normalize_gate_name(g) == base_name
            ]

            if not golden_matches:
                trojan_only_nodes.add(node_idx)
                logger.debug(f"Trojan-only node: {gate_name}")

        return trojan_only_nodes

    def _normalize_gate_name(self, name: str) -> str:
        """Normalize gate name for comparison.

        Removes common suffixes, indices, and hierarchy prefixes that might
        differ between synthesis runs.
        """
        # Remove hierarchy separators and indices
        normalized = re.sub(r'\[\d+\]', '', name)  # Remove bit indices
        normalized = re.sub(r'_\d+$', '', normalized)  # Remove trailing numbers
        normalized = normalized.split('.')[-1]  # Take last part of hierarchy
        return normalized.lower()
