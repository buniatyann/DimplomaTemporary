"""Startup dialog that lets the user choose where reports will be saved."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class _NewFolderDialog(QDialog):
    """Single dialog asking for both the parent location and the new folder name."""

    def __init__(self, start_parent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create New Folder")
        self.setMinimumWidth(460)

        self._parent_edit = QLineEdit(start_parent)
        browse = QPushButton("Browse…")
        browse.setFixedWidth(80)
        browse.clicked.connect(self._browse_parent)
        parent_row = QHBoxLayout()
        parent_row.addWidget(self._parent_edit)
        parent_row.addWidget(browse)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. trojan_reports")

        form = QFormLayout()
        form.addRow("Create in:", parent_row)
        form.addRow("Folder name:", self._name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(6)
        layout.addWidget(buttons)

    def _browse_parent(self) -> None:
        start = self._parent_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, "Select Parent Directory", start
        )
        if chosen:
            self._parent_edit.setText(chosen)

    @property
    def parent_path(self) -> str:
        return self._parent_edit.text().strip()

    @property
    def folder_name(self) -> str:
        return self._name_edit.text().strip()


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

        self._radio_group = QButtonGroup(self)
        self._radio_group.setExclusive(True)
        self._radio_group.addButton(self._radio_default)
        self._radio_group.addButton(self._radio_custom)

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
        new_btn = QPushButton("New Folder…")
        new_btn.setFixedWidth(100)
        new_btn.clicked.connect(self._create_new_folder)
        custom_row.addWidget(self._dir_edit)
        custom_row.addWidget(browse_btn)
        custom_row.addWidget(new_btn)

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

    def _create_new_folder(self) -> None:
        start_parent = self._dir_edit.text().strip() or str(Path.home())
        dialog = _NewFolderDialog(start_parent, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        parent = dialog.parent_path
        name = dialog.folder_name
        if not parent or not name:
            QMessageBox.warning(
                self, "Missing input", "Both location and folder name are required.",
            )
            return
        new_path = Path(parent) / name
        try:
            new_path.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            QMessageBox.warning(
                self, "Folder exists", f"'{new_path}' already exists.",
            )
            return
        except OSError as e:
            QMessageBox.critical(
                self, "Cannot create folder", f"Failed to create '{new_path}':\n{e}",
            )
            return
        self._dir_edit.setText(str(new_path))
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
