"""NetlistSynthesizer facade for Yosys-based validation and synthesis."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from trojan_detector.backend.core.exceptions import SynthesisError
from trojan_detector.backend.core.history import History
from trojan_detector.backend.core.outcome import StageOutcome
from trojan_detector.backend.netlist_synthesizer.models import CellStatistics, SynthesisResult
from trojan_detector.backend.netlist_synthesizer.yosys_runner import YosysRunner
from trojan_detector.backend.syntax_parser.models import ParsedModule

logger = logging.getLogger(__name__)

STAGE = "netlist_synthesizer"


class NetlistSynthesizer:
    """Validates netlist synthesizability and extracts structural information using Yosys."""

    def __init__(self, history: History, timeout: int = 300) -> None:
        self._history = history
        self._runner = YosysRunner(timeout=timeout)

    def process(
        self, parsed_modules: list[ParsedModule]
    ) -> StageOutcome[SynthesisResult]:
        """Validate and synthesize netlists via Yosys.

        Args:
            parsed_modules: List of ParsedModule objects from syntax_parser.

        Returns:
            StageOutcome wrapping a SynthesisResult.
        """
        self._history.begin_stage(STAGE)
        start = time.time()

        if not self._runner.is_available:
            msg = "Yosys is not installed or not found in PATH"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        # Collect unique source paths
        source_paths: list[Path] = []
        seen: set[str] = set()
        for m in parsed_modules:
            if m.source_path and m.source_path not in seen:
                source_paths.append(Path(m.source_path))
                seen.add(m.source_path)

        if not source_paths:
            msg = "No source files to synthesize"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        self._history.info(
            STAGE,
            f"Running Yosys elaboration on {len(source_paths)} file(s)",
        )

        try:
            json_netlist, stdout, stderr = self._runner.elaborate(source_paths)
        except SynthesisError as e:
            self._history.error(STAGE, str(e), data=e.context)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(str(e), stage_name=STAGE)

        # Parse warnings from Yosys output
        warnings = self._extract_warnings(stdout + "\n" + stderr)
        for w in warnings:
            self._history.warning(STAGE, w)

        # Extract cell statistics from JSON netlist
        cell_stats = self._extract_cell_statistics(json_netlist)
        module_hierarchy = list(json_netlist.get("modules", {}).keys())

        duration = time.time() - start

        result = SynthesisResult(
            json_netlist=json_netlist,
            cell_statistics=cell_stats,
            module_hierarchy=module_hierarchy,
            warnings=warnings,
            source_paths=[str(p) for p in source_paths],
        )

        # Record in history
        self._history.record(STAGE, "synthesis_duration", duration)
        self._history.record(STAGE, "total_cells", cell_stats.total_cells)
        self._history.record(STAGE, "cell_counts", cell_stats.cell_counts)
        self._history.record(STAGE, "total_wires", cell_stats.total_wires)
        self._history.record(STAGE, "total_inputs", cell_stats.total_inputs)
        self._history.record(STAGE, "total_outputs", cell_stats.total_outputs)
        self._history.record(STAGE, "module_count", cell_stats.module_count)
        self._history.record(STAGE, "module_hierarchy", module_hierarchy)
        self._history.record(STAGE, "warning_count", len(warnings))

        self._history.info(
            STAGE,
            f"Synthesis completed: {cell_stats.total_cells} cells, "
            f"{cell_stats.total_wires} wires, {len(module_hierarchy)} modules",
        )
        self._history.end_stage(STAGE, status="completed")

        return StageOutcome.ok(result, stage_name=STAGE)

    def _extract_warnings(self, output: str) -> list[str]:
        """Extract warning lines from Yosys stdout/stderr."""
        warnings: list[str] = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped.startswith("Warning:") or "warning:" in stripped.lower():
                warnings.append(stripped)
        return warnings

    def _extract_cell_statistics(self, json_netlist: dict[str, Any]) -> CellStatistics:
        """Extract cell statistics from the Yosys JSON netlist."""
        stats = CellStatistics()
        modules = json_netlist.get("modules", {})
        stats.module_count = len(modules)

        for module_name, module_data in modules.items():
            cells = module_data.get("cells", {})
            for cell_name, cell_data in cells.items():
                cell_type = cell_data.get("type", "unknown")
                stats.add_cell(cell_type)

            # Count ports
            ports = module_data.get("ports", {})
            for port_name, port_data in ports.items():
                direction = port_data.get("direction", "")
                bits = port_data.get("bits", [])
                width = len(bits)
                if direction == "input":
                    stats.total_inputs += width
                elif direction == "output":
                    stats.total_outputs += width

            # Count nets/wires
            netnames = module_data.get("netnames", {})
            stats.total_wires += len(netnames)

        return stats
