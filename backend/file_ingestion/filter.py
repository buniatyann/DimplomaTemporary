"""ExtensionFilter for filtering files by extension."""

from __future__ import annotations

from pathlib import Path

from trojan_detector.backend.file_ingestion.models import FileType

EXTENSION_MAP: dict[str, FileType] = {
    ".v": FileType.VERILOG,
    ".vh": FileType.VERILOG,
    ".sv": FileType.SYSTEMVERILOG,
}


class ExtensionFilter:
    """Filters files by extension and determines file type."""

    def __init__(self, allowed_extensions: set[str] | None = None) -> None:
        if allowed_extensions is None:
            self._allowed = set(EXTENSION_MAP.keys())
        else:
            self._allowed = {ext if ext.startswith(".") else f".{ext}" for ext in allowed_extensions}

    def matches(self, path: Path) -> bool:
        """Check if a file has an allowed extension."""
        return path.suffix.lower() in self._allowed

    def detect_type(self, path: Path) -> FileType | None:
        """Determine the FileType for a path based on its extension."""
        return EXTENSION_MAP.get(path.suffix.lower())

    @property
    def allowed_extensions(self) -> set[str]:
        return set(self._allowed)
