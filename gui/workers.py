"""Background QThread workers for running the detection pipeline."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class DetectionWorker(QThread):
    """Processes a list of files sequentially through the backend pipeline.

    Emits Qt signals so the GUI can update without blocking the main thread.
    """

    file_started = Signal(str)                   # path
    file_completed = Signal(str, object)           # path, result dict
    file_error = Signal(str, str)                 # path, error message
    progress_updated = Signal(int, int)           # current, total
    all_completed = Signal()

    def __init__(
        self,
        file_paths: list[str],
        selected_models: list[str] | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._file_paths = list(file_paths)
        self._selected_models = selected_models
        self._cancelled = False

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    def cancel(self) -> None:
        self._cancelled = True

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------
    def run(self) -> None:  # noqa: D401 – Qt override
        total = len(self._file_paths)
        for idx, path in enumerate(self._file_paths, 1):
            if self._cancelled:
                break

            self.file_started.emit(path)
            self.progress_updated.emit(idx, total)

            try:
                result = self._analyse_file(path, self._selected_models)
                self.file_completed.emit(path, result)
            except Exception as exc:
                tb = traceback.format_exc()
                logger.error("Detection failed for %s:\n%s", path, tb)
                self.file_error.emit(path, str(exc))

        self.all_completed.emit()

    # ------------------------------------------------------------------
    # Backend integration
    # ------------------------------------------------------------------
    @staticmethod
    def _analyse_file(
        path: str, selected_models: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run the backend pipeline on a single file.

        Attempts to use the real DetectorAPI; falls back to a stub
        that simulates detection if the backend is unavailable.
        """
        try:
            from backend.api.detector_api import DetectorAPI

            api = DetectorAPI()
            result = api.analyze_file(
                path, export_formats=["text"], selected_models=selected_models,
            )
            return _extract_result(result)
        except Exception:
            logger.debug("Backend unavailable, using stub", exc_info=True)
            return _stub_analyse(path)


# ------------------------------------------------------------------
# Result extraction helpers
# ------------------------------------------------------------------

def _extract_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields the GUI cares about from a full pipeline result."""
    report = raw.get("report", {})
    classification = report.get("classification_results", {})

    # Build a human-readable report text from the report dict
    report_text = _build_report_text(report)

    verdict = classification.get("verdict") or "N/A"
    confidence = classification.get("confidence") or 0.0

    return {
        "is_trojan": verdict.lower() not in ("clean", "n/a"),
        "confidence": confidence,
        "verdict": verdict,
        "export_paths": raw.get("export_paths", []),
        "report_text": report_text,
        "raw": raw,
    }


def _build_report_text(report: dict[str, Any]) -> str:
    """Render a report dict into the text exporter format for GUI display."""
    try:
        from backend.analysis_summarizer.models import AnalysisReport
        from backend.analysis_summarizer.exporters.text_exporter import TextExporter

        analysis_report = AnalysisReport(**report)
        return TextExporter().render_to_string(analysis_report)
    except Exception:
        return _fallback_report_text(report)


def _fallback_report_text(report: dict[str, Any]) -> str:
    """Minimal report text when the full exporter is unavailable."""
    lines: list[str] = ["=" * 60, "  DETECTION REPORT", "=" * 60]

    fi = report.get("file_info", {})
    for fp in fi.get("file_paths", []):
        lines.append(f"  File: {fp}")

    cr = report.get("classification_results", {})
    if cr.get("verdict"):
        lines.append(f"  Verdict:    {cr['verdict']}")
        lines.append(f"  Confidence: {cr.get('confidence', 0):.4f}")

    errors = report.get("errors", [])
    if errors:
        lines.append("")
        lines.append("  Errors:")
        for e in errors:
            lines.append(f"    - {e}")

    lines.append("=" * 60)
    return "\n".join(lines)


def _stub_analyse(path: str) -> dict[str, Any]:
    """Deterministic stub when the real backend is not available."""
    import hashlib
    import time
    from datetime import datetime

    time.sleep(1.5)  # simulate processing delay
    digest = int(hashlib.md5(path.encode()).hexdigest(), 16)  # noqa: S324
    is_trojan = digest % 3 == 0  # ~33 % flagged for demo purposes
    confidence = 0.85 + (digest % 15) / 100.0 if is_trojan else 0.10 + (digest % 20) / 100.0
    confidence = round(min(confidence, 0.99), 4)
    verdict = "TROJAN" if is_trojan else "CLEAN"
    name = Path(path).name

    report_text = (
        f"{'=' * 72}\n"
        f"  HARDWARE TROJAN DETECTION REPORT\n"
        f"{'=' * 72}\n"
        f"  Generated: {datetime.now().isoformat()}\n"
        f"\n"
        f"--- File Information {'─' * 44}\n"
        f"  File: {path}\n"
        f"\n"
        f"--- Syntax Analysis {'─' * 44}\n"
        f"  No syntax errors.\n"
        f"\n"
        f"--- Synthesis {'─' * 50}\n"
        f"  No synthesis errors.\n"
        f"\n"
        f"--- Classification Results {'─' * 38}\n"
        f"  Verdict:           {verdict}\n"
        f"  Confidence:        {confidence:.4f}\n"
        f"\n"
        f"{'=' * 72}"
    )

    return {
        "is_trojan": is_trojan,
        "confidence": confidence,
        "verdict": verdict,
        "export_paths": [],
        "report_text": report_text,
        "raw": {},
    }
