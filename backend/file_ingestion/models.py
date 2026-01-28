"""Data models for the file ingestion module."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """Detected file type based on extension."""

    VERILOG = "verilog"
    SYSTEMVERILOG = "systemverilog"


class FileEntry(BaseModel):
    """Metadata for a single discovered file."""

    path: Path
    size: int = Field(ge=0)
    extension: str
    checksum: str
    file_type: FileType

    model_config = {"arbitrary_types_allowed": True}


class DirectoryManifest(BaseModel):
    """Aggregation of FileEntry objects for batch processing."""

    files: list[FileEntry] = Field(default_factory=list)
    root_directory: Path
    total_count: int = 0
    verilog_count: int = 0
    systemverilog_count: int = 0
    total_size: int = 0

    model_config = {"arbitrary_types_allowed": True}

    def add_file(self, entry: FileEntry) -> None:
        self.files.append(entry)
        self.total_count += 1
        self.total_size += entry.size
        if entry.file_type == FileType.VERILOG:
            self.verilog_count += 1
        elif entry.file_type == FileType.SYSTEMVERILOG:
            self.systemverilog_count += 1
