"""DetectionPipeline orchestrator for sequential stage execution."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from backend.core.history import History
from backend.core.outcome import StageOutcome

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]


class DetectionPipeline:
    """Orchestrates the sequential execution of all pipeline stages.

    Manages data flow between modules, handles early termination on
    failures, and ensures the analysis_summarizer receives the History
    object regardless of pipeline outcome.
    """

    STAGE_NAMES = [
        "file_ingestion",
        "syntax_parser",
        "netlist_synthesizer",
        "netlist_graph_builder",
        "trojan_classifier",
        "analysis_summarizer",
    ]

    def __init__(self, progress_callback: ProgressCallback | None = None) -> None:
        self._progress_callback = progress_callback

    def _report_progress(self, stage: str, current: int, total: int) -> None:
        if self._progress_callback:
            self._progress_callback(stage, current, total)

    def run(
        self,
        input_path: Path,
        output_dir: Path | None = None,
        export_formats: list[str] | None = None,
        selected_models: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute the full detection pipeline on a single file or directory.

        Args:
            input_path: Path to a Verilog file or directory of files.
            output_dir: Directory for report output. Defaults to current directory.
            export_formats: List of export formats (json, pdf, text). Defaults to ["json"].
            selected_models: List of model architectures to use for classification
                (e.g. ["gcn"], ["gcn", "gat"], or None for all three).

        Returns:
            Dictionary containing the analysis report and export paths.
        """
        from backend.file_ingestion.collector import FileCollector
        from backend.netlist_graph_builder.builder import NetlistGraphBuilder
        from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer
        from backend.syntax_parser.parser import SyntaxParser
        from backend.trojan_classifier.ensemble import EnsembleClassifier

        if export_formats is None:
            export_formats = ["json"]
        if output_dir is None:
            output_dir = Path(__file__).resolve().parent.parent.parent / "reports"
        
        output_dir.mkdir(parents=True, exist_ok=True)

        history = History()
        total_stages = len(self.STAGE_NAMES)

        # Stage 1: File Ingestion
        self._report_progress("file_ingestion", 1, total_stages)
        collector = FileCollector(history)
        ingestion_outcome = collector.process(input_path)
        if not ingestion_outcome.success:
            history.end_stage("file_ingestion", status="failed")
            return self._finalize(history, output_dir, export_formats)

        # Stage 2: Syntax Parsing
        self._report_progress("syntax_parser", 2, total_stages)
        parser = SyntaxParser(history)
        parse_outcome = parser.process(ingestion_outcome.data)

        # Stage 3: Netlist Synthesis
        self._report_progress("netlist_synthesizer", 3, total_stages)
        synthesizer = NetlistSynthesizer(history)
        if parse_outcome.success:
            synth_outcome = synthesizer.process(parse_outcome.data)
        else:
            # Fallback: bypass pyverilog and run Yosys directly on source files
            history.info("netlist_synthesizer", "Parser failed — falling back to direct Yosys synthesis")
            source_paths = [f.path for f in ingestion_outcome.data.files]
            synth_outcome = synthesizer.process_paths(source_paths)
        if not synth_outcome.success:
            return self._finalize(history, output_dir, export_formats)

        # Stage 4: Graph Building
        self._report_progress("netlist_graph_builder", 4, total_stages)
        graph_builder = NetlistGraphBuilder(history)
        graph_outcome = graph_builder.process(synth_outcome.data)
        if not graph_outcome.success:
            return self._finalize(history, output_dir, export_formats)

        # Stage 5: Trojan Classification (ensemble: GCN → GIN → GAT cascade)
        self._report_progress("trojan_classifier", 5, total_stages)
        classifier = EnsembleClassifier(
            history, selected_models=selected_models,
        )
        classify_outcome = classifier.process(
            graph_outcome.data,
            parsed_modules=parse_outcome.data if parse_outcome.success else None,
        )
        if not classify_outcome.success:
            return self._finalize(history, output_dir, export_formats)

        # Stage 6: Analysis Summary
        self._report_progress("analysis_summarizer", 6, total_stages)
        return self._finalize(history, output_dir, export_formats)

    def _finalize(
        self,
        history: History,
        output_dir: Path,
        export_formats: list[str],
    ) -> dict[str, Any]:
        """Run the analysis summarizer and return results."""
        from backend.analysis_summarizer.summarizer import AnalysisSummarizer

        summarizer = AnalysisSummarizer(history)
        report = summarizer.compile()
        export_paths = summarizer.export(report, output_dir, export_formats)

        return {
            "report": report.to_dict(),
            "export_paths": [str(p) for p in export_paths],
            "history": history.to_dict(),
        }

    def run_batch(
        self,
        input_path: Path,
        output_dir: Path | None = None,
        export_formats: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute the pipeline on all files in a directory.

        Args:
            input_path: Directory containing Verilog files.
            output_dir: Directory for report output.
            export_formats: List of export formats.

        Returns:
            List of result dictionaries, one per processed file.
        """
        from backend.file_ingestion.collector import FileCollector

        if not input_path.is_dir():
            return [self.run(input_path, output_dir, export_formats)]

        history = History()
        collector = FileCollector(history)
        manifest_outcome = collector.process(input_path)

        if not manifest_outcome.success or manifest_outcome.data is None:
            return [{"error": manifest_outcome.error_message}]

        results = []
        manifest = manifest_outcome.data
        for file_entry in manifest.files:
            result = self.run(file_entry.path, output_dir, export_formats)
            results.append(result)

        return results
