"""TrojanClassifier facade for GNN-based trojan detection."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import torch
import torch.nn.functional as F

from backend.core.exceptions import ClassificationError
from backend.core.history import History
from backend.core.outcome import StageOutcome
from backend.netlist_graph_builder.models import CircuitGraph
from backend.trojan_classifier.architectures.gat import GATClassifier
from backend.trojan_classifier.architectures.gcn import GCNClassifier
from backend.trojan_classifier.architectures.gin import GINClassifier
from backend.trojan_classifier.localization import localize_trojans
from backend.trojan_classifier.models import (
    ClassificationResult,
    TrojanLocation,
    TrojanVerdict,
)

if TYPE_CHECKING:
    from backend.syntax_parser.models import ParsedModule

logger = logging.getLogger(__name__)

STAGE = "trojan_classifier"

WEIGHTS_DIR = Path(__file__).parent / "weights"

ARCHITECTURE_MAP = {
    "gcn": GCNClassifier,
    "gat": GATClassifier,
    "gin": GINClassifier,
}

# Threshold for considering a node suspicious (for location reporting)
SUSPICION_THRESHOLD = 0.3

# Threshold percentage of trojan nodes to trigger high-risk alert
HIGH_RISK_THRESHOLD = 5.0


class TrojanClassifier:
    """Applies trained GNN models to circuit graphs for trojan detection.

    Extended to provide detailed trojan localization with source file
    and line number information when a high percentage of nodes are
    identified as suspicious.
    """

    def __init__(
        self,
        history: History,
        architecture: str = "gcn",
        model_path: Path | None = None,
        confidence_threshold: float = 0.7,
        suspicion_threshold: float = SUSPICION_THRESHOLD,
        risk_threshold: float = HIGH_RISK_THRESHOLD,
        device: str | None = None,
    ) -> None:
        self._history = history
        self._architecture = architecture
        self._model_path = model_path
        self._confidence_threshold = confidence_threshold
        self._suspicion_threshold = suspicion_threshold
        self._risk_threshold = risk_threshold
        self._model: torch.nn.Module | None = None
        self._model_version = "0.1.0"
        self._parsed_modules: list[ParsedModule] | None = None

        if device is None:
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self._device = torch.device(device)

    def set_parsed_modules(self, modules: list[ParsedModule]) -> None:
        """Set parsed module data for source location resolution.

        Should be called before process() to enable line number reporting.
        """
        self._parsed_modules = modules

    def process(
        self,
        circuit_graph: CircuitGraph,
        parsed_modules: list[ParsedModule] | None = None,
    ) -> StageOutcome[ClassificationResult]:
        """Classify a circuit graph as clean or trojan-infected.

        Args:
            circuit_graph: CircuitGraph from netlist_graph_builder.
            parsed_modules: Optional parsed modules for source location resolution.

        Returns:
            StageOutcome wrapping a ClassificationResult with trojan locations.
        """
        if parsed_modules is not None:
            self._parsed_modules = parsed_modules

        self._history.begin_stage(STAGE)
        start = time.time()

        try:
            self._load_model(circuit_graph)
        except ClassificationError as e:
            self._history.error(STAGE, str(e), data=e.context)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(str(e), stage_name=STAGE)

        try:
            result = self._classify(circuit_graph)
        except Exception as e:
            msg = f"Classification failed: {e}"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        duration = time.time() - start

        # Record in history
        self._history.record(STAGE, "verdict", result.verdict.value)
        self._history.record(STAGE, "confidence", result.confidence)
        self._history.record(STAGE, "trojan_probability", result.trojan_probability)
        self._history.record(STAGE, "model_version", result.model_version)
        self._history.record(STAGE, "architecture", result.architecture)
        self._history.record(STAGE, "inference_duration", duration)
        self._history.record(STAGE, "device", str(self._device))
        self._history.record(STAGE, "trojan_node_percentage", result.trojan_node_percentage)
        self._history.record(STAGE, "high_risk", result.high_risk)
        self._history.record(STAGE, "trojan_modules", result.trojan_modules)

        if result.verdict == TrojanVerdict.INFECTED or result.high_risk:
            # Record top suspicious gates with locations
            top_locations = result.get_top_suspicious(20)
            self._history.record(
                STAGE,
                "top_suspicious_gates",
                [
                    {
                        "gate": loc.gate_name,
                        "score": loc.suspicion_score,
                        "module": loc.module_name,
                        "file": loc.source_file,
                        "line": loc.line_number,
                        "type": loc.gate_type,
                    }
                    for loc in top_locations
                ],
            )

            # Record locations by module for structured reporting
            by_module = result.get_locations_by_module()
            self._history.record(
                STAGE,
                "trojan_locations_by_module",
                {
                    module: [
                        {
                            "gate": loc.gate_name,
                            "line": loc.line_number,
                            "score": loc.suspicion_score,
                        }
                        for loc in locs
                    ]
                    for module, locs in by_module.items()
                },
            )

        # Log result
        self._history.info(
            STAGE,
            f"Classification: {result.verdict.value} "
            f"(confidence={result.confidence:.4f}, p(trojan)={result.trojan_probability:.4f}, "
            f"trojan_nodes={result.trojan_node_percentage:.2f}%)",
        )

        if result.high_risk:
            self._history.warning(
                STAGE,
                f"HIGH RISK: {result.trojan_node_percentage:.2f}% of nodes identified as trojan. "
                f"Affected modules: {', '.join(result.trojan_modules)}",
            )

        self._history.end_stage(STAGE, status="completed")

        return StageOutcome.ok(result, stage_name=STAGE)

    def _load_model(self, circuit_graph: CircuitGraph) -> None:
        """Load the GNN model, initializing with random weights if no checkpoint exists."""
        if self._model is not None:
            return

        if self._architecture not in ARCHITECTURE_MAP:
            raise ClassificationError(
                f"Unknown architecture: {self._architecture}",
                model_name=self._architecture,
            )

        input_dim = circuit_graph.graph_data.x.shape[1] if circuit_graph.graph_data is not None else 17

        model_cls = ARCHITECTURE_MAP[self._architecture]
        self._model = model_cls(input_dim=input_dim)

        # Try to load pretrained weights
        if self._model_path is not None:
            weight_file = self._model_path
        else:
            weight_file = WEIGHTS_DIR / f"{self._architecture}_weights.pt"

        if weight_file.exists():
            try:
                state_dict = torch.load(weight_file, map_location=self._device, weights_only=True)
                self._model.load_state_dict(state_dict)
                self._history.info(STAGE, f"Loaded weights from {weight_file}")
            except Exception as e:
                self._history.warning(
                    STAGE,
                    f"Failed to load weights from {weight_file}: {e}. Using random initialization.",
                )
        else:
            self._history.warning(
                STAGE,
                f"No pretrained weights found at {weight_file}. Using random initialization.",
            )

        self._model.to(self._device)
        self._model.eval()

    def _classify(self, circuit_graph: CircuitGraph) -> ClassificationResult:
        """Run inference on a circuit graph with algorithmic trojan localization."""
        assert self._model is not None

        data = circuit_graph.graph_data
        data = data.to(self._device)

        # Create batch tensor (single graph)
        batch = torch.zeros(data.x.shape[0], dtype=torch.long, device=self._device)

        with torch.no_grad():
            graph_logits, node_logits = self._model(data.x, data.edge_index, batch)
            graph_probs = F.softmax(graph_logits, dim=1)

        # Class 0 = clean, Class 1 = infected
        trojan_prob = graph_probs[0, 1].item()
        clean_prob = graph_probs[0, 0].item()
        confidence = max(trojan_prob, clean_prob)

        if confidence < self._confidence_threshold:
            verdict = TrojanVerdict.UNCERTAIN
        elif trojan_prob > clean_prob:
            verdict = TrojanVerdict.INFECTED
        else:
            verdict = TrojanVerdict.CLEAN

        # Stage 2: algorithmic localization only runs on flagged circuits.
        if verdict == TrojanVerdict.CLEAN:
            logger.debug("Graph classified as CLEAN — skipping localization.")
            gate_scores: dict[str, float] = {}
            trojan_locations = []
            trojan_percentage = 0.0
            high_risk = False
            trojan_modules: list[str] = []
        else:
            # Algorithmic localization via structural anomaly detection
            gate_scores = localize_trojans(circuit_graph, self._suspicion_threshold)

            # Identify trojan locations for nodes above threshold
            trojan_locations = self._locate_trojans(circuit_graph, gate_scores)

            # Calculate trojan node percentage
            total_nodes = len(gate_scores)
            suspicious_count = len(trojan_locations)
            trojan_percentage = (suspicious_count / total_nodes * 100) if total_nodes > 0 else 0.0

            # Determine if high risk
            high_risk = trojan_percentage >= self._risk_threshold

            # Collect affected modules
            trojan_modules = list(set(loc.module_name for loc in trojan_locations))

        return ClassificationResult(
            verdict=verdict,
            confidence=confidence,
            trojan_probability=trojan_prob,
            gate_suspicion_scores=gate_scores,
            model_version=self._model_version,
            architecture=self._architecture,
            trojan_locations=trojan_locations,
            trojan_node_percentage=trojan_percentage,
            trojan_modules=trojan_modules,
            high_risk=high_risk,
            risk_threshold=self._risk_threshold,
        )

    def _locate_trojans(
        self,
        circuit_graph: CircuitGraph,
        gate_scores: dict[str, float],
    ) -> list[TrojanLocation]:
        """Identify and locate suspected trojan nodes with source information.

        Args:
            circuit_graph: The circuit graph being analyzed.
            gate_scores: Per-gate suspicion scores from GNN.

        Returns:
            List of TrojanLocation objects for gates above threshold.
        """
        locations: list[TrojanLocation] = []

        # Build lookups from parsed modules
        module_lookup = self._build_module_lookup()
        gate_lookup = self._build_gate_lookup()

        for node_idx, gate_name in circuit_graph.node_to_gate.items():
            score = gate_scores.get(gate_name, 0.0)

            if score < self._suspicion_threshold:
                continue

            # Get gate information
            gate_info = gate_lookup.get(gate_name, {})
            module_name = gate_info.get("module_name", "unknown")
            gate_type = gate_info.get("gate_type", "unknown")

            # Get source file and line number
            source_file = None
            line_number = gate_info.get("line_number")

            module_info = module_lookup.get(module_name)
            if module_info:
                source_path = module_info.get("source_path")
                if source_path:
                    source_file = source_path
                    # Fall back to regex search if parser didn't capture line number
                    if line_number is None:
                        line_number = self._find_gate_line(Path(source_path), gate_name)

            # Determine detection method
            if self._matches_trojan_pattern(gate_name):
                detection_method = "name_pattern"
            else:
                detection_method = "structural"

            location = TrojanLocation(
                node_index=node_idx,
                gate_name=gate_name,
                gate_type=gate_type,
                module_name=module_name,
                source_file=source_file,
                line_number=line_number,
                suspicion_score=score,
                detection_method=detection_method,
            )
            locations.append(location)

        # Sort by suspicion score (highest first)
        locations.sort(key=lambda x: x.suspicion_score, reverse=True)

        return locations

    def _build_module_lookup(self) -> dict[str, dict]:
        """Build lookup table for module information."""
        if not self._parsed_modules:
            return {}

        lookup = {}
        for module in self._parsed_modules:
            lookup[module.name] = {
                "source_path": module.source_path,
                "gate_count": len(module.gates),
            }
        return lookup

    def _build_gate_lookup(self) -> dict[str, dict]:
        """Build lookup table for gate information."""
        if not self._parsed_modules:
            return {}

        lookup = {}
        for module in self._parsed_modules:
            for gate in module.gates:
                lookup[gate.instance_name] = {
                    "module_name": module.name,
                    "gate_type": gate.canonical_type or gate.gate_type,
                    "line_number": gate.line_number,
                }
        return lookup

    def _find_gate_line(self, source_file: Path, gate_name: str) -> int | None:
        """Search source file to find the line containing a gate instance.

        Args:
            source_file: Path to Verilog/SystemVerilog file.
            gate_name: Name of the gate instance to find.

        Returns:
            Line number (1-indexed) or None if not found.
        """
        if not source_file.exists():
            return None

        try:
            with open(source_file, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    # Look for instance declaration patterns
                    # Pattern 1: "instance_name (" - module instantiation
                    if re.search(rf'\b{re.escape(gate_name)}\s*\(', line):
                        return line_num
                    # Pattern 2: ".port(instance_name)" - port connection
                    if re.search(rf'\.\w+\s*\(\s*{re.escape(gate_name)}\s*\)', line):
                        return line_num
                    # Pattern 3: "wire/reg instance_name" - signal declaration
                    if re.search(rf'\b(wire|reg)\b.*\b{re.escape(gate_name)}\b', line):
                        return line_num
        except Exception as e:
            logger.debug(f"Could not search {source_file}: {e}")

        return None

    def _matches_trojan_pattern(self, name: str) -> bool:
        """Check if a gate name matches known trojan naming patterns."""
        patterns = [
            r"(?i)trojan",
            r"(?i)^tj_",
            r"(?i)_tj$",
            r"(?i)trigger",
            r"(?i)payload",
            r"(?i)^mal_",
            r"(?i)^ht_",
            r"(?i)backdoor",
            r"(?i)leak",
        ]
        for pattern in patterns:
            if re.search(pattern, name):
                return True
        return False
