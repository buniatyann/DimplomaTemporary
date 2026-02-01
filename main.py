"""CLI entry point for the hardware trojan detection system.

When invoked without arguments the PySide6 GUI is launched.
Pass a file/directory path to use the CLI pipeline directly.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="trojan-detector",
        description="Detect hardware trojans in gate-level netlists using Graph Neural Networks.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=None,
        help="Path to a Verilog file or directory. Omit to launch the GUI.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for report output (default: current directory).",
    )
    parser.add_argument(
        "-f",
        "--format",
        nargs="+",
        choices=["json", "pdf", "text"],
        default=["json"],
        help="Export format(s) for the report (default: json).",
    )
    parser.add_argument(
        "-a",
        "--architecture",
        choices=["gcn", "gat", "gin"],
        default="gcn",
        help="GNN architecture to use (default: gcn).",
    )
    parser.add_argument(
        "-t",
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Confidence threshold for classification (default: 0.7).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Computation device: 'cpu', 'cuda', or 'cuda:N' (default: auto-detect).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase output verbosity (-v for INFO, -vv for DEBUG).",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process all files in directory independently.",
    )
    return parser.parse_args(argv)


def setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def progress_printer(stage: str, current: int, total: int) -> None:
    print(f"  [{current}/{total}] {stage}...")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    # No input path → launch the GUI
    if args.input is None:
        from gui.main import main as gui_main

        return gui_main()

    # CLI mode
    from backend.analysis_summarizer.exporters.text_exporter import TextExporter
    from backend.analysis_summarizer.models import AnalysisReport
    from backend.core.pipeline import DetectionPipeline

    input_path: Path = args.input.resolve()
    output_dir: Path = args.output_dir.resolve()

    if not input_path.exists():
        print(f"Error: path does not exist: {input_path}", file=sys.stderr)
        return 1

    print(f"Hardware Trojan Detector v0.1.0")
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    print()

    pipeline = DetectionPipeline(progress_callback=progress_printer)

    if args.batch and input_path.is_dir():
        results = pipeline.run_batch(
            input_path=input_path,
            output_dir=output_dir,
            export_formats=args.format,
        )
        print(f"\nProcessed {len(results)} file(s).")
        for i, result in enumerate(results):
            if "error" in result:
                print(f"  File {i + 1}: ERROR - {result['error']}")
            else:
                report_data = result.get("report", {})
                cr = report_data.get("classification_results", {})
                verdict = cr.get("verdict", "N/A")
                confidence = cr.get("confidence", 0)
                print(f"  File {i + 1}: {verdict} (confidence={confidence:.4f})")
    else:
        result = pipeline.run(
            input_path=input_path,
            output_dir=output_dir,
            export_formats=args.format,
        )

        report_data = result.get("report", {})

        # Print text summary to terminal
        report = AnalysisReport(**report_data)
        text_exporter = TextExporter()
        print(text_exporter.render_to_string(report))

        # Show export paths
        export_paths = result.get("export_paths", [])
        if export_paths:
            print("\nExported reports:")
            for p in export_paths:
                print(f"  {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
