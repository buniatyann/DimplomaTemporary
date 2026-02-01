"""AnalysisSummarizer facade for compiling reports from History."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.analysis_summarizer.models import AnalysisReport, ReportSection
from backend.core.history import History

logger = logging.getLogger(__name__)

STAGE = "analysis_summarizer"


class AnalysisSummarizer:
    """Aggregates results from all pipeline stages via History and generates reports."""

    def __init__(self, history: History) -> None:
        self._history = history

    def compile(self) -> AnalysisReport:
        """Compile a comprehensive analysis report from History.

        Returns:
            AnalysisReport with all available pipeline data.
        """
        self._history.begin_stage(STAGE)

        report = AnalysisReport()

        # File information
        report.file_info = self._extract_file_info()

        # Processing summary per stage
        report.processing_summary = self._extract_processing_summary()

        # Parsing details
        report.parsing_details = self._extract_parsing_details()

        # Synthesis statistics
        report.synthesis_statistics = self._extract_synthesis_statistics()

        # Graph properties
        report.graph_properties = self._extract_graph_properties()

        # Classification results
        report.classification_results = self._extract_classification_results()

        # Warnings and errors
        report.warnings = [e.message for e in self._history.get_warnings()]
        report.errors = [e.message for e in self._history.get_errors()]

        # Structured syntax and synthesis errors (with line info)
        report.syntax_errors = self._extract_syntax_errors()
        report.synthesis_errors = self._extract_synthesis_errors()

        # Audit trail
        report.audit_trail = [e.to_dict() for e in self._history.entries]

        # Build sections
        report.sections = self._build_sections(report)

        self._history.info(STAGE, "Report compilation complete")
        self._history.end_stage(STAGE, status="completed")

        return report

    def export(
        self,
        report: AnalysisReport,
        output_dir: Path,
        formats: list[str],
    ) -> list[Path]:
        """Export the report to requested formats.

        Args:
            report: Compiled AnalysisReport.
            output_dir: Directory for output files.
            formats: List of format strings ("json", "pdf", "text").

        Returns:
            List of paths to exported files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for fmt in formats:
            if fmt == "json":
                from backend.analysis_summarizer.exporters.json_exporter import (
                    JsonExporter,
                )
              
                path = JsonExporter().export(report, output_dir)
                paths.append(path)
            elif fmt == "pdf":
                from backend.analysis_summarizer.exporters.pdf_exporter import (
                    PdfExporter,
                )
              
                path = PdfExporter().export(report, output_dir)
                paths.append(path)
            elif fmt == "text":
                from backend.analysis_summarizer.exporters.text_exporter import (
                    TextExporter,
                )
              
                path = TextExporter().export(report, output_dir)
                paths.append(path)
            else:
                self._history.warning(STAGE, f"Unknown export format: {fmt}")

        return paths

    def _extract_file_info(self) -> dict[str, Any]:
        """Extract file metadata from History."""
        return {
            "file_paths": self._history.get_record("file_ingestion", "file_paths", []),
            "total_files": self._history.get_record("file_ingestion", "total_files", 0),
            "verilog_files": self._history.get_record("file_ingestion", "verilog_files", 0),
            "systemverilog_files": self._history.get_record(
                "file_ingestion", "systemverilog_files", 0
            ),
            "total_size": self._history.get_record("file_ingestion", "total_size", 0),
        }

    def _extract_processing_summary(self) -> list[dict[str, Any]]:
        """Extract per-stage processing summary from History."""
        summary = []
        for stage_name in self._history.stage_order:
            stage = self._history.stages.get(stage_name)
            if stage is None:
                continue
            
            summary.append({
                "stage": stage_name,
                "status": stage.status,
                "duration": stage.duration,
                "warning_count": len(stage.warnings),
                "error_count": len(stage.errors),
            })

        return summary

    def _extract_parsing_details(self) -> dict[str, Any]:
        """Extract parsing metrics from History."""
        return {
            "parse_duration": self._history.get_record("syntax_parser", "parse_duration"),
            "module_count": self._history.get_record("syntax_parser", "module_count"),
            "total_gates": self._history.get_record("syntax_parser", "total_gates"),
            "total_wires": self._history.get_record("syntax_parser", "total_wires"),
            "module_names": self._history.get_record("syntax_parser", "module_names", []),
        }

    def _extract_synthesis_statistics(self) -> dict[str, Any]:
        """Extract synthesis metrics from History."""
        return {
            "synthesis_duration": self._history.get_record(
                "netlist_synthesizer", "synthesis_duration"
            ),
            "total_cells": self._history.get_record("netlist_synthesizer", "total_cells"),
            "cell_counts": self._history.get_record("netlist_synthesizer", "cell_counts", {}),
            "total_wires": self._history.get_record("netlist_synthesizer", "total_wires"),
            "total_inputs": self._history.get_record("netlist_synthesizer", "total_inputs"),
            "total_outputs": self._history.get_record("netlist_synthesizer", "total_outputs"),
            "module_count": self._history.get_record("netlist_synthesizer", "module_count"),
            "module_hierarchy": self._history.get_record(
                "netlist_synthesizer", "module_hierarchy", []
            ),
            "warning_count": self._history.get_record("netlist_synthesizer", "warning_count"),
        }

    def _extract_graph_properties(self) -> dict[str, Any]:
        """Extract graph construction metrics from History."""
        node_count = self._history.get_record("netlist_graph_builder", "node_count", 0)
        edge_count = self._history.get_record("netlist_graph_builder", "edge_count", 0)
        avg_degree = (2 * edge_count / node_count) if node_count > 0 else 0

        return {
            "node_count": node_count,
            "edge_count": edge_count,
            "average_degree": round(avg_degree, 4),
            "construction_duration": self._history.get_record(
                "netlist_graph_builder", "construction_duration"
            ),
            "vocabulary_size": self._history.get_record(
                "netlist_graph_builder", "vocabulary_size"
            ),
            "feature_dim": self._history.get_record("netlist_graph_builder", "feature_dim"),
            "unknown_gate_types": self._history.get_record(
                "netlist_graph_builder", "unknown_gate_types", []
            ),
        }

    def _extract_classification_results(self) -> dict[str, Any]:
        """Extract classification data from History including trojan locations."""
        return {
            "verdict": self._history.get_record("trojan_classifier", "verdict"),
            "confidence": self._history.get_record("trojan_classifier", "confidence"),
            "trojan_probability": self._history.get_record(
                "trojan_classifier", "trojan_probability"
            ),
            "model_version": self._history.get_record("trojan_classifier", "model_version"),
            "architecture": self._history.get_record("trojan_classifier", "architecture"),
            "inference_duration": self._history.get_record(
                "trojan_classifier", "inference_duration"
            ),
            "device": self._history.get_record("trojan_classifier", "device"),
            "top_suspicious_gates": self._history.get_record(
                "trojan_classifier", "top_suspicious_gates", []
            ),
            # Extended trojan localization fields
            "trojan_node_percentage": self._history.get_record(
                "trojan_classifier", "trojan_node_percentage", 0.0
            ),
            "high_risk": self._history.get_record("trojan_classifier", "high_risk", False),
            "trojan_modules": self._history.get_record(
                "trojan_classifier", "trojan_modules", []
            ),
            "trojan_locations_by_module": self._history.get_record(
                "trojan_classifier", "trojan_locations_by_module", {}
            ),
        }

    def _build_sections(self, report: AnalysisReport) -> list[ReportSection]:
        """Build structured report sections."""
        sections = [
            ReportSection(title="File Information", content=report.file_info),
            ReportSection(
                title="Processing Summary",
                content={"stages": report.processing_summary},
            ),
            ReportSection(title="Parsing Details", content=report.parsing_details),
            ReportSection(
                title="Synthesis Statistics",
                content=report.synthesis_statistics,
            ),
            ReportSection(title="Graph Properties", content=report.graph_properties),
            ReportSection(
                title="Classification Results",
                content=report.classification_results,
            ),
        ]

        # Add trojan locations section if high risk or infected
        cr = report.classification_results
        if cr.get("high_risk") or cr.get("verdict") == "infected":
            trojan_section = self._build_trojan_locations_section(cr)
            sections.append(trojan_section)

        if report.warnings:
            sections.append(
                ReportSection(
                    title="Warnings",
                    content={"warnings": report.warnings},
                )
            )
        if report.errors:
            sections.append(
                ReportSection(
                    title="Errors",
                    content={"errors": report.errors},
                )
            )

        return sections

    def _extract_syntax_errors(self) -> list[dict[str, Any]]:
        """Extract structured syntax errors with line/column info from History."""
        from backend.core.history import Severity

        errors: list[dict[str, Any]] = []
        for entry in self._history.entries:
            if entry.stage != "syntax_parser":
                continue
            if entry.severity not in (Severity.ERROR, Severity.CRITICAL):
                continue
            
            err: dict[str, Any] = {"message": entry.message}
            if entry.data:
                if "file_path" in entry.data:
                    err["file_path"] = entry.data["file_path"]
                if "line" in entry.data:
                    err["line"] = entry.data["line"]
                if "column" in entry.data:
                    err["column"] = entry.data["column"]
            
            errors.append(err)
        
        return errors

    def _extract_synthesis_errors(self) -> list[dict[str, Any]]:
        """Extract structured synthesis errors from History."""
        from backend.core.history import Severity

        errors: list[dict[str, Any]] = []
        for entry in self._history.entries:
            if entry.stage != "netlist_synthesizer":
                continue
            if entry.severity not in (Severity.ERROR, Severity.CRITICAL):
                continue
        
            err: dict[str, Any] = {"message": entry.message}
            if entry.data and "yosys_output" in entry.data:
                err["yosys_output"] = entry.data["yosys_output"]
        
            errors.append(err)
        
        return errors

    def _build_trojan_locations_section(
        self, classification_results: dict[str, Any]
    ) -> ReportSection:
        """Build a detailed trojan locations section for the report."""
        content: dict[str, Any] = {
            "high_risk_alert": classification_results.get("high_risk", False),
            "trojan_node_percentage": classification_results.get("trojan_node_percentage", 0.0),
            "affected_modules": classification_results.get("trojan_modules", []),
        }

        # Format top suspicious gates with file:line locations
        top_gates = classification_results.get("top_suspicious_gates", [])
        formatted_locations = []
        for gate in top_gates:
            location_str = ""
            if gate.get("file") and gate.get("line"):
                location_str = f"{gate['file']}:{gate['line']}"
            elif gate.get("file"):
                location_str = gate["file"]
            elif gate.get("module"):
                location_str = f"module:{gate['module']}"

            formatted_locations.append({
                "gate_name": gate.get("gate", "unknown"),
                "gate_type": gate.get("type", "unknown"),
                "module": gate.get("module", "unknown"),
                "suspicion_score": gate.get("score", 0.0),
                "location": location_str,
            })

        content["suspicious_locations"] = formatted_locations

        # Organize by module for structured view
        by_module = classification_results.get("trojan_locations_by_module", {})
        content["locations_by_module"] = by_module

        return ReportSection(
            title="Trojan Locations",
            content=content,
        )
