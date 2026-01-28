"""File ingestion module for discovering and validating Verilog source files."""

from trojan_detector.backend.file_ingestion.collector import FileCollector
from trojan_detector.backend.file_ingestion.filter import ExtensionFilter
from trojan_detector.backend.file_ingestion.models import DirectoryManifest, FileEntry

__all__ = ["FileCollector", "ExtensionFilter", "FileEntry", "DirectoryManifest"]
