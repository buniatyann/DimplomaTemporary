"""Checkbox-based file explorer with Files and Directories sections.

Layout:
    ── Files ──────────────────────
    [x] ⚪  c7552.v
    [ ] 🟢  c2670_T001.v
    ── Directories ────────────────
    [x] 📁  c2670
        [x] ⚪  c2670_T000.v
        [ ] 🔴  c2670_T001.v

Checkboxes allow selecting individual files (or whole directories)
for running detection or removing them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QTreeView, QWidget

from gui.state import FILE_STATUS_ICONS, AppStateManager, FileStatus

_VERILOG_FILTER = "Verilog Files (*.v *.sv *.vh)"
_VERILOG_SUFFIXES = {".v", ".sv", ".vh"}

# Role constants for item data
_ROLE_PATH = Qt.ItemDataRole.UserRole          # absolute file/dir path
_ROLE_KIND = Qt.ItemDataRole.UserRole + 1      # "file", "dir", "section"


def _make_section_header(title: str) -> QStandardItem:
    """Non-selectable, bold section separator."""
    item = QStandardItem(f"\u2500\u2500 {title} \u2500\u2500")
    item.setSelectable(False)
    item.setEditable(False)
    item.setEnabled(False)
    item.setData("section", _ROLE_KIND)
    font = QFont()
    font.setBold(True)
    item.setFont(font)
    item.setForeground(QBrush(QColor("#808080")))
    return item


def _make_file_item(path: str, show_absolute: bool, status: FileStatus) -> QStandardItem:
    """Checkable file row — no children, no expand triangle."""
    display = path if show_absolute else Path(path).name
    icon = FILE_STATUS_ICONS[status]
    item = QStandardItem(f"{icon}  {display}")
    item.setData(path, _ROLE_PATH)
    item.setData("file", _ROLE_KIND)
    item.setToolTip(path)
    item.setCheckable(True)
    item.setCheckState(Qt.CheckState.Checked)
    return item


def _make_dir_item(dir_path: str) -> QStandardItem:
    """Checkable directory row — children are file items."""
    dir_name = Path(dir_path).name or dir_path
    item = QStandardItem(f"\U0001f4c1  {dir_name}")
    item.setData(dir_path, _ROLE_PATH)
    item.setData("dir", _ROLE_KIND)
    item.setToolTip(dir_path)
    item.setCheckable(True)
    item.setCheckState(Qt.CheckState.Checked)
    font = QFont()
    font.setBold(True)
    item.setFont(font)
    return item


class FileExplorer(QTreeView):
    """Left-panel tree with checkbox selection for files and directories."""

    files_added = Signal(list)          # list[str]
    file_removed = Signal(str)
    selection_changed = Signal(bool)    # True if any file is checked
    file_double_clicked = Signal(str)   # path — emitted on double-click of a file item

    def __init__(self, state_mgr: AppStateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state_mgr = state_mgr
        self._show_absolute = False

        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Files"])
        self.setModel(self._model)

        self.setAlternatingRowColors(True)
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)
        self.setEditTriggers(self.EditTrigger.NoEditTriggers)
        self.setRootIsDecorated(True)
        self.setIndentation(20)

        # Drag-drop
        self.setAcceptDrops(True)
        self.setDragDropMode(self.DragDropMode.DropOnly)

        # State signals
        self._state_mgr.file_status_changed.connect(self._on_status_changed)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Propagate dir checkbox → children
        self._model.itemChanged.connect(self._on_item_changed)

        # Double-click → show report
        self.doubleClicked.connect(self._on_double_click)

        # ── Section headers ──
        self._files_header = _make_section_header("Files")
        self._dirs_header = _make_section_header("Directories")
        self._model.appendRow([self._files_header])
        self._model.appendRow([self._dirs_header])

        # ── Tracking ──
        self._file_items: dict[str, QStandardItem] = {}      # Files section
        self._dir_items: dict[str, QStandardItem] = {}        # dir nodes
        self._dir_file_items: dict[str, QStandardItem] = {}   # files inside dirs
        self._all_paths: set[str] = set()

    # ------------------------------------------------------------------
    # Add individual files (Files section)
    # ------------------------------------------------------------------
    def add_files(self, paths: list[str]) -> list[str]:
        added: list[str] = []
        for p in paths:
            if p in self._all_paths:
                continue
            item = _make_file_item(p, self._show_absolute, FileStatus.PENDING)
            self._files_header.appendRow([item])
            self._file_items[p] = item
            self._all_paths.add(p)
            self._state_mgr.set_file_status(p, FileStatus.PENDING)
            added.append(p)
        if added:
            self.files_added.emit(added)
            self.selection_changed.emit(len(self.checked_paths()) > 0)
        return added

    # ------------------------------------------------------------------
    # Add folder (Directories section)
    # ------------------------------------------------------------------
    def add_folder(self, root_folder: str) -> list[str]:
        """Add a folder to the Directories section.

        The dropped folder becomes a top-level dir item.  Its subfolders and
        files are nested recursively inside it, mirroring the real directory
        tree.
        """
        root = Path(root_folder)
        added: list[str] = []

        root_key = str(root)
        if root_key not in self._dir_items:
            root_item = _make_dir_item(root_key)
            self._dirs_header.appendRow([root_item])
            self._dir_items[root_key] = root_item
        else:
            root_item = self._dir_items[root_key]

        self._populate_dir_item(root_item, root, added)

        if added:
            self.files_added.emit(added)
            self.selection_changed.emit(len(self.checked_paths()) > 0)
        return added

    def _populate_dir_item(
        self, parent_item: QStandardItem, dir_path: Path, added: list[str]
    ) -> None:
        """Recursively add subfolders and files under *parent_item*."""
        try:
            entries = sorted(dir_path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        except PermissionError:
            return

        for entry in entries:
            if entry.is_dir():
                sub_key = str(entry)
                if sub_key not in self._dir_items:
                    sub_item = _make_dir_item(sub_key)
                    parent_item.appendRow([sub_item])
                    self._dir_items[sub_key] = sub_item
                else:
                    sub_item = self._dir_items[sub_key]
                self._populate_dir_item(sub_item, entry, added)
            elif entry.is_file() and entry.suffix.lower() in _VERILOG_SUFFIXES:
                fp = str(entry)
                if fp in self._all_paths:
                    continue
                child = _make_file_item(fp, self._show_absolute, FileStatus.PENDING)
                parent_item.appendRow([child])
                self._dir_file_items[fp] = child
                self._all_paths.add(fp)
                self._state_mgr.set_file_status(fp, FileStatus.PENDING)
                added.append(fp)

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------
    def add_files_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Verilog Files", self._last_dir(), _VERILOG_FILTER,
        )
        if paths:
            self.add_files(paths)

    def add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", self._last_dir()
        )
        if folder:
            self.add_folder(folder)

    # ------------------------------------------------------------------
    # Checked / all paths
    # ------------------------------------------------------------------
    def checked_paths(self) -> list[str]:
        """Return paths of all checked file items (both sections)."""
        result: list[str] = []
        for path, item in self._file_items.items():
            if item.checkState() == Qt.CheckState.Checked:
                result.append(path)
        for path, item in self._dir_file_items.items():
            if item.checkState() == Qt.CheckState.Checked:
                result.append(path)
        return result

    def all_paths(self) -> list[str]:
        return list(self._all_paths)

    # ------------------------------------------------------------------
    # Remove checked items
    # ------------------------------------------------------------------
    def remove_checked(self) -> None:
        """Remove all checked files and their now-empty ancestor dir nodes."""
        # Collect dir items that are fully checked — remove the whole subtree
        dirs_to_remove: list[QStandardItem] = []
        for dir_path, dir_item in list(self._dir_items.items()):
            if dir_item.checkState() == Qt.CheckState.Checked:
                # Only remove top-level checked dirs (children will be covered)
                parent = dir_item.parent()
                if parent is not None and parent.data(_ROLE_KIND) != "dir":
                    dirs_to_remove.append(dir_item)

        for dir_item in dirs_to_remove:
            self._remove_dir_subtree(dir_item)

        # Remove individually checked files that weren't already cleared above
        to_remove = self.checked_paths()
        for path in to_remove:
            # Files section
            item = self._file_items.pop(path, None)
            if item is not None:
                parent = item.parent() or self._model.invisibleRootItem()
                parent.removeRow(item.row())

            # Directories section
            dir_child = self._dir_file_items.pop(path, None)
            if dir_child is not None:
                dir_parent = dir_child.parent()
                if dir_parent:
                    dir_parent.removeRow(dir_child.row())

            self._all_paths.discard(path)
            self._state_mgr.remove_file(path)
            self.file_removed.emit(path)

        # Prune any dir nodes left empty after individual file removal
        self._prune_empty_dirs(self._dirs_header)

    def _remove_dir_subtree(self, dir_item: QStandardItem) -> None:
        """Recursively remove all files and subdirs under *dir_item*, then remove it."""
        for row in range(dir_item.rowCount()):
            child = dir_item.child(row, 0)
            if child is None:
                continue
            kind = child.data(_ROLE_KIND)
            if kind == "dir":
                self._remove_dir_subtree(child)
            elif kind == "file":
                fp = child.data(_ROLE_PATH)
                self._dir_file_items.pop(fp, None)
                self._all_paths.discard(fp)
                self._state_mgr.remove_file(fp)
                self.file_removed.emit(fp)

        dp = dir_item.data(_ROLE_PATH)
        self._dir_items.pop(dp, None)
        parent = dir_item.parent() or self._model.invisibleRootItem()
        parent.removeRow(dir_item.row())

    def _prune_empty_dirs(self, parent_item: QStandardItem) -> None:
        """Remove dir nodes that have no children, bottom-up."""
        row = 0
        while row < parent_item.rowCount():
            child = parent_item.child(row, 0)
            if child is None:
                row += 1
                continue
            if child.data(_ROLE_KIND) == "dir":
                self._prune_empty_dirs(child)
                if child.rowCount() == 0:
                    dp = child.data(_ROLE_PATH)
                    self._dir_items.pop(dp, None)
                    parent_item.removeRow(row)
                    continue  # don't increment — next child shifts into this row
            row += 1

    # ------------------------------------------------------------------
    # Absolute path toggle
    # ------------------------------------------------------------------
    def toggle_absolute_paths(self) -> None:
        self._show_absolute = not self._show_absolute
        for path, item in self._file_items.items():
            self._refresh_item_text(path, item)
        for path, item in self._dir_file_items.items():
            self._refresh_item_text(path, item)

    @property
    def showing_absolute(self) -> bool:
        return self._show_absolute

    # ------------------------------------------------------------------
    # Report path (unused now but kept for API compat)
    # ------------------------------------------------------------------
    def set_report_path(self, file_path: str, report_path: str) -> None:
        pass  # no detail rows any more

    # ------------------------------------------------------------------
    # Drag-drop
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        mime: QMimeData = event.mimeData()
        if not mime.hasUrls():
            return
        single: list[str] = []
        folders: list[str] = []
        for url in mime.urls():
            local = url.toLocalFile()
            p = Path(local)
            if p.is_file() and p.suffix.lower() in _VERILOG_SUFFIXES:
                single.append(str(p))
            elif p.is_dir():
                folders.append(str(p))
        if single:
            self.add_files(sorted(single))
        for folder in folders:
            self.add_folder(folder)
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------
    def _show_context_menu(self, pos) -> None:  # noqa: ANN001
        menu = QMenu(self)

        # Path copy actions (only for file/dir items)
        idx = self.indexAt(pos)
        item = self._model.itemFromIndex(idx) if idx.isValid() else None
        if item and item.data(_ROLE_KIND) in ("file", "dir"):
            copy_full = QAction("Copy Full Path", self)
            copy_full.triggered.connect(lambda: self._copy_path(item, relative=False))
            menu.addAction(copy_full)

            copy_rel = QAction("Copy Relative Path", self)
            copy_rel.triggered.connect(lambda: self._copy_path(item, relative=True))
            menu.addAction(copy_rel)

            menu.addSeparator()

        remove_act = QAction("Remove Checked", self)
        remove_act.triggered.connect(self.remove_checked)
        menu.addAction(remove_act)

        open_folder_act = QAction("Open Containing Folder", self)
        open_folder_act.triggered.connect(self._open_containing_folder)
        menu.addAction(open_folder_act)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_path(self, item: QStandardItem, *, relative: bool) -> None:
        """Copy the file/dir path to the system clipboard."""
        path = item.data(_ROLE_PATH)
        if not path:
            return
        if relative:
            try:
                path = str(Path(path).relative_to(Path.cwd()))
            except ValueError:
                pass  # fallback to absolute if not relative to cwd
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(path)

    def _open_containing_folder(self) -> None:
        # Use the item under cursor
        idx = self.currentIndex()
        item = self._model.itemFromIndex(idx)
        if not item:
            return
        path = item.data(_ROLE_PATH)
        if not path:
            return
        folder = str(Path(path).parent) if item.data(_ROLE_KIND) == "file" else path
        if sys.platform == "linux":
            subprocess.Popen(["xdg-open", folder])  # noqa: S603, S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])  # noqa: S603, S607
        else:
            os.startfile(folder)  # type: ignore[attr-defined]  # noqa: S606

    # ------------------------------------------------------------------
    # Dir checkbox → propagate to children
    # ------------------------------------------------------------------
    def _on_item_changed(self, item: QStandardItem) -> None:
        kind = item.data(_ROLE_KIND)
        if kind == "dir":
            state = item.checkState()
            self._model.itemChanged.disconnect(self._on_item_changed)
            self._set_check_recursive(item, state)
            self._model.itemChanged.connect(self._on_item_changed)
        # Notify whether any files are now checked
        if kind in ("file", "dir"):
            self.selection_changed.emit(len(self.checked_paths()) > 0)

    def _set_check_recursive(self, parent: QStandardItem, state: Qt.CheckState) -> None:
        """Recursively apply *state* to all children of *parent*."""
        for row in range(parent.rowCount()):
            child = parent.child(row, 0)
            if child is None:
                continue
            child.setCheckState(state)
            if child.data(_ROLE_KIND) == "dir":
                self._set_check_recursive(child, state)

    # ------------------------------------------------------------------
    # Double-click → emit file path
    # ------------------------------------------------------------------
    def _on_double_click(self, index) -> None:  # noqa: ANN001
        item = self._model.itemFromIndex(index)
        if item is None:
            return
        if item.data(_ROLE_KIND) != "file":
            return
        path = item.data(_ROLE_PATH)
        if path:
            self.file_double_clicked.emit(path)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _refresh_item_text(self, path: str, item: QStandardItem) -> None:
        status = self._state_mgr.file_status(path)
        icon = FILE_STATUS_ICONS[status]
        display = path if self._show_absolute else Path(path).name
        item.setText(f"{icon}  {display}")

    def _on_status_changed(self, path: str, status: FileStatus) -> None:
        item = self._file_items.get(path)
        if item is not None:
            self._refresh_item_text(path, item)
        dir_child = self._dir_file_items.get(path)
        if dir_child is not None:
            self._refresh_item_text(path, dir_child)

    def _last_dir(self) -> str:
        from gui.config import GUIConfig
        cfg = GUIConfig.load()
        return cfg.last_directory or str(Path.home())
