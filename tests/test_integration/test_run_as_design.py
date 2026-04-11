"""Tests for run-as-design functionality (pipeline.run_file_list / API)."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not shutil.which("yosys"),
    reason="Yosys not found in PATH",
)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "training" / "data"
ISCAS85_DIR = DATA_DIR / "iscas" / "iscas85"
ISCAS89_DIR = DATA_DIR / "iscas" / "iscas89"

C17_PATH = ISCAS85_DIR / "c17.v"
S27_PATH = ISCAS89_DIR / "s27.v"


@pytest.fixture
def output_dir():
    d = tempfile.mkdtemp(prefix="trojan_design_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tb_design_dir():
    """A temp dir with one real design file and one testbench file."""
    d = Path(tempfile.mkdtemp(prefix="trojan_design_tb_"))
    shutil.copy(C17_PATH, d / "c17.v")
    (d / "tb_c17.v").write_text(
        "module tb_c17;\n"
        "  initial begin\n"
        "    $display(\"testbench\");\n"
        "    $finish;\n"
        "  end\n"
        "endmodule\n"
    )
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestRunFileList:
    """Pipeline.run_file_list — analyse an explicit file list as one design."""

    def test_single_file_as_design(self, output_dir):
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run_file_list(
            file_paths=[C17_PATH],
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        assert "classification_results" in result["report"]
        assert len(result["export_paths"]) > 0
        assert Path(result["export_paths"][0]).exists()

    def test_multiple_files_as_design(self, output_dir):
        """Multiple files should synthesise together into one netlist."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run_file_list(
            file_paths=[C17_PATH, S27_PATH],
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        report = result["report"]
        assert "classification_results" in report
        # One combined verdict, not two
        assert len(report["classification_results"]) <= 1 or isinstance(
            report["classification_results"], dict
        )

    def test_testbench_files_are_filtered(self, tb_design_dir, output_dir):
        """Files with tb_/test_/testbench prefixes must be excluded from synthesis."""
        from backend.core.pipeline import DetectionPipeline

        design_file = tb_design_dir / "c17.v"
        tb_file = tb_design_dir / "tb_c17.v"

        pipeline = DetectionPipeline()
        result = pipeline.run_file_list(
            file_paths=[design_file, tb_file],
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        # History should record the testbench was skipped
        import json
        history_str = json.dumps(result["history"]).lower()
        assert "skipped" in history_str and "testbench" in history_str

    def test_all_testbenches_fails_gracefully(self, tb_design_dir, output_dir):
        """If every input is a testbench, pipeline should fail cleanly at ingestion."""
        from backend.core.pipeline import DetectionPipeline

        tb_file = tb_design_dir / "tb_c17.v"
        pipeline = DetectionPipeline()
        result = pipeline.run_file_list(
            file_paths=[tb_file],
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        import json
        history_str = json.dumps(result["history"]).lower()
        assert "no synthesizable" in history_str

    def test_selected_model_only(self, output_dir):
        """run_file_list honours selected_models parameter."""
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        result = pipeline.run_file_list(
            file_paths=[C17_PATH],
            output_dir=output_dir,
            export_formats=["json"],
            selected_models=["gcn"],
        )

        assert "report" in result
        assert "classification_results" in result["report"]


class TestTrojanLocationSourceFile:
    """Every reported TrojanLocation.source_file must be a real user HDL file.

    Guards against the `.cc` leak: pyslang / Yosys internals must never
    appear in reports, only .v/.sv/.vh files the user actually supplied.
    """

    def _run_file_list(self, file_paths, output_dir):
        from backend.core.pipeline import DetectionPipeline

        pipeline = DetectionPipeline()
        return pipeline.run_file_list(
            file_paths=file_paths,
            output_dir=output_dir,
            export_formats=["json"],
        )

    def test_source_files_are_all_hdl(self, output_dir):
        """Every non-None source_file must have a .v/.sv/.vh suffix and exist."""
        result = self._run_file_list([C17_PATH, S27_PATH], output_dir)

        # The summarizer puts per-location data under top_suspicious_gates;
        # only populated when the classifier flags something, but we still
        # validate anything that DOES get reported.
        report = result["report"]
        cr = report.get("classification_results", {})
        top_gates = cr.get("top_suspicious_gates", [])

        _ALLOWED = {".v", ".sv", ".vh", ".svh"}
        _FORBIDDEN = (".cc", ".cpp", ".h", "pyslang", "yosys", "tmp")

        for gate in top_gates:
            src = gate.get("file")
            if src is None:
                continue
            # Every reported file must be HDL, on disk, and free of
            # internal-path markers.
            p = Path(src)
            assert p.suffix.lower() in _ALLOWED, (
                f"Non-HDL source_file leaked into report: {src}"
            )
            assert p.is_file(), f"Reported source_file does not exist: {src}"
            assert not any(marker in src.lower() for marker in _FORBIDDEN), (
                f"Internal path marker leaked into source_file: {src}"
            )

    def test_source_files_under_user_inputs(self, output_dir):
        """Reported source_file must match one of the files the user passed in."""
        inputs = [C17_PATH, S27_PATH]
        result = self._run_file_list(inputs, output_dir)

        allowed = {str(Path(p).resolve()) for p in inputs}
        top_gates = result["report"].get("classification_results", {}).get(
            "top_suspicious_gates", []
        )
        for gate in top_gates:
            src = gate.get("file")
            if src is None:
                continue
            assert str(Path(src).resolve()) in allowed, (
                f"source_file not in user input set: {src}"
            )


class TestDetectorAPIAsDesign:
    """DetectorAPI.analyze_files_as_design — public facade."""

    def test_api_single_design(self, output_dir):
        from backend.api.detector_api import DetectorAPI

        api = DetectorAPI()
        result = api.analyze_files_as_design(
            file_paths=[C17_PATH],
            output_dir=output_dir,
            export_formats=["json"],
        )

        assert "report" in result
        assert len(result["export_paths"]) > 0

    def test_api_analyze_directory_combined(self, output_dir):
        """analyze_directory with mode='combined' routes through run_directory."""
        from backend.api.detector_api import DetectorAPI

        api = DetectorAPI()
        result = api.analyze_directory(
            dir_path=ISCAS85_DIR,
            output_dir=output_dir,
            export_formats=["json"],
            mode="combined",
        )

        assert isinstance(result, dict)
        assert "report" in result

    def test_api_unknown_mode_raises(self, output_dir):
        from backend.api.detector_api import DetectorAPI

        api = DetectorAPI()
        with pytest.raises(ValueError, match="Unknown mode"):
            api.analyze_directory(
                dir_path=ISCAS85_DIR,
                output_dir=output_dir,
                mode="bogus",
            )
