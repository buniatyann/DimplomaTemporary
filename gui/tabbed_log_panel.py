"""Tabbed log panel with VS Code-style closable tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTabBar, QTabWidget, QWidget

from gui.log_viewer import LogViewer


class TabbedLogPanel(QTabWidget):
    """Multi-tab panel: a pinned 'Log' tab plus closable report tabs."""

    def __init__(
        self, max_lines: int = 10_000, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)

        self.setTabsClosable(True)
        self.setMovable(True)
        self.tabCloseRequested.connect(self._close_tab)

        # ── Pinned main log tab ──
        self._main_log = LogViewer(max_lines=max_lines, parent=self)
        self.addTab(self._main_log, "Log")
        # Make the first tab non-closable
        self.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)

        # Track open report tabs: path -> tab index
        self._report_tabs: dict[str, LogViewer] = {}

    # ------------------------------------------------------------------
    # Main log delegation
    # ------------------------------------------------------------------
    @property
    def main_log(self) -> LogViewer:
        """The pinned main log viewer."""
        return self._main_log

    def log_info(self, message: str) -> None:
        self._main_log.log_info(message)

    def log_ok(self, message: str) -> None:
        self._main_log.log_ok(message)

    def log_warning(self, message: str) -> None:
        self._main_log.log_warning(message)

    def log_alert(self, message: str) -> None:
        self._main_log.log_alert(message)

    def append_plain(self, text: str) -> None:
        self._main_log.append_plain(text)

    def clear(self) -> None:
        """Clear the main log tab."""
        self._main_log.clear()

    @property
    def auto_scroll(self) -> bool:
        return self._main_log.auto_scroll

    @auto_scroll.setter
    def auto_scroll(self, value: bool) -> None:
        self._main_log.auto_scroll = value

    # ------------------------------------------------------------------
    # Report tabs
    # ------------------------------------------------------------------
    def open_report(self, path: str, report_text: str) -> None:
        """Open (or focus) a report tab for the given file path."""
        if path in self._report_tabs:
            viewer = self._report_tabs[path]
            self.setCurrentWidget(viewer)
            return

        viewer = LogViewer(parent=self)
        viewer.auto_scroll = False
        # Apply same theme as main log
        viewer.set_theme(self._main_log._colours_key)

        name = Path(path).name
        viewer.log_info(f"Report for {name}:")
        viewer.append_plain(report_text)

        idx = self.addTab(viewer, name)
        self.setTabToolTip(idx, path)
        self.setCurrentIndex(idx)
        self._report_tabs[path] = viewer

    # ------------------------------------------------------------------
    # Theme support
    # ------------------------------------------------------------------
    def set_theme(self, theme: str) -> None:
        """Propagate theme change to all log viewers."""
        self._main_log.set_theme(theme)
        for viewer in self._report_tabs.values():
            viewer.set_theme(theme)

    # ------------------------------------------------------------------
    # Tab close
    # ------------------------------------------------------------------
    def _close_tab(self, index: int) -> None:
        """Close a tab (but never the pinned Log tab at index 0)."""
        if index == 0:
            return

        widget = self.widget(index)
        # Remove from tracking dict
        path_to_remove = None
        for path, viewer in self._report_tabs.items():
            if viewer is widget:
                path_to_remove = path
                break
        if path_to_remove:
            del self._report_tabs[path_to_remove]

        self.removeTab(index)
        widget.deleteLater()
