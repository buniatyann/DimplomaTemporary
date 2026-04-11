"""Data models for netlist synthesis results."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CellStatistics(BaseModel):
    """Detailed gate counts from synthesis."""

    cell_counts: dict[str, int] = Field(default_factory=dict)
    total_cells: int = 0
    total_wires: int = 0
    total_inputs: int = 0
    total_outputs: int = 0
    module_count: int = 0

    def add_cell(self, cell_type: str, count: int = 1) -> None:
        self.cell_counts[cell_type] = self.cell_counts.get(cell_type, 0) + count
        self.total_cells += count


class SynthesisResult(BaseModel):
    """Packages synthesis outputs for downstream processing."""

    json_netlist: dict[str, Any] = Field(default_factory=dict)
    cell_statistics: CellStatistics = Field(default_factory=CellStatistics)
    module_hierarchy: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    # Maps the temp-dir file name Yosys saw (e.g. "input_0_aes_128.v") back to
    # the absolute path of the original user source file. Populated by
    # YosysRunner when it copies inputs into the temp workspace; used by the
    # graph builder to resolve Yosys `src` attributes to user source files.
    temp_to_original: dict[str, str] = Field(default_factory=dict)
