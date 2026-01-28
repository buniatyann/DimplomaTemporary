"""SyntaxParser facade for routing to the appropriate parser implementation."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from trojan_detector.backend.core.exceptions import ParseError
from trojan_detector.backend.core.history import History
from trojan_detector.backend.core.outcome import StageOutcome
from trojan_detector.backend.file_ingestion.models import (
    DirectoryManifest,
    FileEntry,
    FileType,
)
from trojan_detector.backend.syntax_parser.models import ParsedModule
from trojan_detector.backend.syntax_parser.systemverilog_parser import SystemVerilogParser
from trojan_detector.backend.syntax_parser.verilog_parser import VerilogParser

logger = logging.getLogger(__name__)

STAGE = "syntax_parser"


class SyntaxParser:
    """Facade that selects and delegates to the appropriate parser."""

    def __init__(self, history: History) -> None:
        self._history = history
        self._verilog_parser = VerilogParser(history)
        self._sv_parser = SystemVerilogParser(history)

    def process(
        self, manifest: DirectoryManifest
    ) -> StageOutcome[list[ParsedModule]]:
        """Parse all files in the manifest.

        Args:
            manifest: DirectoryManifest from file_ingestion stage.

        Returns:
            StageOutcome wrapping a list of ParsedModule objects.
        """
        self._history.begin_stage(STAGE)
        start = time.time()

        all_modules: list[ParsedModule] = []
        total_gates = 0
        total_wires = 0
        errors: list[str] = []

        for file_entry in manifest.files:
            try:
                modules = self._parse_file(file_entry)
                all_modules.extend(modules)
                for m in modules:
                    total_gates += len(m.gates)
                    total_wires += len(m.wires)
            except ParseError as e:
                errors.append(f"{file_entry.path.name}: {e}")
                self._history.error(STAGE, str(e), data=e.context)

        duration = time.time() - start

        self._history.record(STAGE, "parse_duration", duration)
        self._history.record(STAGE, "module_count", len(all_modules))
        self._history.record(STAGE, "total_gates", total_gates)
        self._history.record(STAGE, "total_wires", total_wires)
        self._history.record(STAGE, "module_names", [m.name for m in all_modules])

        if not all_modules:
            msg = "No modules extracted from any file"
            if errors:
                msg += f" ({len(errors)} parse error(s))"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        if errors:
            self._history.warning(
                STAGE,
                f"{len(errors)} file(s) had parse errors but {len(all_modules)} module(s) extracted",
            )

        self._history.info(
            STAGE,
            f"Parsed {len(all_modules)} module(s): {total_gates} gates, {total_wires} wires",
        )
        self._history.end_stage(STAGE, status="completed")
        return StageOutcome.ok(all_modules, stage_name=STAGE)

    def _parse_file(self, file_entry: FileEntry) -> list[ParsedModule]:
        """Route a file to the appropriate parser based on its type."""
        parser_name: str

        if file_entry.file_type == FileType.SYSTEMVERILOG:
            parser_name = "SystemVerilogParser (pyslang)"
            self._history.info(
                STAGE,
                f"Selected {parser_name} for {file_entry.path.name}",
            )
            return self._sv_parser.parse(file_entry.path)
        else:
            parser_name = "VerilogParser (pyverilog)"
            self._history.info(
                STAGE,
                f"Selected {parser_name} for {file_entry.path.name}",
            )
            return self._verilog_parser.parse(file_entry.path)
