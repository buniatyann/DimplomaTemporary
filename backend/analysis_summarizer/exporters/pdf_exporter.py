"""PdfExporter for formatted PDF report output using ReportLab."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.analysis_summarizer.models import AnalysisReport

logger = logging.getLogger(__name__)


class PdfExporter:
    """Produces formatted PDF documents with tables and styled text."""

    def export(self, report: AnalysisReport, output_dir: Path) -> Path:
        """Export the report as a PDF file.

        Args:
            report: Compiled AnalysisReport.
            output_dir: Directory for the output file.

        Returns:
            Path to the generated PDF file.
        """
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        output_path = output_dir / "trojan_analysis_report.pdf"

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=20 * mm,
            leftMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontSize=18,
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            "ReportHeading",
            parent=styles["Heading2"],
            fontSize=13,
            spaceBefore=12,
            spaceAfter=6,
        )
        body_style = styles["BodyText"]

        elements: list[Any] = []

        # Title
        elements.append(Paragraph("Hardware Trojan Detection Report", title_style))
        elements.append(Paragraph(f"Generated: {report.timestamp}", body_style))
        elements.append(Spacer(1, 10 * mm))

        # File Information
        elements.append(Paragraph("File Information", heading_style))
        fi = report.file_info
        fi_data = [
            ["Total Files", str(fi.get("total_files", 0))],
            ["Verilog Files", str(fi.get("verilog_files", 0))],
            ["SystemVerilog Files", str(fi.get("systemverilog_files", 0))],
            ["Total Size (bytes)", str(fi.get("total_size", 0))],
        ]

        elements.append(self._make_table(fi_data))
        elements.append(Spacer(1, 5 * mm))

        # Processing Summary
        elements.append(Paragraph("Processing Summary", heading_style))
        ps_header = ["Stage", "Status", "Duration", "Warnings", "Errors"]
        ps_data = [ps_header]
        for stage in report.processing_summary:
            dur = stage.get("duration")
            dur_str = f"{dur:.4f}s" if dur is not None else "N/A"
            ps_data.append([
                stage["stage"],
                stage["status"],
                dur_str,
                str(stage.get("warning_count", 0)),
                str(stage.get("error_count", 0)),
            ])
        
        elements.append(self._make_table(ps_data, header=True))
        elements.append(Spacer(1, 5 * mm))

        # Parsing Details
        pd = report.parsing_details
        if pd.get("module_count") is not None:
            elements.append(Paragraph("Parsing Details", heading_style))
            pd_data = [
                ["Modules Parsed", str(pd.get("module_count", 0))],
                ["Total Gates", str(pd.get("total_gates", 0))],
                ["Total Wires", str(pd.get("total_wires", 0))],
            ]
        
            dur = pd.get("parse_duration")
            if dur is not None:
                pd_data.append(["Parse Duration", f"{dur:.4f}s"])
        
            elements.append(self._make_table(pd_data))
            elements.append(Spacer(1, 5 * mm))

        # Synthesis Statistics
        ss = report.synthesis_statistics
        if ss.get("total_cells") is not None:
            elements.append(Paragraph("Synthesis Statistics", heading_style))
            ss_data = [
                ["Total Cells", str(ss.get("total_cells", 0))],
                ["Total Wires", str(ss.get("total_wires", 0))],
                ["Total Inputs", str(ss.get("total_inputs", 0))],
                ["Total Outputs", str(ss.get("total_outputs", 0))],
            ]
        
            elements.append(self._make_table(ss_data))

            cell_counts = ss.get("cell_counts", {})
            if cell_counts:
                elements.append(Spacer(1, 3 * mm))
                elements.append(Paragraph("Cell Breakdown", body_style))
                cc_header = ["Cell Type", "Count"]
                cc_data = [cc_header] + [
                    [ctype, str(count)]
                    for ctype, count in sorted(cell_counts.items())
                ]
        
                elements.append(self._make_table(cc_data, header=True))
        
            elements.append(Spacer(1, 5 * mm))

        # Graph Properties
        gp = report.graph_properties
        if gp.get("node_count", 0) > 0:
            elements.append(Paragraph("Graph Properties", heading_style))
            gp_data = [
                ["Nodes", str(gp.get("node_count", 0))],
                ["Edges", str(gp.get("edge_count", 0))],
                ["Average Degree", f"{gp.get('average_degree', 0):.4f}"],
                ["Feature Dimensionality", str(gp.get("feature_dim", 0))],
            ]
        
            elements.append(self._make_table(gp_data))
            elements.append(Spacer(1, 5 * mm))

        # Classification Results
        cr = report.classification_results
        if cr.get("verdict") is not None:
            elements.append(Paragraph("Classification Results", heading_style))
            cr_data = [
                ["Verdict", cr.get("verdict", "N/A").upper()],
                ["Confidence", f"{cr.get('confidence', 0):.4f}"],
                ["Trojan Probability", f"{cr.get('trojan_probability', 0):.4f}"],
                ["Model", f"{cr.get('architecture', 'N/A')} v{cr.get('model_version', 'N/A')}"],
                ["Device", str(cr.get("device", "N/A"))],
            ]
        
            elements.append(self._make_table(cr_data))

            suspicious = cr.get("top_suspicious_gates", [])
            if suspicious:
                elements.append(Spacer(1, 3 * mm))
                elements.append(Paragraph("Top Suspicious Gates", body_style))
                sg_header = ["Gate", "Suspicion Score"]
                sg_data = [sg_header] + [
                    [entry["gate"], f"{entry['score']:.6f}"]
                    for entry in suspicious
                ]
        
                elements.append(self._make_table(sg_data, header=True))
        
            elements.append(Spacer(1, 5 * mm))

        # Warnings
        if report.warnings:
            elements.append(Paragraph("Warnings", heading_style))
            for w in report.warnings:
                elements.append(Paragraph(f"- {w}", body_style))
        
            elements.append(Spacer(1, 5 * mm))

        # Errors
        if report.errors:
            elements.append(Paragraph("Errors", heading_style))
            for e in report.errors:
                elements.append(Paragraph(f"- {e}", body_style))

        doc.build(elements)
        return output_path

    def _make_table(
        self, data: list[list[str]], header: bool = False
    ) -> Any:
        """Create a formatted ReportLab table."""
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle

        table = Table(data)
        style_commands: list[Any] = [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]

        if header:
            style_commands.extend([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ])

        table.setStyle(TableStyle(style_commands))
        return table
