"""Centralised application-state tracker with Qt signals."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QObject, Signal


class AppState(Enum):
    IDLE = auto()
    PROCESSING = auto()
    CANCELLING = auto()


class FileStatus(Enum):
    PENDING = auto()
    PROCESSING = auto()
    CLEAN = auto()
    INFECTED = auto()
    ERROR = auto()


# Human-readable icons per status
FILE_STATUS_ICONS: dict[FileStatus, str] = {
    FileStatus.PENDING: "\u26aa",      # ⚪
    FileStatus.PROCESSING: "\U0001f535",  # 🔵
    FileStatus.CLEAN: "\U0001f7e2",    # 🟢
    FileStatus.INFECTED: "\U0001f534", # 🔴
    FileStatus.ERROR: "\u26a0\ufe0f",  # ⚠️
}


class AppStateManager(QObject):
    """Single source of truth for application and per-file state."""

    state_changed = Signal(object)           # AppState
    file_status_changed = Signal(str, object)  # (path, FileStatus)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = AppState.IDLE
        self._file_statuses: dict[str, FileStatus] = {}

    # ------------------------------------------------------------------
    # Application state
    # ------------------------------------------------------------------
    @property
    def state(self) -> AppState:
        return self._state

    def set_state(self, new_state: AppState) -> None:
        if new_state != self._state:
            self._state = new_state
            self.state_changed.emit(self._state)

    # ------------------------------------------------------------------
    # Per-file status
    # ------------------------------------------------------------------
    def file_status(self, path: str) -> FileStatus:
        return self._file_statuses.get(path, FileStatus.PENDING)

    def set_file_status(self, path: str, status: FileStatus) -> None:
        self._file_statuses[path] = status
        self.file_status_changed.emit(path, status)

    def remove_file(self, path: str) -> None:
        self._file_statuses.pop(path, None)

    def pending_files(self) -> list[str]:
        return [p for p, s in self._file_statuses.items() if s == FileStatus.PENDING]

    def all_files(self) -> list[str]:
        return list(self._file_statuses.keys())

    def reset_all_to_pending(self) -> None:
        for path in list(self._file_statuses):
            self.set_file_status(path, FileStatus.PENDING)
