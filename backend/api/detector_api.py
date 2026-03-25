"""DetectorAPI facade for GUI and external consumers."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from backend.core.pipeline import DetectionPipeline, ProgressCallback

logger = logging.getLogger(__name__)


class DetectorAPI:
    """Simplified facade hiding pipeline complexity for GUI integration.

    Provides high-level methods for analysis with support for progress
    callbacks, cancellation, and threading.
    """

    def __init__(self, progress_callback: ProgressCallback | None = None) -> None:
        self._progress_callback = progress_callback
        self._pipeline = DetectionPipeline(progress_callback=progress_callback)
        self._cancel_event = threading.Event()
        self._current_thread: threading.Thread | None = None

    def analyze_file(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        export_formats: list[str] | None = None,
        selected_models: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze a single Verilog file.

        Args:
            file_path: Path to the Verilog file.
            output_dir: Directory for report output.
            export_formats: List of export formats.
            selected_models: List of model architectures to use
                (e.g. ["gcn"], ["gcn", "gat"], or None for all).

        Returns:
            Dictionary containing the analysis report and export paths.
        """
        return self._pipeline.run(
            input_path=Path(file_path),
            output_dir=Path(output_dir) if output_dir else None,
            export_formats=export_formats,
            selected_models=selected_models,
        )

    def analyze_directory(
        self,
        dir_path: str | Path,
        output_dir: str | Path | None = None,
        export_formats: list[str] | None = None,
        mode: str = "combined",
        selected_models: list[str] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Analyze all Verilog files in a directory.

        Args:
            dir_path: Path to the directory.
            output_dir: Directory for report output.
            export_formats: List of export formats.
            mode: Analysis mode:
                - "combined": Synthesize all files as one design (default).
                    Best for whole-design verdicts — matches training data.
                - "per_file": Analyze each file independently.
                - "both": Run combined design analysis AND per-file analysis.
                    Returns dict with "design" and "per_file" keys.
            selected_models: List of model architectures to use.

        Returns:
            Result dict, list of dicts, or dict with both (depending on mode).
        """
        out_dir = Path(output_dir) if output_dir else None

        if mode == "combined":
            return self._pipeline.run_directory(
                input_path=Path(dir_path),
                output_dir=out_dir,
                export_formats=export_formats,
                selected_models=selected_models,
            )
        elif mode == "per_file":
            return self._pipeline.run_batch(
                input_path=Path(dir_path),
                output_dir=out_dir,
                export_formats=export_formats,
            )
        elif mode == "both":
            design_result = self._pipeline.run_directory(
                input_path=Path(dir_path),
                output_dir=out_dir,
                export_formats=export_formats,
                selected_models=selected_models,
            )
            per_file_results = self._pipeline.run_batch(
                input_path=Path(dir_path),
                output_dir=out_dir,
                export_formats=export_formats,
            )
            return {
                "design": design_result,
                "per_file": per_file_results,
            }
        else:
            raise ValueError(f"Unknown mode {mode!r}. Use 'combined', 'per_file', or 'both'.")

    def analyze_file_async(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        export_formats: list[str] | None = None,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> threading.Thread:
        """Analyze a file in a background thread (non-blocking for GUI).

        Args:
            file_path: Path to the Verilog file.
            output_dir: Directory for report output.
            export_formats: List of export formats.
            on_complete: Callback invoked with results on success.
            on_error: Callback invoked with exception on failure.

        Returns:
            The background thread running the analysis.
        """
        self._cancel_event.clear()

        def _worker() -> None:
            try:
                result = self.analyze_file(file_path, output_dir, export_formats)
                if on_complete and not self._cancel_event.is_set():
                    on_complete(result)
            except Exception as e:
                if on_error and not self._cancel_event.is_set():
                    on_error(e)

        thread = threading.Thread(target=_worker, daemon=True)
        self._current_thread = thread
        thread.start()
        
        return thread

    def cancel(self) -> None:
        """Request cancellation of the current analysis."""
        self._cancel_event.set()

    @property
    def is_running(self) -> bool:
        """Check if an analysis is currently in progress."""
        return self._current_thread is not None and self._current_thread.is_alive()
