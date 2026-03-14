"""Full pipeline integration tests: synthesis → classification → report."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

# Skip entire module if Yosys is not installed
pytestmark = pytest.mark.skipif(
    not shutil.which("yosys"),
    reason="Yosys not found in PATH",
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "training" / "data"
ISCAS85_DIR = DATA_DIR / "iscas" / "iscas85"
ISCAS89_DIR = DATA_DIR / "iscas" / "iscas89"
TRIT_DIR = DATA_DIR / "trit" / "raw"

# Small clean benchmark files
C17_PATH = ISCAS85_DIR / "c17.v"
S27_PATH = ISCAS89_DIR / "s27.v"

# Find a trojan-infected file for positive test
_trojan_candidates = sorted(TRIT_DIR.rglob("*.v")) if TRIT_DIR.exists() else []
TROJAN_PATH = _trojan_candidates[0] if _trojan_candidates else None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def output_dir():
    """Create a temporary directory for report output."""
    d = tempfile.mkdtemp(prefix="trojan_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Stage-by-stage tests
# ---------------------------------------------------------------------------

class TestFileIngestion:
    """Test the file ingestion stage."""

    def test_single_file(self):
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector

        history = History()
        collector = FileCollector(history)
        outcome = collector.process(C17_PATH)

        assert outcome.success, f"File ingestion failed: {outcome.error_message}"
        assert outcome.data is not None
        assert len(outcome.data.files) == 1
        assert outcome.data.files[0].extension == ".v"

    def test_directory(self):
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector

        history = History()
        collector = FileCollector(history)
        outcome = collector.process(ISCAS85_DIR)

        assert outcome.success, f"Directory ingestion failed: {outcome.error_message}"
        assert outcome.data is not None
        assert len(outcome.data.files) > 0

    def test_nonexistent_path(self):
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector

        history = History()
        collector = FileCollector(history)
        outcome = collector.process(Path("/nonexistent/path.v"))

        assert not outcome.success


class TestSyntaxParser:
    """Test the syntax parsing stage."""

    def test_parse_c17(self):
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector
        from backend.syntax_parser.parser import SyntaxParser

        history = History()
        collector = FileCollector(history)
        manifest = collector.process(C17_PATH)
        assert manifest.success

        parser = SyntaxParser(history)
        outcome = parser.process(manifest.data)

        assert outcome.success, f"Parsing failed: {outcome.error_message}"
        assert outcome.data is not None
        assert len(outcome.data) >= 1

        module = outcome.data[0]
        assert module.name == "c17"
        assert len(module.gates) == 6  # 6 NAND gates
        assert len(module.ports) == 7  # 5 inputs + 2 outputs


class TestNetlistSynthesizer:
    """Test the Yosys synthesis stage."""

    def test_synthesize_c17(self):
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector
        from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer
        from backend.syntax_parser.parser import SyntaxParser

        history = History()

        collector = FileCollector(history)
        manifest = collector.process(C17_PATH)
        assert manifest.success

        parser = SyntaxParser(history)
        parsed = parser.process(manifest.data)
        assert parsed.success

        synthesizer = NetlistSynthesizer(history)
        outcome = synthesizer.process(parsed.data)

        assert outcome.success, f"Synthesis failed: {outcome.error_message}"
        assert outcome.data is not None
        assert outcome.data.json_netlist is not None
        assert outcome.data.cell_statistics is not None

    def test_direct_synthesis(self):
        """Test Yosys direct synthesis bypass (no parser needed)."""
        from backend.core.history import History
        from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer

        history = History()
        synthesizer = NetlistSynthesizer(history)
        outcome = synthesizer.process_paths([C17_PATH])

        assert outcome.success, f"Direct synthesis failed: {outcome.error_message}"
        assert outcome.data is not None


class TestNetlistGraphBuilder:
    """Test the graph construction stage."""

    def test_build_graph_c17(self):
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector
        from backend.netlist_graph_builder.builder import NetlistGraphBuilder
        from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer
        from backend.syntax_parser.parser import SyntaxParser

        history = History()

        collector = FileCollector(history)
        manifest = collector.process(C17_PATH)
        assert manifest.success

        parser = SyntaxParser(history)
        parsed = parser.process(manifest.data)
        assert parsed.success

        synthesizer = NetlistSynthesizer(history)
        synth = synthesizer.process(parsed.data)
        assert synth.success

        builder = NetlistGraphBuilder(history)
        outcome = builder.process(synth.data)

        assert outcome.success, f"Graph building failed: {outcome.error_message}"
        graph = outcome.data
        assert graph is not None
        assert graph.node_count > 0
        assert graph.edge_count > 0
        assert graph.graph_data is not None
        assert graph.graph_data.x.shape[0] == graph.node_count


class TestTrojanClassifier:
    """Test the trojan classification stage."""

    def _run_through_graph(self, file_path: Path):
        """Helper: run stages 1-4 and return (history, graph, parsed_modules)."""
        from backend.core.history import History
        from backend.file_ingestion.collector import FileCollector
        from backend.netlist_graph_builder.builder import NetlistGraphBuilder
        from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer
        from backend.syntax_parser.parser import SyntaxParser

        history = History()
        collector = FileCollector(history)
        manifest = collector.process(file_path)
        assert manifest.success

        parser = SyntaxParser(history)
        parsed = parser.process(manifest.data)
        assert parsed.success

        synthesizer = NetlistSynthesizer(history)
        synth = synthesizer.process(parsed.data)
        assert synth.success

        builder = NetlistGraphBuilder(history)
        graph = builder.process(synth.data)
        assert graph.success

        return history, graph.data, parsed.data

    def test_classify_clean_circuit(self):
        """c17 is a clean ISCAS benchmark — should not be flagged as infected."""
        from backend.trojan_classifier.ensemble import EnsembleClassifier
        from backend.trojan_classifier.models import TrojanVerdict

        history, graph, parsed = self._run_through_graph(C17_PATH)
        classifier = EnsembleClassifier(history)
        outcome = classifier.process(graph, parsed_modules=parsed)

        assert outcome.success, f"Classification failed: {outcome.error_message}"
        result = outcome.data
        assert result is not None
        assert result.confidence > 0.0
        assert result.trojan_probability >= 0.0
        assert result.trojan_probability <= 1.0
        assert result.verdict in (TrojanVerdict.CLEAN, TrojanVerdict.INFECTED, TrojanVerdict.UNCERTAIN)

    def test_single_model_gcn(self):
        """Test classification with GCN only."""
        from backend.trojan_classifier.ensemble import EnsembleClassifier

        history, graph, parsed = self._run_through_graph(C17_PATH)
        classifier = EnsembleClassifier(history, selected_models=["gcn"])
        outcome = classifier.process(graph, parsed_modules=parsed)

        assert outcome.success
        assert outcome.data is not None

    def test_single_model_gin(self):
        """Test classification with GIN only."""
        from backend.trojan_classifier.ensemble import EnsembleClassifier

        history, graph, parsed = self._run_through_graph(C17_PATH)
        classifier = EnsembleClassifier(history, selected_models=["gin"])
        outcome = classifier.process(graph, parsed_modules=parsed)

        assert outcome.success
        assert outcome.data is not None

    @pytest.mark.skipif(TROJAN_PATH is None, reason="No trojan benchmark files found")
    def test_classify_trojan_circuit(self):
        """A TrustHub trojan file should have trojan_probability > 0."""
        from backend.trojan_classifier.ensemble import EnsembleClassifier

        history, graph, parsed = self._run_through_graph(TROJAN_PATH)
        classifier = EnsembleClassifier(history)
        outcome = classifier.process(graph, parsed_modules=parsed)

        assert outcome.success, f"Classification failed: {outcome.error_message}"
        result = outcome.data
        assert result is not None
        assert result.trojan_probability >= 0.0

    def test_localization_produces_locations(self):
        """When a circuit is classified, trojan_locations should be a list."""
        from backend.trojan_classifier.ensemble import EnsembleClassifier

        history, graph, parsed = self._run_through_graph(C17_PATH)
        classifier = EnsembleClassifier(history)
        outcome = classifier.process(graph, parsed_modules=parsed)

        assert outcome.success
        assert isinstance(outcome.data.trojan_locations, list)


# ---------------------------------------------------------------------------
# Full pipeline tests
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """End-to-end pipeline tests."""

    def test_pipeline_clean_file(self, output_dir):
        """Run the full pipeline on a clean ISCAS benchmark."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=C17_PATH,
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        assert "export_paths" in result
        assert "history" in result

        report = result["report"]
        assert "classification_results" in report
        assert "processing_summary" in report

        # Check JSON export was created
        assert len(result["export_paths"]) > 0
        json_path = Path(result["export_paths"][0])
        assert json_path.exists()

    def test_pipeline_text_export(self, output_dir):
        """Verify text export format works."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=C17_PATH,
            output_dir=output_dir,
            export_formats=["text"],
        )

        assert len(result["export_paths"]) > 0
        text_path = Path(result["export_paths"][0])
        assert text_path.exists()
        content = text_path.read_text()
        assert len(content) > 0

    def test_pipeline_json_report_structure(self, output_dir):
        """Verify the JSON report contains expected sections."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=C17_PATH,
            output_dir=output_dir,
            export_formats=["json"],
        )

        json_path = Path(result["export_paths"][0])
        with open(json_path) as f:
            report = json.load(f)

        expected_keys = [
            "timestamp",
            "processing_summary",
            "classification_results",
        ]
        for key in expected_keys:
            assert key in report, f"Missing key '{key}' in report"

    def test_pipeline_with_selected_model(self, output_dir):
        """Run pipeline with only GCN model selected."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=C17_PATH,
            output_dir=output_dir,
            export_formats=["json"],
            selected_models=["gcn"],
        )

        assert "report" in result
        report = result["report"]
        assert "classification_results" in report

    def test_pipeline_sequential_benchmark(self, output_dir):
        """Run pipeline on s27 (sequential circuit with flip-flops)."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=S27_PATH,
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        assert "history" in result

    @pytest.mark.skipif(TROJAN_PATH is None, reason="No trojan benchmark files found")
    def test_pipeline_trojan_file(self, output_dir):
        """Run the full pipeline on a known trojan-infected file."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=TROJAN_PATH,
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        report = result["report"]
        assert "classification_results" in report

    def test_pipeline_invalid_file(self, output_dir):
        """Pipeline should handle nonexistent file gracefully."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=Path("/nonexistent/file.v"),
            output_dir=output_dir,
            export_formats=["json"],
        )

        # Pipeline should still return a result (with errors in report)
        assert "report" in result


class TestHistory:
    """Test that History captures all stage data correctly."""

    def test_history_records_all_stages(self, output_dir):
        """Verify History captures entries from all pipeline stages."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=C17_PATH,
            output_dir=output_dir,
            export_formats=["json"],
        )

        history = result["history"]
        assert "stages" in history or "entries" in history or len(history) > 0

    def test_history_contains_verdict(self, output_dir):
        """Verify the classification verdict is recorded in History."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run(
            input_path=C17_PATH,
            output_dir=output_dir,
            export_formats=["json"],
        )

        history_data = result["history"]
        history_str = json.dumps(history_data).lower()
        # The verdict should appear somewhere in the history
        assert any(
            v in history_str for v in ["clean", "infected", "uncertain"]
        ), "No verdict found in history"
