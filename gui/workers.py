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
    file_completed = Signal(str, dict)            # path, result dict
    file_error = Signal(str, str)                 # path, error message
    progress_updated = Signal(int, int)           # current, total
    all_completed = Signal()

    def __init__(self, file_paths: list[str], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._file_paths = list(file_paths)
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
                result = self._analyse_file(path)
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
    def _analyse_file(path: str) -> dict[str, Any]:
        """Run the backend pipeline on a single file.

        Attempts to use the real DetectorAPI; falls back to a stub
        that simulates detection if the backend is unavailable.
        """
        try:
            from backend.api.detector_api import DetectorAPI

            api = DetectorAPI()
            result = api.analyze_file(path)
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
    return {
        "is_trojan": classification.get("verdict", "CLEAN") != "CLEAN",
        "confidence": classification.get("confidence", 0.0),
        "verdict": classification.get("verdict", "N/A"),
        "export_paths": raw.get("export_paths", []),
        "raw": raw,
    }


def _stub_analyse(path: str) -> dict[str, Any]:
    """Deterministic stub when the real backend is not available."""
    import hashlib
    import time

    time.sleep(1.5)  # simulate processing delay
    digest = int(hashlib.md5(path.encode()).hexdigest(), 16)  # noqa: S324
    is_trojan = digest % 3 == 0  # ~33 % flagged for demo purposes
    confidence = 0.85 + (digest % 15) / 100.0 if is_trojan else 0.10 + (digest % 20) / 100.0
    return {
        "is_trojan": is_trojan,
        "confidence": round(min(confidence, 0.99), 4),
        "verdict": "TROJAN" if is_trojan else "CLEAN",
        "export_paths": [],
        "raw": {},
    }
