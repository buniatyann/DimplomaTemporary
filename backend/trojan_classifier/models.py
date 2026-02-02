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
        description="GNN-computed suspicion score"
    )
    detection_method: str = Field(
        default="gnn_attribution",
        description="How this node was identified (gnn_attribution, name_pattern, structural)"
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
        description="Agreement level across ensemble models (1.0 = unanimous)"
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
