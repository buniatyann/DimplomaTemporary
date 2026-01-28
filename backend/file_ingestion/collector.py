"""FileCollector for discovering and validating Verilog source files."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import xxhash

from trojan_detector.backend.core.history import History
from trojan_detector.backend.core.outcome import StageOutcome
from trojan_detector.backend.file_ingestion.filter import ExtensionFilter
from trojan_detector.backend.file_ingestion.models import DirectoryManifest, FileEntry

logger = logging.getLogger(__name__)

STAGE = "file_ingestion"


class FileCollector:
    """Discovers, validates, and catalogs Verilog source files."""

    def __init__(self, history: History, extension_filter: ExtensionFilter | None = None) -> None:
        self._history = history
        self._filter = extension_filter or ExtensionFilter()

    def process(self, input_path: Path) -> StageOutcome[DirectoryManifest]:
        """Collect files from a path (single file or directory).

        Returns a StageOutcome wrapping a DirectoryManifest.
        """
        self._history.begin_stage(STAGE)

        input_path = Path(input_path).resolve()

        if not input_path.exists():
            msg = f"Path does not exist: {input_path}"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        if input_path.is_file():
            return self._collect_file(input_path)
        elif input_path.is_dir():
            return self._collect_directory(input_path)
        else:
            msg = f"Path is neither a file nor a directory: {input_path}"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

    def _collect_file(self, file_path: Path) -> StageOutcome[DirectoryManifest]:
        """Validate and collect a single file."""
        entry = self._validate_file(file_path)
        if entry is None:
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(
                f"File validation failed: {file_path}", stage_name=STAGE
            )

        manifest = DirectoryManifest(root_directory=file_path.parent)
        manifest.add_file(entry)
        self._record_manifest(manifest)
        self._history.end_stage(STAGE, status="completed")
        return StageOutcome.ok(manifest, stage_name=STAGE)

    def _collect_directory(self, dir_path: Path) -> StageOutcome[DirectoryManifest]:
        """Recursively collect files from a directory."""
        manifest = DirectoryManifest(root_directory=dir_path)

        for root, _dirs, files in os.walk(dir_path):
            for fname in sorted(files):
                fpath = Path(root) / fname
                if not self._filter.matches(fpath):
                    continue
                entry = self._validate_file(fpath)
                if entry is not None:
                    manifest.add_file(entry)

        if manifest.total_count == 0:
            msg = f"No matching files found in directory: {dir_path}"
            self._history.warning(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        self._record_manifest(manifest)
        self._history.end_stage(STAGE, status="completed")
        self._history.info(
            STAGE,
            f"Collected {manifest.total_count} files "
            f"({manifest.verilog_count} Verilog, {manifest.systemverilog_count} SystemVerilog)",
        )
        return StageOutcome.ok(manifest, stage_name=STAGE)

    def _validate_file(self, file_path: Path) -> FileEntry | None:
        """Validate a single file and return a FileEntry or None on failure."""
        if not file_path.is_file():
            self._history.error(STAGE, f"Not a file: {file_path}")
            return None

        if not os.access(file_path, os.R_OK):
            self._history.error(STAGE, f"Permission denied: {file_path}")
            return None

        size = file_path.stat().st_size
        if size == 0:
            self._history.error(STAGE, f"Empty file: {file_path}")
            return None

        file_type = self._filter.detect_type(file_path)
        if file_type is None:
            self._history.error(STAGE, f"Unrecognized extension: {file_path}")
            return None

        checksum = self._compute_checksum(file_path)

        entry = FileEntry(
            path=file_path,
            size=size,
            extension=file_path.suffix.lower(),
            checksum=checksum,
            file_type=file_type,
        )

        self._history.info(
            STAGE,
            f"Validated file: {file_path.name}",
            data={
                "path": str(file_path),
                "size": size,
                "type": file_type.value,
                "checksum": checksum,
            },
        )
        return entry

    def _compute_checksum(self, file_path: Path) -> str:
        """Compute xxhash checksum for a file."""
        h = xxhash.xxh64()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _record_manifest(self, manifest: DirectoryManifest) -> None:
        """Record manifest data in history."""
        self._history.record(STAGE, "total_files", manifest.total_count)
        self._history.record(STAGE, "verilog_files", manifest.verilog_count)
        self._history.record(STAGE, "systemverilog_files", manifest.systemverilog_count)
        self._history.record(STAGE, "total_size", manifest.total_size)
        self._history.record(
            STAGE,
            "file_paths",
            [str(f.path) for f in manifest.files],
        )
