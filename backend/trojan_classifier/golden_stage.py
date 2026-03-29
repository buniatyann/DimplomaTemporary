"""Optional golden-reference comparison stage for the detection pipeline.

When the user provides a known-clean (golden) version of the design,
this stage synthesises both the suspect and golden netlists, diffs their
circuit graphs, and returns a ClassificationResult whose verdict and
suspicious-node list are derived entirely from the structural difference.

This is deterministic and needs no trained GNN weights — any gate present
in the suspect graph but absent from the golden graph is flagged as
trojan-inserted with suspicion_score=1.0 and detection_method="golden_diff".

If synthesis of the golden design fails for any reason the stage returns
None so the pipeline silently falls back to GNN-only analysis.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from backend.core.history import History
from backend.core.outcome import StageOutcome
from backend.netlist_graph_builder.builder import NetlistGraphBuilder
from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer
from backend.trojan_classifier.models import (
    ClassificationResult,
    TrojanLocation,
    TrojanVerdict,
)

if TYPE_CHECKING:
    from backend.netlist_graph_builder.models import CircuitGraph
    from backend.syntax_parser.models import ParsedModule

logger = logging.getLogger(__name__)

STAGE = "golden_diff"

_TB_PREFIXES = ("test_", "tb_", "tb", "testbench")


class GoldenDiffStage:
    """Runs golden-reference graph diff and produces a ClassificationResult."""

    def run(
        self,
        suspect_graph: CircuitGraph,
        golden_paths: list[Path],
        history: History,
        parsed_modules: list[ParsedModule] | None = None,
    ) -> StageOutcome[ClassificationResult] | None:
        """Compare suspect_graph against a freshly synthesised golden graph.

        Returns None on any synthesis / graph-build failure so the caller
        can fall back to GNN-only analysis without aborting.
        """
        history.begin_stage(STAGE)

        if not golden_paths:
            history.warning(STAGE, "No golden files provided — skipping golden diff")
            history.end_stage(STAGE, status="skipped")
            return None

        history.info(STAGE, f"Synthesising golden reference ({len(golden_paths)} file(s))")

        # Synthesise golden design
        golden_synthesizer = NetlistSynthesizer(history)
        golden_synth = golden_synthesizer.process_paths(golden_paths)
        if not golden_synth.success:
            history.warning(STAGE, f"Golden synthesis failed: {golden_synth.error_message}")
            history.end_stage(STAGE, status="failed")
            return None

        # Build golden graph
        golden_builder = NetlistGraphBuilder(history)
        golden_graph_outcome = golden_builder.process(golden_synth.data)
        if not golden_graph_outcome.success:
            history.warning(STAGE, "Golden graph build failed — skipping golden diff")
            history.end_stage(STAGE, status="failed")
            return None

        golden_graph: CircuitGraph = golden_graph_outcome.data

        # Diff: find nodes in suspect that have no match in golden
        diff_node_indices = self._diff_graphs(suspect_graph, golden_graph)

        history.info(
            STAGE,
            f"Golden diff: {len(diff_node_indices)} suspect-only node(s) out of "
            f"{len(suspect_graph.node_to_gate)} total",
        )
        history.record(STAGE, "golden_node_count", len(golden_graph.node_to_gate))
        history.record(STAGE, "suspect_node_count", len(suspect_graph.node_to_gate))
        history.record(STAGE, "diff_node_count", len(diff_node_indices))

        # Build ClassificationResult from diff
        result = self._build_result(
            suspect_graph, diff_node_indices, parsed_modules
        )

        history.record(STAGE, "verdict", result.verdict.value)
        history.record(STAGE, "golden_diff_node_count", result.golden_diff_node_count)
        history.end_stage(STAGE, status="completed")

        return StageOutcome.ok(result, stage_name=STAGE)

    # ------------------------------------------------------------------
    # Graph diffing
    # ------------------------------------------------------------------

    def _diff_graphs(
        self,
        suspect: CircuitGraph,
        golden: CircuitGraph,
    ) -> set[int]:
        """Return node indices from suspect whose gate has no match in golden."""
        golden_names = {
            self._normalize(name)
            for name in golden.node_to_gate.values()
        }

        diff: set[int] = set()
        for idx, gate_name in suspect.node_to_gate.items():
            if self._normalize(gate_name) not in golden_names:
                diff.add(idx)

        return diff

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize gate name for robust cross-synthesis comparison.

        Strips bit indices, trailing counters, and hierarchy prefixes so that
        minor Yosys naming differences don't inflate the diff count.
        """
        n = re.sub(r'\[\d+\]', '', name)       # remove [N] bit indices
        n = re.sub(r'_\d+$', '', n)            # remove trailing _N counters
        n = n.split('.')[-1]                   # drop hierarchy prefix
        return n.lower()

    # ------------------------------------------------------------------
    # Result construction
    # ------------------------------------------------------------------

    def _build_result(
        self,
        suspect_graph: CircuitGraph,
        diff_node_indices: set[int],
        parsed_modules: list[ParsedModule] | None,
    ) -> ClassificationResult:
        gate_scores: dict[str, float] = {}
        trojan_locations: list[TrojanLocation] = []

        gate_lookup = self._build_gate_lookup(parsed_modules)
        module_lookup = self._build_module_lookup(parsed_modules)

        for idx, gate_name in suspect_graph.node_to_gate.items():
            score = 1.0 if idx in diff_node_indices else 0.0
            gate_scores[gate_name] = score

            if idx not in diff_node_indices:
                continue

            gate_info = gate_lookup.get(gate_name, {})
            module_name = gate_info.get("module_name", "unknown")
            gate_type = gate_info.get("gate_type", "unknown")
            line_number = gate_info.get("line_number")
            source_file: str | None = None

            mod_info = module_lookup.get(module_name)
            if mod_info and mod_info.get("source_path"):
                source_file = mod_info["source_path"]
                if line_number is None:
                    line_number = self._find_gate_line(
                        Path(source_file), gate_name
                    )

            trojan_locations.append(
                TrojanLocation(
                    node_index=idx,
                    gate_name=gate_name,
                    gate_type=gate_type,
                    module_name=module_name,
                    source_file=source_file,
                    line_number=line_number,
                    suspicion_score=1.0,
                    detection_method="golden_diff",
                )
            )

        trojan_locations.sort(key=lambda x: x.gate_name)

        n_diff = len(diff_node_indices)
        n_total = len(suspect_graph.node_to_gate)
        trojan_pct = (n_diff / n_total * 100.0) if n_total > 0 else 0.0
        trojan_modules = list({loc.module_name for loc in trojan_locations})

        if n_diff > 0:
            verdict = TrojanVerdict.INFECTED
            trojan_prob = 1.0
            confidence = 1.0
        else:
            verdict = TrojanVerdict.CLEAN
            trojan_prob = 0.0
            confidence = 1.0

        return ClassificationResult(
            verdict=verdict,
            confidence=confidence,
            trojan_probability=trojan_prob,
            gate_suspicion_scores=gate_scores,
            model_version="golden_diff",
            architecture="golden_diff",
            trojan_locations=trojan_locations,
            trojan_node_percentage=round(trojan_pct, 4),
            trojan_modules=trojan_modules,
            high_risk=trojan_pct >= 5.0,
            golden_diff_used=True,
            golden_diff_node_count=n_diff,
        )

    # ------------------------------------------------------------------
    # Source location helpers (mirrors ensemble.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_module_lookup(
        parsed_modules: list[ParsedModule] | None,
    ) -> dict[str, dict]:
        if not parsed_modules:
            return {}
        return {
            m.name: {"source_path": m.source_path, "gate_count": len(m.gates)}
            for m in parsed_modules
        }

    @staticmethod
    def _build_gate_lookup(
        parsed_modules: list[ParsedModule] | None,
    ) -> dict[str, dict]:
        if not parsed_modules:
            return {}
        lookup: dict[str, dict] = {}
        for module in parsed_modules:
            for gate in module.gates:
                lookup[gate.instance_name] = {
                    "module_name": module.name,
                    "gate_type": gate.canonical_type or gate.gate_type,
                    "line_number": gate.line_number,
                }
        return lookup

    @staticmethod
    def _find_gate_line(source_file: Path, gate_name: str) -> int | None:
        if not source_file.exists():
            return None
        escaped = re.escape(gate_name)
        try:
            with open(source_file, encoding="utf-8", errors="replace") as fh:
                for line_num, line in enumerate(fh, start=1):
                    if re.search(rf'\b{escaped}\s*\(', line):
                        return line_num
                    if re.search(rf'\.\w+\s*\(\s*{escaped}\s*\)', line):
                        return line_num
                    if re.search(rf'\b(wire|reg|input|output)\b.*\b{escaped}\b', line):
                        return line_num
        except Exception as exc:
            logger.debug("Could not search %s: %s", source_file, exc)
        return None


def collect_golden_paths(golden_path: Path) -> list[Path]:
    """Return synthesisable Verilog files from a file or directory."""
    if golden_path.is_file():
        return [golden_path]
    if golden_path.is_dir():
        return [
            p for p in sorted(golden_path.rglob("*.v"))
            if not p.stem.lower().startswith(_TB_PREFIXES)
        ] + [
            p for p in sorted(golden_path.rglob("*.sv"))
            if not p.stem.lower().startswith(_TB_PREFIXES)
        ]
    return []
