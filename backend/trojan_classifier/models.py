"""Data models for trojan classification results."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class TrojanVerdict(str, Enum):
    """Possible classification outcomes."""

    CLEAN = "clean"
    INFECTED = "infected"
    UNCERTAIN = "uncertain"


class NodeAlgorithmicInfo(BaseModel):
    """Per-node SCOAP and Cone of Influence metrics from algorithmic analysis."""

    node_index: int
    gate_name: str

    # Raw SCOAP values (integer counts before normalization)
    scoap_cc0_raw: int = Field(default=1, description="Raw CC0: cost to set node to 0")
    scoap_cc1_raw: int = Field(default=1, description="Raw CC1: cost to set node to 1")
    scoap_co_raw:  int = Field(default=0, description="Raw CO: observability cost")

    # Normalized SCOAP scores in [0, 1]
    scoap_cc0: float = Field(default=0.0, ge=0.0, le=1.0)
    scoap_cc1: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="High = hard to activate = likely trojan trigger",
    )
    scoap_co: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="High = hard to observe at outputs = likely trojan payload",
    )

    # Cone of Influence
    coi_input_count:  int       = Field(default=0, description="# primary inputs in backward CoI")
    coi_output_count: int       = Field(default=0, description="# primary outputs in forward CoI")
    coi_inputs:  list[str]      = Field(default_factory=list,
                                        description="Primary input names that can activate this node")
    coi_outputs: list[str]      = Field(default_factory=list,
                                        description="Primary output names this node can drive")

    # Subgraph isolation in [0, 1]; 1.0 = fully isolated
    subgraph_isolation: float   = Field(default=0.0, ge=0.0, le=1.0)

    # Combined algorithmic suspicion score in [0, 1]
    algo_suspicion_score: float = Field(default=0.0, ge=0.0, le=1.0)


class AlgorithmicResult(BaseModel):
    """Result of SCOAP + CoI algorithmic analysis of a circuit graph."""

    node_info: dict[str, NodeAlgorithmicInfo] = Field(
        default_factory=dict,
        description="Per-gate algorithmic info, keyed by gate_name",
    )

    # Graph-level summary
    graph_algo_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of non-I/O nodes with high algorithmic suspicion",
    )
    high_cc1_nodes:         list[str] = Field(default_factory=list,
                                               description="Top-5% CC1 nodes (hard to activate)")
    high_co_nodes:          list[str] = Field(default_factory=list,
                                               description="Top-5% CO nodes (hard to observe)")
    isolated_nodes:         list[str] = Field(default_factory=list,
                                               description="Nodes with subgraph_isolation > 0.7")
    zero_coi_output_nodes:  list[str] = Field(default_factory=list,
                                               description="Nodes that drive zero primary outputs")

    analysis_node_count: int = 0
    analysis_edge_count: int = 0


class TrojanLocation(BaseModel):
    """Detailed location of identified trojan logic in source code.

    Provides exact file and line information for trojan gates,
    enabling precise identification of malicious circuitry.
    """

    node_index: int = Field(description="Index in the circuit graph")
    gate_name: str = Field(description="Name of the gate/instance")
    gate_type: str = Field(description="Type of gate (AND, OR, DFF, etc.)")
    module_name: str = Field(description="Verilog module containing the gate")
    source_file: str | None = Field(
        default=None,
        description="Path to the source Verilog/SystemVerilog file"
    )
    line_number: int | None = Field(
        default=None,
        description="Line number in the source file (1-indexed)"
    )
    column: int | None = Field(
        default=None,
        description="Column number in the source file"
    )
    suspicion_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Combined suspicion score (GNN + algorithmic)",
    )
    detection_method: str = Field(
        default="gnn_attribution",
        description="How this node was identified (gnn_attribution, name_pattern, gnn+algorithmic, etc.)",
    )

    # Algorithmic analysis fields (populated when AlgorithmicAnalyzer runs)
    scoap_cc1: float | None = Field(
        default=None, description="Normalized CC1: high = hard to activate (trojan trigger pattern)",
    )
    scoap_co: float | None = Field(
        default=None, description="Normalized CO: high = hard to observe (trojan payload pattern)",
    )
    coi_outputs: list[str] = Field(
        default_factory=list, description="Primary outputs this node drives",
    )
    algo_suspicion_score: float | None = Field(
        default=None, description="Combined algorithmic suspicion score",
    )

    model_config = {"arbitrary_types_allowed": True}

    def format_location(self) -> str:
        """Format location as 'file:line' string for display."""
        if self.source_file and self.line_number:
            return f"{self.source_file}:{self.line_number}"
        elif self.source_file:
            return self.source_file
        
        return f"module:{self.module_name}"


class ClassificationResult(BaseModel):
    """Holds the classification verdict and supporting data.

    Extended to include detailed trojan locations when a high percentage
    of nodes are identified as suspicious.
    """

    verdict: TrojanVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    trojan_probability: float = Field(ge=0.0, le=1.0)
    gate_suspicion_scores: dict[str, float] = Field(default_factory=dict)
    model_version: str = ""
    architecture: str = ""

    # Extended fields for trojan localization
    trojan_locations: list[TrojanLocation] = Field(
        default_factory=list,
        description="Detailed locations of suspected trojan gates"
    )
    trojan_node_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Percentage of nodes identified as trojan"
    )
    trojan_modules: list[str] = Field(
        default_factory=list,
        description="List of module names containing trojan logic"
    )
    high_risk: bool = Field(
        default=False,
        description="True if trojan percentage exceeds threshold"
    )
    risk_threshold: float = Field(
        default=5.0,
        description="Threshold percentage for high-risk classification"
    )

    # Ensemble fields
    ensemble_used: bool = Field(
        default=False,
        description="Whether ensemble classification was used"
    )
    ensemble_models_run: list[str] = Field(
        default_factory=list,
        description="List of architecture names that contributed to this result"
    )
    per_model_results: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Per-model graph-level scores: {arch: {trojan_probability, confidence}}"
    )
    model_agreement: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Agreement level across ensemble models (1.0 = unanimous)",
    )

    # Algorithmic analysis result (None if skipped)
    algorithmic_result: AlgorithmicResult | None = Field(
        default=None,
        description="SCOAP + CoI analysis; None if algorithmic analysis was not run",
    )

    # Golden reference comparison fields
    golden_diff_used: bool = Field(
        default=False,
        description="Whether a golden reference comparison was performed",
    )
    golden_diff_node_count: int = Field(
        default=0,
        description="Number of nodes found exclusively in the suspect design vs golden",
    )

    def get_top_suspicious(self, n: int = 10) -> list[TrojanLocation]:
        """Get top N most suspicious locations sorted by score."""
        return sorted(
            self.trojan_locations,
            key=lambda x: x.suspicion_score,
            reverse=True
        )[:n]

    def get_locations_by_module(self) -> dict[str, list[TrojanLocation]]:
        """Group trojan locations by their containing module."""
        by_module: dict[str, list[TrojanLocation]] = {}
        for loc in self.trojan_locations:
            if loc.module_name not in by_module:
                by_module[loc.module_name] = []
            by_module[loc.module_name].append(loc)
    
        return by_module

    def get_locations_by_file(self) -> dict[str, list[TrojanLocation]]:
        """Group trojan locations by their source file."""
        by_file: dict[str, list[TrojanLocation]] = {}
        for loc in self.trojan_locations:
            file_key = loc.source_file or "unknown"
            if file_key not in by_file:
                by_file[file_key] = []
    
            by_file[file_key].append(loc)
    
        return by_file

    def format_report(self) -> str:
        """Generate a human-readable report of trojan locations."""
        lines = []
        lines.append(f"Verdict: {self.verdict.value.upper()}")
        lines.append(f"Confidence: {self.confidence:.2%}")
        lines.append(f"Trojan Probability: {self.trojan_probability:.2%}")
        lines.append(f"Trojan Node Percentage: {self.trojan_node_percentage:.2f}%")
        lines.append(f"High Risk: {'YES' if self.high_risk else 'NO'}")
        lines.append("")

        if self.trojan_modules:
            lines.append("Affected Modules:")
            for mod in self.trojan_modules:
                lines.append(f"  - {mod}")
    
            lines.append("")

        if self.trojan_locations:
            lines.append("Top Suspicious Gates:")
            for loc in self.get_top_suspicious(10):
                location_str = loc.format_location()
                lines.append(
                    f"  {loc.gate_name} ({loc.gate_type}) "
                    f"[score={loc.suspicion_score:.4f}] "
                    f"@ {location_str}"
                )

        return "\n".join(lines)
