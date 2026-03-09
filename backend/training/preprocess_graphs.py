#!/usr/bin/env python3
"""Preprocess training Verilog files through the Yosys inference pipeline.

Eliminates the training/inference graph mismatch by building training graphs
with the same Yosys + NetlistGraphBuilder pipeline used at inference time.

Usage:
    python -m backend.training.preprocess_graphs --data-dir backend/training/data -v
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import torch

logger = logging.getLogger(__name__)

# Trojan gate name patterns (same as train_local.py)
TROJAN_NAME_PATTERNS = [
    r"(?i)trojan", r"(?i)^tj_", r"(?i)_tj$", r"(?i)trigger",
    r"(?i)payload", r"(?i)^mal_", r"(?i)^ht_", r"(?i)backdoor",
    r"(?i)leak", r"(?i)snoop", r"(?i)capture", r"(?i)hidden",
    r"(?i)kill", r"(?i)armed", r"(?i)corrupt",
]


def is_trojan_name(name: str) -> bool:
    return any(re.search(p, name) for p in TROJAN_NAME_PATTERNS)


@dataclass
class FileEntry:
    path: Path
    is_trojan: bool
    source: str  # trit_tc, trit_ts, iscas85, iscas89, epfl, trusthub
    benchmark_name: str
    trojan_gates: set[str] | None = None


@dataclass
class Stats:
    total: int = 0
    success: int = 0
    yosys_failed: int = 0
    graph_failed: int = 0
    too_small: int = 0
    failed_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# TRIT label loading (copied from train_local.py to avoid import dependencies)
# ---------------------------------------------------------------------------

def _parse_trit_log(log_path: Path) -> set[str]:
    trojan_gates: set[str] = set()
    try:
        content = log_path.read_text(errors="replace")
    except OSError:
        return trojan_gates
    in_body = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("TROJAN BODY"):
            in_body = True
            continue
        if in_body:
            if stripped.startswith("---") or stripped == "":
                continue
            if stripped.startswith("*"):
                in_body = False
                continue
            m = re.match(r'\s*\w+\s+(\w+)\s*\(', stripped)
            if m:
                trojan_gates.add(m.group(1))
    return trojan_gates


def _load_trit_labels(labels_dir: Path) -> dict[str, set[str]]:
    labels: dict[str, set[str]] = {}
    if not labels_dir.exists():
        return labels
    for log_file in sorted(labels_dir.glob("*_log.txt")):
        bench_name = log_file.stem.replace("_log", "")
        gates = _parse_trit_log(log_file)
        if gates:
            labels[bench_name] = gates
    return labels


# ---------------------------------------------------------------------------
# File discovery (mirrors train_local.py:_load_graphs_from_source)
# ---------------------------------------------------------------------------

def _discover_files(
    base: Path, trit_labels: dict[str, set[str]],
) -> list[FileEntry]:
    entries: list[FileEntry] = []

    # --- TRIT trojan files ---
    for trit_set in ("trit_tc", "trit_ts"):
        trit_dir = base / "trit" / "raw" / "leda250nm" / trit_set
        if not trit_dir.exists():
            continue
        for circuit_dir in sorted(trit_dir.iterdir()):
            if not circuit_dir.is_dir():
                continue
            for vf in sorted(circuit_dir.glob("*_T*.v")):
                entries.append(FileEntry(
                    path=vf,
                    is_trojan=True,
                    source=trit_set,
                    benchmark_name=vf.stem,
                    trojan_gates=trit_labels.get(vf.stem),
                ))

    # --- TRIT golden (clean) files ---
    for trit_set in ("trit_tc", "trit_ts"):
        trit_dir = base / "trit" / "raw" / "leda250nm" / trit_set
        if not trit_dir.exists():
            continue
        for vf in sorted(trit_dir.glob("*.v")):
            if "_T" in vf.stem:
                continue
            entries.append(FileEntry(
                path=vf, is_trojan=False, source=trit_set,
                benchmark_name=vf.stem,
            ))

    # --- ISCAS clean ---
    for sub in ("iscas85", "iscas89"):
        iscas_dir = base / "iscas" / sub
        if not iscas_dir.exists():
            continue
        for vf in sorted(iscas_dir.glob("*.v")):
            entries.append(FileEntry(
                path=vf, is_trojan=False, source=sub,
                benchmark_name=vf.stem,
            ))

    # --- EPFL clean ---
    for sub in ("arithmetic", "random_control"):
        epfl_dir = base / "epfl" / sub
        if not epfl_dir.exists():
            continue
        for vf in sorted(epfl_dir.glob("*.v")):
            entries.append(FileEntry(
                path=vf, is_trojan=False, source="epfl",
                benchmark_name=vf.stem,
            ))

    # --- TrustHub trojan + golden ---
    trusthub_dir = base / "trusthub"
    if trusthub_dir.exists():
        for bench_dir in sorted(trusthub_dir.iterdir()):
            if not bench_dir.is_dir():
                continue
            trojan_dir = bench_dir / "trojan"
            if trojan_dir.exists():
                for vf in sorted(trojan_dir.glob("*.v")):
                    entries.append(FileEntry(
                        path=vf, is_trojan=True, source="trusthub",
                        benchmark_name=f"{bench_dir.name}/{vf.stem}",
                    ))
            golden_dir = bench_dir / "golden"
            if golden_dir.exists():
                for vf in sorted(golden_dir.glob("*.v")):
                    entries.append(FileEntry(
                        path=vf, is_trojan=False, source="trusthub",
                        benchmark_name=f"{bench_dir.name}/{vf.stem}",
                    ))

    # --- HDL benchmarks (all clean) ---
    hdl_dir = base / "hdl_benchmarks"
    if hdl_dir.exists():
        for suite_link in sorted(hdl_dir.iterdir()):
            suite_name = suite_link.name
            for vf in sorted(suite_link.rglob("*.v")):
                entries.append(FileEntry(
                    path=vf, is_trojan=False, source=f"hdl_{suite_name}",
                    benchmark_name=f"{suite_name}/{vf.stem}",
                ))

    return entries


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def _compute_node_labels(
    node_to_gate: dict[int, str],
    entry: FileEntry,
) -> torch.Tensor:
    n = len(node_to_gate)
    labels = torch.zeros(n, dtype=torch.long)

    if not entry.is_trojan:
        return labels

    for idx, gate_name in node_to_gate.items():
        # Strip Yosys backslash-escaped identifiers
        clean_name = gate_name.lstrip("\\").strip()

        if entry.trojan_gates and clean_name in entry.trojan_gates:
            labels[idx] = 1
        elif is_trojan_name(clean_name):
            labels[idx] = 1

    return labels


def _process_one_file(
    entry: FileEntry,
    yosys_runner: "YosysRunner",
    stats: Stats,
) -> "Data | None":
    from backend.core.exceptions import SynthesisError
    from backend.core.history import History
    from backend.netlist_graph_builder.builder import NetlistGraphBuilder
    from backend.netlist_synthesizer.models import SynthesisResult
    from torch_geometric.data import Data

    # Step 1: Run Yosys (try preprocess first, then synthesize as fallback)
    json_netlist = None
    for method_name in ("preprocess", "synthesize"):
        try:
            method = getattr(yosys_runner, method_name)
            json_netlist, _, _ = method([entry.path])
            break
        except SynthesisError:
            if method_name == "synthesize":
                logger.debug(f"Both Yosys flows failed for {entry.path}")
                stats.yosys_failed += 1
                stats.failed_files.append(str(entry.path))
                return None

    if json_netlist is None:
        stats.yosys_failed += 1
        stats.failed_files.append(str(entry.path))
        return None

    # Check that the netlist has modules
    modules = json_netlist.get("modules", {})
    if not modules:
        stats.yosys_failed += 1
        stats.failed_files.append(str(entry.path))
        return None

    # Step 2: Build graph via NetlistGraphBuilder
    history = History()
    synth_result = SynthesisResult(
        json_netlist=json_netlist,
        source_paths=[str(entry.path)],
    )

    builder = NetlistGraphBuilder(history)
    outcome = builder.process(synth_result)
    if not outcome.success:
        logger.debug(f"Graph build failed for {entry.path}: {outcome.error_message}")
        stats.graph_failed += 1
        stats.failed_files.append(str(entry.path))
        return None

    circuit_graph = outcome.data
    pyg_data = circuit_graph.graph_data

    if circuit_graph.node_count < 3:
        stats.too_small += 1
        return None

    # Step 3: Assign labels
    node_labels = _compute_node_labels(circuit_graph.node_to_gate, entry)
    graph_label = torch.tensor([1 if entry.is_trojan else 0], dtype=torch.long)

    pyg_data.y = graph_label
    pyg_data.node_labels = node_labels
    pyg_data.num_nodes = circuit_graph.node_count
    pyg_data._name = entry.benchmark_name
    pyg_data._source = entry.source

    stats.success += 1
    return pyg_data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Preprocess training Verilog files through Yosys pipeline",
    )
    p.add_argument(
        "--data-dir", type=Path,
        default=Path("backend/training/data"),
        help="Root training data directory",
    )
    p.add_argument(
        "--output", type=Path, default=None,
        help="Output cache file (default: <data-dir>/precomputed_graphs/graphs.pt)",
    )
    p.add_argument(
        "--yosys-timeout", type=int, default=120,
        help="Per-file Yosys timeout in seconds (default: 120)",
    )
    p.add_argument("-v", "--verbose", action="count", default=0)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    level = logging.WARNING
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose >= 1:
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    from backend.netlist_synthesizer.yosys_runner import YosysRunner

    data_dir = args.data_dir.resolve()
    output_path = args.output or (data_dir / "precomputed_graphs" / "graphs.pt")

    runner = YosysRunner(timeout=args.yosys_timeout)
    if not runner.is_available:
        logger.error("Yosys not found in PATH. Install Yosys first.")
        return 1

    # Discover files
    trit_labels = _load_trit_labels(data_dir / "trit" / "raw" / "leda250nm" / "labels")
    logger.info(f"Loaded TRIT labels for {len(trit_labels)} benchmarks")

    entries = _discover_files(data_dir, trit_labels)
    logger.info(f"Discovered {len(entries)} Verilog files")

    if not entries:
        logger.error("No Verilog files found. Check --data-dir.")
        return 1

    # Process each file
    stats = Stats(total=len(entries))
    all_graphs = []

    for i, entry in enumerate(entries):
        if (i + 1) % 50 == 0 or i == 0:
            logger.info(f"Processing {i + 1}/{len(entries)}...")

        data = _process_one_file(entry, runner, stats)
        if data is not None:
            all_graphs.append(data)

    # Save cache
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(all_graphs, output_path)

    n_trojan = sum(1 for g in all_graphs if g.y.item() == 1)
    n_clean = len(all_graphs) - n_trojan

    logger.info("=" * 60)
    logger.info(f"Preprocessing complete!")
    logger.info(f"  Total files:    {stats.total}")
    logger.info(f"  Success:        {stats.success}")
    logger.info(f"  Yosys failed:   {stats.yosys_failed}")
    logger.info(f"  Graph failed:   {stats.graph_failed}")
    logger.info(f"  Too small:      {stats.too_small}")
    logger.info(f"  Graphs saved:   {len(all_graphs)} ({n_trojan} trojan, {n_clean} clean)")
    logger.info(f"  Output:         {output_path}")
    logger.info("=" * 60)

    if stats.failed_files:
        logger.debug(f"Failed files: {stats.failed_files[:30]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
