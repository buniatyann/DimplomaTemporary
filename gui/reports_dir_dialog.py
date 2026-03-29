"""Startup dialog that lets the user choose where reports will be saved."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class ReportsDirDialog(QDialog):
    """Shown once on startup to pick the reports output directory."""

    def __init__(self, last_reports_dir: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reports Save Location")
        self.setMinimumWidth(480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._chosen_dir: str = ""

        # ── Radio: Default (current working directory) ──
        self._radio_default = QRadioButton("Default — save in current working directory")
        self._radio_default.setChecked(True)
        self._default_label = QLabel(f"  ({Path.cwd()})")
        self._default_label.setStyleSheet("color: gray; font-size: 11px;")

        # ── Radio: Custom directory ──
        self._radio_custom = QRadioButton("Choose a directory:")

        custom_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("No directory selected")
        self._dir_edit.setReadOnly(True)
        if last_reports_dir:
            self._dir_edit.setText(last_reports_dir)
            self._radio_custom.setChecked(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse)
        custom_row.addWidget(self._dir_edit)
        custom_row.addWidget(browse_btn)

        # ── Buttons ──
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        # ── Layout ──
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("<b>Where should reports be saved?</b>"))
        layout.addSpacing(4)
        layout.addWidget(self._radio_default)
        layout.addWidget(self._default_label)
        layout.addSpacing(6)
        layout.addWidget(self._radio_custom)
        layout.addLayout(custom_row)
        layout.addSpacing(8)
        layout.addWidget(buttons)

        # Toggle edit field enabled state
        self._radio_default.toggled.connect(self._on_radio_changed)
        self._on_radio_changed(self._radio_default.isChecked())

    # ------------------------------------------------------------------

    def _on_radio_changed(self, default_checked: bool) -> None:
        self._dir_edit.setEnabled(not default_checked)

    def _browse(self) -> None:
        start = self._dir_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Reports Directory", start)
        if folder:
            self._dir_edit.setText(folder)
            self._radio_custom.setChecked(True)

    def _accept(self) -> None:
        if self._radio_default.isChecked():
            self._chosen_dir = str(Path.cwd())
        else:
            custom = self._dir_edit.text().strip()
            self._chosen_dir = custom if custom else str(Path.cwd())
        self.accept()

    # ------------------------------------------------------------------
    # Public result
    # ------------------------------------------------------------------

    @property
    def chosen_directory(self) -> str:
        """Absolute path the user selected (or current dir for default)."""
        return self._chosen_dir
