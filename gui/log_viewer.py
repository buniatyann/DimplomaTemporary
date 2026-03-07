"""Colour-coded, timestamped log viewer widget."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class LogViewer(QPlainTextEdit):
    """Read-only monospace log panel with coloured severity levels."""

    # Colour palettes per theme
    _DARK_COLOURS: dict[str, QColor] = {
        "INFO": QColor("#B0B0B0"),
        "OK": QColor("#4CAF50"),
        "WARNING": QColor("#FFC107"),
        "ALERT": QColor("#F44336"),
    }

    _LIGHT_COLOURS: dict[str, QColor] = {
        "INFO": QColor("#333333"),
        "OK": QColor("#2E7D32"),
        "WARNING": QColor("#E65100"),
        "ALERT": QColor("#C62828"),
    }

    def __init__(self, max_lines: int = 10_000, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(max_lines)
        self._auto_scroll = True
        self._colours = self._DARK_COLOURS
        # Store entries for re-rendering on theme change
        self._entries: list[tuple[str, str]] = []  # (level, formatted_text)

    def set_theme(self, theme: str) -> None:
        """Switch colour palette and re-render all existing log entries."""
        self._colours = self._LIGHT_COLOURS if theme == "light" else self._DARK_COLOURS
        self._rerender()

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
        self._entries.append(("INFO", text + "\n"))
        self._insert_text("INFO", text + "\n")

    @Slot()
    def clear(self) -> None:  # type: ignore[override]
        super().clear()
        self._entries.clear()

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
        line = f"{timestamp} {level:<7} {message}\n"
        self._entries.append((level, line))
        self._insert_text(level, line)

    def _insert_text(self, level: str, text: str) -> None:
        colour = self._colours.get(level, self._colours["INFO"])
        fmt = QTextCharFormat()
        fmt.setForeground(colour)
        if level == "ALERT":
            fmt.setFontWeight(700)

        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text, fmt)

        if self._auto_scroll:
            scrollbar = self.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _rerender(self) -> None:
        """Re-render all stored entries with the current colour palette."""
        super().clear()
        for level, text in self._entries:
            self._insert_text(level, text)
