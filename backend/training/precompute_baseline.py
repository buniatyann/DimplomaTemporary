"""Precompute the structural baseline from clean training circuits.

This script processes the trojan-free ISCAS benchmarks and TrustHub clean
references to build a JSON baseline that the StructuralVerifier uses at
inference time to resolve UNCERTAIN GNN verdicts.

Usage:
    python -m backend.training.precompute_baseline \
        --data-dir ./backend/training/data \
        --output ./backend/trojan_classifier/weights/structural_baseline.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def collect_clean_verilog_files(data_dir: Path) -> list[Path]:
    """Gather Verilog files from known-clean benchmark directories."""
    clean_files: list[Path] = []

    # ISCAS'85 combinational benchmarks (all clean)
    iscas85 = data_dir / "iscas" / "iscas85"
    if iscas85.exists():
        clean_files.extend(sorted(iscas85.glob("*.v")))

    # ISCAS'89 sequential benchmarks (all clean)
    iscas89 = data_dir / "iscas" / "iscas89"
    if iscas89.exists():
        clean_files.extend(sorted(iscas89.glob("*.v")))

    # EPFL combinational benchmarks (all clean)
    for subdir in ("arithmetic", "random_control"):
        epfl = data_dir / "epfl" / subdir
        if epfl.exists():
            clean_files.extend(sorted(epfl.glob("*.v")))

    # TrustHub trojan-free references
    trit_free = data_dir / "trit" / "TjFree"
    if trit_free.exists():
        clean_files.extend(sorted(trit_free.rglob("*.v")))

    # Also check alternate location
    tj_free = data_dir / "trit" / "tjFree"
    if tj_free.exists() and tj_free != trit_free:
        clean_files.extend(sorted(tj_free.rglob("*.v")))

    return clean_files


def build_baseline(clean_files: list[Path], output_path: Path) -> None:
    """Run the pipeline stages and compute the structural baseline."""
    import shutil

    if not shutil.which("yosys"):
        logger.error("Yosys not found in PATH — required for synthesis")
        sys.exit(1)

    from backend.core.history import History
    from backend.file_ingestion.collector import FileCollector
    from backend.netlist_graph_builder.builder import NetlistGraphBuilder
    from backend.netlist_graph_builder.models import CircuitGraph
    from backend.netlist_synthesizer.synthesizer import NetlistSynthesizer
    from backend.syntax_parser.parser import SyntaxParser
    from backend.trojan_classifier.structural_verifier import StructuralVerifier

    clean_graphs: list[CircuitGraph] = []
    errors = 0

    for i, vfile in enumerate(clean_files, 1):
        logger.info("[%d/%d] Processing %s", i, len(clean_files), vfile.name)
        try:
            history = History()

            collector = FileCollector(history)
            manifest = collector.process(vfile)
            if not manifest.success:
                logger.warning("  Ingestion failed: %s", manifest.error_message)
                errors += 1
                continue

            parser = SyntaxParser(history)
            parsed = parser.process(manifest.data)
            if not parsed.success:
                logger.warning("  Parsing failed: %s", parsed.error_message)
                errors += 1
                continue

            synthesizer = NetlistSynthesizer(history)
            synth = synthesizer.process(parsed.data)
            if not synth.success:
                logger.warning("  Synthesis failed: %s", synth.error_message)
                errors += 1
                continue

            builder = NetlistGraphBuilder(history)
            graph = builder.process(synth.data)
            if not graph.success:
                logger.warning("  Graph building failed: %s", graph.error_message)
                errors += 1
                continue

            clean_graphs.append(graph.data)
            logger.info("  OK (%d nodes, %d edges)", graph.data.node_count, graph.data.edge_count)

        except Exception as e:
            logger.warning("  Exception: %s", e)
            errors += 1

    logger.info(
        "Processed %d clean circuits (%d succeeded, %d failed)",
        len(clean_files), len(clean_graphs), errors,
    )

    if not clean_graphs:
        logger.error("No clean graphs — cannot build baseline")
        sys.exit(1)

    verifier = StructuralVerifier()
    verifier.precompute_baseline(clean_graphs)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    verifier.save_baseline(output_path)
    logger.info("Baseline saved to %s", output_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Precompute structural baseline from clean circuits"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Root data directory containing iscas/ and trit/ subdirs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "trojan_classifier" / "weights" / "structural_baseline.json",
        help="Output path for the baseline JSON",
    )
    args = parser.parse_args()

    clean_files = collect_clean_verilog_files(args.data_dir)
    if not clean_files:
        logger.error("No clean Verilog files found in %s", args.data_dir)
        sys.exit(1)

    logger.info("Found %d clean Verilog files", len(clean_files))
    build_baseline(clean_files, args.output)


if __name__ == "__main__":
    main()
