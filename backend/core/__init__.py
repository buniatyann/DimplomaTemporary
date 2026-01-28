"""Core components shared across all pipeline stages."""

from trojan_detector.backend.core.exceptions import (
    ClassificationError,
    GraphBuildError,
    ParseError,
    ReportGenerationError,
    SynthesisError,
)
from trojan_detector.backend.core.history import History
from trojan_detector.backend.core.outcome import StageOutcome
from trojan_detector.backend.core.pipeline import DetectionPipeline

__all__ = [
    "DetectionPipeline",
    "StageOutcome",
    "History",
    "ParseError",
    "SynthesisError",
    "GraphBuildError",
    "ClassificationError",
    "ReportGenerationError",
]
