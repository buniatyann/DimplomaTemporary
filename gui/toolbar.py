"""Main application toolbar with action buttons."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QToolBar, QToolButton, QWidget


class Toolbar(QToolBar):
    """Top toolbar emitting signals for each user action."""

    upload_file_clicked = Signal()
    upload_folder_clicked = Signal()
    run_all_clicked = Signal()             # run ALL files
    run_detection_clicked = Signal()       # run checked files only
    stop_clicked = Signal()
    remove_checked_clicked = Signal()      # remove checked files
    clear_log_clicked = Signal()
    export_results_clicked = Signal()
    toggle_paths_clicked = Signal()
    export_format_changed = Signal(str)    # "json", "text", or "pdf"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)
        self._has_checked = False

        # ── Upload File ──
        self._upload_file = QAction("Upload File", self)
        self._upload_file.setShortcut(QKeySequence("Ctrl+O"))
        self._upload_file.setToolTip("Upload Verilog file (Ctrl+O)")
        self._upload_file.triggered.connect(self.upload_file_clicked)
        self.addAction(self._upload_file)

        # ── Upload Folder ──
        self._upload_folder = QAction("Upload Folder", self)
        self._upload_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self._upload_folder.setToolTip("Upload folder of Verilog files (Ctrl+Shift+O)")
        self._upload_folder.triggered.connect(self.upload_folder_clicked)
        self.addAction(self._upload_folder)

        # ── Show Absolute Paths ──
        self._toggle_paths = QAction("Show Paths", self)
        self._toggle_paths.setCheckable(True)
        self._toggle_paths.setToolTip("Toggle absolute path display")
        self._toggle_paths.triggered.connect(self.toggle_paths_clicked)
        self.addAction(self._toggle_paths)

        self.addSeparator()

        # ── Run (all files) ──
        self._run_all = QAction("Run", self)
        self._run_all.setShortcut(QKeySequence("Ctrl+R"))
        self._run_all.setToolTip("Run detection on all files (Ctrl+R)")
        self._run_all.triggered.connect(self.run_all_clicked)
        self.addAction(self._run_all)

        # ── Run Selected (checked files only) ──
        self._run_selected = QAction("Run Selected", self)
        self._run_selected.setShortcut(QKeySequence("Ctrl+Shift+R"))
        self._run_selected.setToolTip("Run detection on checked files (Ctrl+Shift+R)")
        self._run_selected.setEnabled(False)
        self._run_selected.triggered.connect(self.run_detection_clicked)
        self.addAction(self._run_selected)

        # ── Stop ──
        self._stop = QAction("Stop", self)
        self._stop.setShortcut(QKeySequence("Escape"))
        self._stop.setToolTip("Cancel detection (Escape)")
        self._stop.setEnabled(False)
        self._stop.triggered.connect(self.stop_clicked)
        self.addAction(self._stop)

        # ── Remove Selected ──
        self._remove = QAction("Remove Selected", self)
        self._remove.setShortcut(QKeySequence("Delete"))
        self._remove.setToolTip("Remove checked files (Delete)")
        self._remove.triggered.connect(self.remove_checked_clicked)
        self.addAction(self._remove)

        self.addSeparator()

        # ── Clear Log ──
        self._clear_log = QAction("Clear Log", self)
        self._clear_log.setShortcut(QKeySequence("Ctrl+L"))
        self._clear_log.setToolTip("Clear log output (Ctrl+L)")
        self._clear_log.triggered.connect(self.clear_log_clicked)
        self.addAction(self._clear_log)

        # ── Export Results ──
        self._export = QAction("Export Results", self)
        self._export.setShortcut(QKeySequence("Ctrl+E"))
        self._export.setToolTip("Export analysis report (Ctrl+E)")
        self._export.triggered.connect(self.export_results_clicked)
        self.addAction(self._export)

        # ── Export Format selector ──
        self._export_format = "json"
        self._format_button = QToolButton(self)
        self._format_button.setText("Format: JSON")
        self._format_button.setToolTip("Choose export format")
        self._format_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        fmt_menu = QMenu(self._format_button)
        self._fmt_json = QAction("JSON (.json)", self)
        self._fmt_json.setCheckable(True)
        self._fmt_json.setChecked(True)
        self._fmt_json.triggered.connect(lambda: self._set_format("json"))
        fmt_menu.addAction(self._fmt_json)

        self._fmt_text = QAction("Text (.txt)", self)
        self._fmt_text.setCheckable(True)
        self._fmt_text.triggered.connect(lambda: self._set_format("text"))
        fmt_menu.addAction(self._fmt_text)

        self._fmt_pdf = QAction("PDF (.pdf)", self)
        self._fmt_pdf.setCheckable(True)
        self._fmt_pdf.triggered.connect(lambda: self._set_format("pdf"))
        fmt_menu.addAction(self._fmt_pdf)

        self._format_button.setMenu(fmt_menu)
        self.addWidget(self._format_button)

    # ------------------------------------------------------------------
    # Export format
    # ------------------------------------------------------------------
    @property
    def export_format(self) -> str:
        return self._export_format

    def _set_format(self, fmt: str) -> None:
        self._export_format = fmt
        label = {"json": "JSON", "text": "Text", "pdf": "PDF"}[fmt]
        self._format_button.setText(f"Format: {label}")
        self._fmt_json.setChecked(fmt == "json")
        self._fmt_text.setChecked(fmt == "text")
        self._fmt_pdf.setChecked(fmt == "pdf")
        self.export_format_changed.emit(fmt)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def set_processing(self, processing: bool) -> None:
        """Toggle button enabled state during processing."""
        self._run_all.setEnabled(not processing)
        self._run_selected.setEnabled(not processing and self._has_checked)
        self._stop.setEnabled(processing)
        self._upload_file.setEnabled(not processing)
        self._upload_folder.setEnabled(not processing)
        self._export.setEnabled(not processing)
        self._remove.setEnabled(not processing)

    def update_selection_state(self, has_checked: bool) -> None:
        """Enable/disable 'Run Selected' based on whether any files are checked."""
        self._has_checked = has_checked
        self._run_selected.setEnabled(has_checked and self._run_all.isEnabled())
