"""JsonExporter for machine-readable JSON report output."""

from __future__ import annotations

import json
from pathlib import Path

from backend.analysis_summarizer.models import AnalysisReport


class JsonExporter:
    """Generates machine-readable JSON reports."""

    def export(self, report: AnalysisReport, output_dir: Path) -> Path:
        """Export the report as a JSON file.

        Args:
            report: Compiled AnalysisReport.
            output_dir: Directory for the output file.

        Returns:
            Path to the generated JSON file.
        """
        output_path = output_dir / "trojan_analysis_report.json"
        data = report.to_dict()

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        return output_path
