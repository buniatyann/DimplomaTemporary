"""TextExporter for plain text report output."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.analysis_summarizer.models import AnalysisReport


class TextExporter:
    """Creates plain text reports suitable for terminal output and logs."""

    def export(self, report: AnalysisReport, output_dir: Path) -> Path:
        """Export the report as a plain text file.

        The filename is derived from the analysed file (e.g. c7552_report.txt).
        Falls back to ``trojan_analysis_report.txt`` when no file info is
        available.

        Args:
            report: Compiled AnalysisReport.
            output_dir: Directory for the output file.

        Returns:
            Path to the generated text file.
        """
        file_paths = report.file_info.get("file_paths", [])
        if file_paths:
            stem = Path(file_paths[0]).stem
            filename = f"{stem}_report.txt"
        else:
            filename = "trojan_analysis_report.txt"

        output_path = output_dir / filename
        lines = self._render(report)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

    def render_to_string(self, report: AnalysisReport) -> str:
        """Render the report as a string (for terminal / log viewer display)."""
        return "\n".join(self._render(report))

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _render(self, report: AnalysisReport) -> list[str]:
        """Build the text lines for the report."""
        lines: list[str] = []
        sep = "=" * 72

        # ── Header ──
        lines.append(sep)
        lines.append("  HARDWARE TROJAN DETECTION REPORT")
        lines.append(sep)
        lines.append(f"  Generated: {report.timestamp}")
        lines.append("")

        # ── File Information ──
        lines.append(self._section_header("File Information"))
        fi = report.file_info
        file_paths = fi.get("file_paths", [])
        if file_paths:
            for fp in file_paths:
                lines.append(f"  File: {fp}")
        else:
            lines.append("  File: (unknown)")
       
        lines.append(f"  Total size: {fi.get('total_size', 0)} bytes")
        lines.append("")

        # ── Timing ──
        lines.append(self._section_header("Timing"))
        total_dur = 0.0
        for stage in report.processing_summary:
            dur = stage.get("duration")
            dur_str = f"{dur:.4f}s" if dur is not None else "N/A"
            status = stage.get("status", "N/A")
            lines.append(f"  {stage['stage']:<28} {status:<10} {dur_str}")
            if dur is not None:
                total_dur += dur
       
        lines.append(f"  {'\u2500' * 28} {'\u2500' * 10} {'\u2500' * 8}")
        lines.append(f"  {'Total':<28} {'':10} {total_dur:.4f}s")
        lines.append("")

        # ── Syntax Errors ──
        syntax_errors = report.syntax_errors
        syntax_stage = self._find_stage(report, "syntax_parser")
        syntax_warnings = self._stage_warnings(report, "syntax_parser")

        lines.append(self._section_header("Syntax Analysis"))
        if not syntax_errors and not syntax_warnings:
            lines.append("  No syntax errors.")
        else:
            if syntax_errors:
                lines.append(f"  {len(syntax_errors)} error(s):")
                for err in syntax_errors:
                    loc = self._format_error_location(err)
                    lines.append(f"    [ERROR] {loc}{err['message']}")
            if syntax_warnings:
                lines.append(f"  {len(syntax_warnings)} warning(s):")
                for w in syntax_warnings:
                    lines.append(f"    [WARN]  {w}")
       
       
        if syntax_stage and syntax_stage.get("status") == "failed":
            lines.append("  ** Syntax parsing FAILED — subsequent stages skipped **")
       
        lines.append("")

        # ── Synthesis Errors ──
        synthesis_errors = report.synthesis_errors
        synth_stage = self._find_stage(report, "netlist_synthesizer")
        synth_warnings = self._stage_warnings(report, "netlist_synthesizer")

        lines.append(self._section_header("Synthesis"))
        if not synthesis_errors and not synth_warnings:
            lines.append("  No synthesis errors.")
        else:
            if synthesis_errors:
                lines.append(f"  {len(synthesis_errors)} error(s):")
                for err in synthesis_errors:
                    lines.append(f"    [ERROR] {err['message']}")
                    yosys_out = err.get("yosys_output", "")
                    if yosys_out:
                        for out_line in yosys_out.strip().splitlines()[-10:]:
                            lines.append(f"            {out_line.strip()}")
            if synth_warnings:
                lines.append(f"  {len(synth_warnings)} warning(s):")
                for w in synth_warnings:
                    lines.append(f"    [WARN]  {w}")
       
        if synth_stage and synth_stage.get("status") == "failed":
            lines.append("  ** Synthesis FAILED — subsequent stages skipped **")
       
        lines.append("")

        # ── Classification Results ──
        cr = report.classification_results
        if cr.get("verdict") is not None:
            lines.append(self._section_header("Classification Results"))
            verdict = str(cr.get("verdict", "N/A")).upper()
            confidence = cr.get("confidence", 0.0)
            lines.append(f"  Verdict:           {verdict}")
            lines.append(f"  Confidence:        {confidence:.4f}")
            lines.append(f"  Trojan probability:{cr.get('trojan_probability', 0.0):.4f}")
            lines.append(
                f"  Model:             {cr.get('architecture', 'N/A')} "
                f"v{cr.get('model_version', 'N/A')}"
            )
       
            dur = cr.get("inference_duration")
            if dur is not None:
                lines.append(f"  Inference time:    {dur:.4f}s")
       
            lines.append("")

            # ── Trojan Locations ──
            trojan_modules = cr.get("trojan_modules", [])
            locations_by_module = cr.get("trojan_locations_by_module", {})
            top_gates = cr.get("top_suspicious_gates", [])
            node_pct = cr.get("trojan_node_percentage", 0.0)
            high_risk = cr.get("high_risk", False)

            if verdict == "INFECTED" or high_risk or top_gates:
                lines.append(self._section_header("Trojan Locations"))
                if high_risk:
                    lines.append(
                        f"  *** HIGH RISK: {node_pct:.2f}% of nodes flagged as suspicious ***"
                    )
       
                    lines.append("")

                if trojan_modules:
                    lines.append(f"  Affected modules: {', '.join(trojan_modules)}")
                    lines.append("")

                if locations_by_module:
                    for module_name, gates in locations_by_module.items():
                        lines.append(f"  Module: {module_name}")
                        for gate in gates:
                            loc = ""
                            if gate.get("file") and gate.get("line"):
                                loc = f"{gate['file']}:{gate['line']} "
                            elif gate.get("file"):
                                loc = f"{gate['file']} "
       
                            score = gate.get("score", 0.0)
                            gate_name = gate.get("gate", "unknown")
                            gate_type = gate.get("type", "")
                            type_str = f" ({gate_type})" if gate_type else ""
                            lines.append(
                                f"    {loc}{gate_name}{type_str}  "
                                f"score={score:.4f}"
                            )
       
                        lines.append("")
                elif top_gates:
                    lines.append("  Suspicious gates:")
                    for gate in top_gates:
                        loc = ""
                        if gate.get("file") and gate.get("line"):
                            loc = f"{gate['file']}:{gate['line']} "
                        elif gate.get("file"):
                            loc = f"{gate['file']} "
       
                        score = gate.get("score", 0.0)
                        gate_name = gate.get("gate", "unknown")
                        gate_type = gate.get("type", "")
                        module = gate.get("module", "")
                        type_str = f" ({gate_type})" if gate_type else ""
                        mod_str = f" [{module}]" if module else ""
                        lines.append(
                            f"    {loc}{gate_name}{type_str}{mod_str}  "
                            f"score={score:.4f}"
                        )
       
                    lines.append("")
        else:
            lines.append(self._section_header("Classification Results"))
            lines.append("  Classification was not reached (earlier stage failed).")
            lines.append("")

        lines.append(sep)
        return lines

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _section_header(self, title: str) -> str:
        padding = max(60 - len(title), 4)
        return f"--- {title} " + "\u2500" * padding

    @staticmethod
    def _format_error_location(err: dict[str, Any]) -> str:
        """Build a ``file:line:col `` prefix from an error dict."""
        parts: list[str] = []
        if err.get("file_path"):
            parts.append(str(err["file_path"]))
        if err.get("line") is not None:
            parts.append(str(err["line"]))
        if err.get("column") is not None:
            parts.append(str(err["column"]))
        if parts:
            return ":".join(parts) + " "
       
        return ""

    @staticmethod
    def _find_stage(
        report: AnalysisReport, stage_name: str
    ) -> dict[str, Any] | None:
        for s in report.processing_summary:
            if s.get("stage") == stage_name:
                return s
        return None

    @staticmethod
    def _stage_warnings(report: AnalysisReport, stage_name: str) -> list[str]:
        """Filter warnings that belong to a specific stage.

        Warning messages in the report are flat strings without stage metadata,
        so we pull them from the audit trail instead.
        """
        result: list[str] = []
        for entry in report.audit_trail:
            if (
                entry.get("stage") == stage_name
                and entry.get("severity") == "warning"
            ):
                result.append(entry["message"])
       
        return result
