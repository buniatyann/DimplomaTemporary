"""Colour-coded, timestamped log viewer widget."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LogViewer(QPlainTextEdit):
    """Read-only monospace log panel with coloured severity levels."""

    # Colour palette per level
    _COLOURS: dict[str, QColor] = {
        "INFO": QColor("#B0B0B0"),
        "OK": QColor("#4CAF50"),
        "WARNING": QColor("#FFC107"),
        "ALERT": QColor("#F44336"),
    }

    def __init__(self, max_lines: int = 10_000, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        self._auto_scroll = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def log_info(self, message: str) -> None:
        self._append("INFO", message)

    def log_ok(self, message: str) -> None:
        self._append("OK", message)

    def log_warning(self, message: str) -> None:
        self._append("WARNING", message)

    def log_alert(self, message: str) -> None:
        self._append("ALERT", message)

    def append_plain(self, text: str) -> None:
        """Append unformatted text (e.g. a full report) to the viewer."""
        colour = self._COLOURS["INFO"]
        fmt = QTextCharFormat()
        fmt.setForeground(colour)

        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)

        if self._auto_scroll:
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    @Slot()
    def clear(self) -> None:  # type: ignore[override]
        super().clear()

    @property
    def auto_scroll(self) -> bool:
        return self._auto_scroll

    @auto_scroll.setter
    def auto_scroll(self, value: bool) -> None:
        self._auto_scroll = value

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _append(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("[%H:%M:%S]")
        colour = self._COLOURS.get(level, self._COLOURS["INFO"])

        fmt = QTextCharFormat()
        fmt.setForeground(colour)
        if level == "ALERT":
            fmt.setFontWeight(700)  # bold

        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(f"{timestamp} {level:<7} {message}\n", fmt)

        if self._auto_scroll:
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
