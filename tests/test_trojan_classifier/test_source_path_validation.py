"""Tests for TrojanLocation source_file validation.

These tests don't need Yosys — they exercise pure-Python helpers that
validate and parse source paths before they reach a TrojanLocation.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.netlist_graph_builder.builder import _parse_yosys_src
from backend.syntax_parser.models import ParsedModule
from backend.trojan_classifier.ensemble import _validate_source_path


@pytest.fixture
def hdl_file():
    """A real .v file on disk we can pass to the validator."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".v", delete=False, prefix="test_src_"
    ) as f:
        f.write("module dummy();\nendmodule\n")
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def cc_file():
    """A real .cc file on disk — must still be rejected by the validator."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cc", delete=False, prefix="test_src_"
    ) as f:
        f.write("// pyslang internal\n")
        path = f.name
    yield Path(path)
    Path(path).unlink(missing_ok=True)


class TestValidateSourcePath:
    """_validate_source_path enforces three rules: suffix, exists, allowlist."""

    def test_none_in_none_out(self):
        assert _validate_source_path(None, None) is None

    def test_empty_string_rejected(self):
        assert _validate_source_path("", None) is None

    def test_cc_file_rejected_even_if_exists(self, cc_file):
        """A real .cc file must still be rejected — suffix check fails first."""
        assert _validate_source_path(str(cc_file), None) is None

    def test_nonexistent_v_file_rejected(self):
        """A path with .v suffix that doesn't exist on disk is rejected."""
        assert _validate_source_path("/nonexistent/fake.v", None) is None

    def test_valid_v_file_passes_without_allowlist(self, hdl_file):
        """A real .v file on disk survives when no allowlist is provided."""
        result = _validate_source_path(str(hdl_file), None)
        assert result is not None
        assert Path(result).samefile(hdl_file)

    def test_valid_v_file_passes_with_matching_allowlist(self, hdl_file):
        """A real .v file survives when the parsed_modules allowlist contains it."""
        mod = ParsedModule(name="dummy", source_path=str(hdl_file))
        result = _validate_source_path(str(hdl_file), [mod])
        assert result is not None
        assert Path(result).samefile(hdl_file)

    def test_file_outside_allowlist_rejected(self, hdl_file, tmp_path):
        """A real .v file NOT in the parser's source list is rejected."""
        # Parser saw a different file
        other = tmp_path / "other.v"
        other.write_text("module other(); endmodule\n")
        mod = ParsedModule(name="other", source_path=str(other))
        # hdl_file exists and is .v but isn't in the allowlist
        assert _validate_source_path(str(hdl_file), [mod]) is None

    def test_sv_and_vh_suffixes_accepted(self, tmp_path):
        for suffix in (".sv", ".vh", ".svh"):
            f = tmp_path / f"sample{suffix}"
            f.write_text("// hdl\n")
            assert _validate_source_path(str(f), None) is not None

    def test_uppercase_suffix_accepted(self, tmp_path):
        """Case-insensitive suffix check."""
        f = tmp_path / "SAMPLE.V"
        f.write_text("// hdl\n")
        assert _validate_source_path(str(f), None) is not None


class TestParseYosysSrc:
    """_parse_yosys_src understands Yosys' `src` attribute format."""

    def test_empty_returns_none(self):
        assert _parse_yosys_src("", None) is None
        assert _parse_yosys_src(None, None) is None

    def test_missing_line_returns_none(self):
        # No colon separator
        assert _parse_yosys_src("justafile.v", None) is None

    def test_non_hdl_file_rejected(self, tmp_path):
        """Even a valid src format pointing at a .cc file is rejected."""
        cc = tmp_path / "simcells.cc"
        cc.write_text("// internal\n")
        assert _parse_yosys_src(f"{cc}:42.5-42.20", None) is None

    def test_nonexistent_file_rejected(self):
        assert _parse_yosys_src("/nonexistent/fake.v:10.1-10.5", None) is None

    def test_full_format_parses(self, tmp_path):
        """Standard "file.v:line.col-line.col" format."""
        f = tmp_path / "dut.v"
        f.write_text("// dut\n")
        result = _parse_yosys_src(f"{f}:42.5-42.20", None)
        assert result is not None
        resolved_path, line = result
        assert Path(resolved_path).samefile(f)
        assert line == 42

    def test_line_only_format_parses(self, tmp_path):
        f = tmp_path / "dut.v"
        f.write_text("// dut\n")
        result = _parse_yosys_src(f"{f}:17", None)
        assert result is not None
        _, line = result
        assert line == 17

    def test_multiple_sources_uses_first(self, tmp_path):
        """Yosys joins multiple src entries with `|`; take the first."""
        first = tmp_path / "first.v"
        first.write_text("// first\n")
        second = tmp_path / "second.v"
        second.write_text("// second\n")
        src_attr = f"{first}:10.1-10.5|{second}:20.1-20.5"
        result = _parse_yosys_src(src_attr, None)
        assert result is not None
        resolved_path, line = result
        assert Path(resolved_path).samefile(first)
        assert line == 10

    def test_temp_name_resolved_to_original(self, tmp_path):
        """run_file_list synthesises renamed temp copies; map back to the original."""
        original = tmp_path / "aes_128.v"
        original.write_text("// real source\n")
        temp_to_original = {
            "input_0_aes_128.v": str(original.resolve()),
        }
        result = _parse_yosys_src("input_0_aes_128.v:5.1-5.3", temp_to_original)
        assert result is not None
        resolved_path, line = result
        assert Path(resolved_path).samefile(original)
        assert line == 5

    def test_negative_or_zero_line_rejected(self, tmp_path):
        f = tmp_path / "dut.v"
        f.write_text("// dut\n")
        assert _parse_yosys_src(f"{f}:0.1-0.5", None) is None

    def test_garbage_line_rejected(self, tmp_path):
        f = tmp_path / "dut.v"
        f.write_text("// dut\n")
        assert _parse_yosys_src(f"{f}:garbage", None) is None
