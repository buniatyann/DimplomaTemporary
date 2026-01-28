"""Data models for analysis reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportSection(BaseModel):
    """A logical section of the analysis report."""

    title: str
    content: dict[str, Any] = Field(default_factory=dict)
    subsections: list[ReportSection] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Aggregates all information from the pipeline for export."""

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    file_info: dict[str, Any] = Field(default_factory=dict)
    processing_summary: list[dict[str, Any]] = Field(default_factory=list)
    parsing_details: dict[str, Any] = Field(default_factory=dict)
    synthesis_statistics: dict[str, Any] = Field(default_factory=dict)
    graph_properties: dict[str, Any] = Field(default_factory=dict)
    classification_results: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
