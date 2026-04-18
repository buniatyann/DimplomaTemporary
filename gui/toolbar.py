"""Main application toolbar with action buttons."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QToolBar,
    QToolButton,
    QWidget,
)


# Model configurations: (label, list of architectures to run, disable_cascade)
# When disable_cascade is True, all selected models always run (true ensemble);
# otherwise, the classifier may early-exit after the first highly confident model.
MODEL_CONFIGS: list[tuple[str, list[str], bool]] = [
    ("GCN", ["gcn"], False),
    ("GAT", ["gat"], False),
    ("GIN", ["gin"], False),
    ("GCN + GAT", ["gcn", "gat"], False),
    ("GCN + GIN", ["gcn", "gin"], False),
    ("GAT + GIN", ["gat", "gin"], False),
    ("Cascade (all)", ["gcn", "gat", "gin"], False),
    ("Ensemble (all)", ["gcn", "gat", "gin"], True),
]

# Number of items visible in the popup at once (rest scroll)
_VISIBLE_ROWS = 3


class _ModelPopup(QFrame):
    """Floating popup with a scrollable list showing 3 items at a time."""

    item_selected = Signal(int)  # index in MODEL_CONFIGS

    def __init__(self, current_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self._list = QListWidget(self)
        self._list.setStyleSheet(
            "QListWidget { font-size: 14px; }"
            "QListWidget::item { padding: 6px 4px; }"
        )
        for entry in MODEL_CONFIGS:
            self._list.addItem(entry[0])

        self._list.setCurrentRow(current_index)
        self._list.itemClicked.connect(self._on_click)

        # Size: show exactly _VISIBLE_ROWS rows
        row_h = self._list.sizeHintForRow(0)
        if row_h <= 0:
            row_h = 36
        # +2 for the frame border on top/bottom
        list_height = row_h * _VISIBLE_ROWS + 2
        self._list.setFixedHeight(list_height)
        self._list.setHorizontalScrollBarPolicy(
            self._list.horizontalScrollBarPolicy().ScrollBarAlwaysOff
            if hasattr(self._list.horizontalScrollBarPolicy(), "ScrollBarAlwaysOff")
            else 1  # Qt.ScrollBarAlwaysOff
        )

        # Make the popup the same width as the list
        width = max(self._list.sizeHintForColumn(0) + 30, 160)
        self._list.setFixedWidth(width)
        self.setFixedSize(width, list_height)

        self._list.move(0, 0)

        # Scroll so the current item is visible
        self._list.scrollToItem(
            self._list.item(current_index),
            QListWidget.ScrollHint.PositionAtCenter,
        )

    def _on_click(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        self.item_selected.emit(row)
        self.close()


class Toolbar(QToolBar):
    """Top toolbar emitting signals for each user action."""

    upload_file_clicked = Signal()
    upload_folder_clicked = Signal()
    run_all_clicked = Signal()             # run ALL files
    run_detection_clicked = Signal()       # run checked files only
    run_as_design_clicked = Signal()       # run checked files as one combined design
    stop_clicked = Signal()
    remove_checked_clicked = Signal()      # remove checked files
    clear_log_clicked = Signal()
    export_results_clicked = Signal()
    toggle_paths_clicked = Signal()
    export_format_changed = Signal(str)    # "json", "text", or "pdf"
    model_selection_changed = Signal(list, bool) # (architecture names, disable_cascade)
    theme_toggled = Signal(str)            # "dark" or "light"

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
        self._run_selected.setToolTip("Run detection on checked files independently (Ctrl+Shift+R)")
        self._run_selected.setEnabled(False)
        self._run_selected.triggered.connect(self.run_detection_clicked)
        self.addAction(self._run_selected)

        # ── Run as Design (checked files as one combined design) ──
        self._run_as_design = QAction("Run as Design", self)
        self._run_as_design.setShortcut(QKeySequence("Ctrl+D"))
        self._run_as_design.setToolTip(
            "Analyze checked files together as one design — synthesizes all files "
            "into a single netlist so cross-module connections are visible (Ctrl+D)"
        )
        self._run_as_design.setEnabled(False)
        self._run_as_design.triggered.connect(self.run_as_design_clicked)
        self.addAction(self._run_as_design)

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

        self.addSeparator()

        # ── Model Selector (button that opens a scrollable popup) ──
        self._selected_model_idx = len(MODEL_CONFIGS) - 1  # default: Ensemble
        self._model_button = QToolButton(self)
        self._model_button.setText(f"Model: {MODEL_CONFIGS[self._selected_model_idx][0]}")  # noqa: E501
        self._model_button.setToolTip("Select classification model(s)")
        self._model_button.clicked.connect(self._show_model_popup)
        self.addWidget(self._model_button)

        self.addSeparator()

        # ── Theme Toggle ──
        self._current_theme = "dark"
        self._theme_button = QToolButton(self)
        self._theme_button.setText("Light Mode")
        self._theme_button.setToolTip("Switch between dark and light theme")
        self._theme_button.clicked.connect(self._toggle_theme)
        self.addWidget(self._theme_button)

    # ------------------------------------------------------------------
    # Model selection
    # ------------------------------------------------------------------
    @property
    def selected_models(self) -> list[str]:
        """Return the list of architecture names for the current selection."""
        return list(MODEL_CONFIGS[self._selected_model_idx][1])

    @property
    def disable_cascade(self) -> bool:
        """True when the active selection forces every model to run (no early-exit)."""
        return MODEL_CONFIGS[self._selected_model_idx][2]

    def _show_model_popup(self) -> None:
        """Open a scrollable list popup below the model button."""
        popup = _ModelPopup(self._selected_model_idx, parent=self)
        popup.item_selected.connect(self._set_model)

        # Position below the button
        btn_pos = self._model_button.mapToGlobal(QPoint(0, self._model_button.height()))
        popup.move(btn_pos)
        popup.show()

    def _set_model(self, index: int) -> None:
        self._selected_model_idx = index
        label, archs, disable_cascade = MODEL_CONFIGS[index]
        self._model_button.setText(f"Model: {label}")
        self.model_selection_changed.emit(list(archs), disable_cascade)

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------
    def _toggle_theme(self) -> None:
        if self._current_theme == "dark":
            self._current_theme = "light"
            self._theme_button.setText("Dark Mode")
        else:
            self._current_theme = "dark"
            self._theme_button.setText("Light Mode")
        self.theme_toggled.emit(self._current_theme)

    @property
    def current_theme(self) -> str:
        return self._current_theme

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
        self._run_as_design.setEnabled(not processing and self._has_checked)
        self._stop.setEnabled(processing)
        self._upload_file.setEnabled(not processing)
        self._upload_folder.setEnabled(not processing)
        self._export.setEnabled(not processing)
        self._remove.setEnabled(not processing)
        self._model_button.setEnabled(not processing)

    def update_selection_state(self, has_checked: bool) -> None:
        """Enable/disable selection-dependent buttons based on checked files."""
        self._has_checked = has_checked
        idle = self._run_all.isEnabled()
        self._run_selected.setEnabled(has_checked and idle)
        self._run_as_design.setEnabled(has_checked and idle)
