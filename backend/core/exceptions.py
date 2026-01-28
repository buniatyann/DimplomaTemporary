"""Custom exception classes for the trojan detection pipeline."""

from __future__ import annotations


class TrojanDetectorError(Exception):
    """Base exception for all trojan detector errors."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


class ParseError(TrojanDetectorError):
    """Raised when syntax parsing of a Verilog/SystemVerilog file fails."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if file_path:
            ctx["file_path"] = file_path
        if line is not None:
            ctx["line"] = line
        if column is not None:
            ctx["column"] = column
       
        super().__init__(message, ctx)
        self.file_path = file_path
        self.line = line
        self.column = column


class SynthesisError(TrojanDetectorError):
    """Raised when Yosys synthesis or elaboration fails."""

    def __init__(
        self,
        message: str,
        yosys_output: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if yosys_output:
            ctx["yosys_output"] = yosys_output
       
        super().__init__(message, ctx)
        self.yosys_output = yosys_output


class GraphBuildError(TrojanDetectorError):
    """Raised when graph construction from a netlist fails."""


class ClassificationError(TrojanDetectorError):
    """Raised when GNN inference fails."""

    def __init__(
        self,
        message: str,
        model_name: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if model_name:
            ctx["model_name"] = model_name
        super().__init__(message, ctx)
        self.model_name = model_name


class ReportGenerationError(TrojanDetectorError):
    """Raised when report export fails."""

    def __init__(
        self,
        message: str,
        export_format: str | None = None,
        context: dict | None = None,
    ) -> None:
        ctx = context or {}
        if export_format:
            ctx["export_format"] = export_format
        super().__init__(message, ctx)
        self.export_format = export_format
