"""TextExporter for plain text report output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from analysis_summarizer.models import AnalysisReport


class TextExporter:
    """Creates plain text reports suitable for terminal output and logs."""

    def export(self, report: AnalysisReport, output_dir: Path) -> Path:
        """Export the report as a plain text file.

        Args:
            report: Compiled AnalysisReport.
            output_dir: Directory for the output file.

        Returns:
            Path to the generated text file.
        """
        output_path = output_dir / "trojan_analysis_report.txt"
        lines = self._render(report)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

    def render_to_string(self, report: AnalysisReport) -> str:
        """Render the report as a string (for terminal display)."""
        return "\n".join(self._render(report))

    def _render(self, report: AnalysisReport) -> list[str]:
        """Build the text lines for the report."""
        lines: list[str] = []
        sep = "=" * 72

        lines.append(sep)
        lines.append("  HARDWARE TROJAN DETECTION REPORT")
        lines.append(sep)
        lines.append(f"  Generated: {report.timestamp}")
        lines.append("")

        # File Information
        lines.append(self._section_header("File Information"))
        fi = report.file_info
        lines.append(f"  Total files analyzed: {fi.get('total_files', 0)}")
        lines.append(f"  Verilog files: {fi.get('verilog_files', 0)}")
        lines.append(f"  SystemVerilog files: {fi.get('systemverilog_files', 0)}")
        lines.append(f"  Total size: {fi.get('total_size', 0)} bytes")
        for fp in fi.get("file_paths", []):
            lines.append(f"    - {fp}")
        lines.append("")

        # Processing Summary
        lines.append(self._section_header("Processing Summary"))
        for stage in report.processing_summary:
            dur = stage.get("duration")
            dur_str = f"{dur:.4f}s" if dur is not None else "N/A"
            lines.append(
                f"  [{stage['status']:>10}] {stage['stage']:<25} "
                f"({dur_str}, {stage.get('warning_count', 0)} warnings, "
                f"{stage.get('error_count', 0)} errors)"
            )
        lines.append("")

        # Parsing Details
        pd = report.parsing_details
        if pd.get("module_count") is not None:
            lines.append(self._section_header("Parsing Details"))
            lines.append(f"  Modules parsed: {pd.get('module_count', 0)}")
            lines.append(f"  Total gates: {pd.get('total_gates', 0)}")
            lines.append(f"  Total wires: {pd.get('total_wires', 0)}")
            dur = pd.get("parse_duration")
            if dur is not None:
                lines.append(f"  Parse duration: {dur:.4f}s")
            lines.append("")

        # Synthesis Statistics
        ss = report.synthesis_statistics
        if ss.get("total_cells") is not None:
            lines.append(self._section_header("Synthesis Statistics"))
            lines.append(f"  Total cells: {ss.get('total_cells', 0)}")
            lines.append(f"  Total wires: {ss.get('total_wires', 0)}")
            lines.append(f"  Total inputs: {ss.get('total_inputs', 0)}")
            lines.append(f"  Total outputs: {ss.get('total_outputs', 0)}")
            cell_counts = ss.get("cell_counts", {})
            if cell_counts:
                lines.append("  Cell breakdown:")
                for ctype, count in sorted(cell_counts.items()):
                    lines.append(f"    {ctype}: {count}")
            lines.append("")

        # Graph Properties
        gp = report.graph_properties
        if gp.get("node_count", 0) > 0:
            lines.append(self._section_header("Graph Properties"))
            lines.append(f"  Nodes: {gp.get('node_count', 0)}")
            lines.append(f"  Edges: {gp.get('edge_count', 0)}")
            lines.append(f"  Average degree: {gp.get('average_degree', 0):.4f}")
            lines.append(f"  Feature dimensionality: {gp.get('feature_dim', 0)}")
            unknown = gp.get("unknown_gate_types", [])
            if unknown:
                lines.append(f"  Unknown gate types: {', '.join(unknown)}")
            lines.append("")

        # Classification Results
        cr = report.classification_results
        if cr.get("verdict") is not None:
            lines.append(self._section_header("Classification Results"))
            verdict = cr.get("verdict", "N/A").upper()
            lines.append(f"  Verdict: {verdict}")
            lines.append(f"  Confidence: {cr.get('confidence', 0):.4f}")
            lines.append(f"  Trojan probability: {cr.get('trojan_probability', 0):.4f}")
            lines.append(f"  Model: {cr.get('architecture', 'N/A')} v{cr.get('model_version', 'N/A')}")
            lines.append(f"  Device: {cr.get('device', 'N/A')}")
            suspicious = cr.get("top_suspicious_gates", [])
            if suspicious:
                lines.append("  Top suspicious gates:")
                for entry in suspicious:
                    lines.append(f"    {entry['gate']}: {entry['score']:.6f}")
            lines.append("")

        # Warnings
        if report.warnings:
            lines.append(self._section_header("Warnings"))
            for w in report.warnings:
                lines.append(f"  - {w}")
            lines.append("")

        # Errors
        if report.errors:
            lines.append(self._section_header("Errors"))
            for e in report.errors:
                lines.append(f"  - {e}")
            lines.append("")

        lines.append(sep)
        return lines

    def _section_header(self, title: str) -> str:
        return f"--- {title} {'─' * (60 - len(title))}"
