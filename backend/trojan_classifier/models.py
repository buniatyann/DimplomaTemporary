"""Data models for trojan classification results."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TrojanVerdict(str, Enum):
    """Possible classification outcomes."""

    CLEAN = "clean"
    INFECTED = "infected"
    UNCERTAIN = "uncertain"


class ClassificationResult(BaseModel):
    """Holds the classification verdict and supporting data."""

    verdict: TrojanVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    trojan_probability: float = Field(ge=0.0, le=1.0)
    gate_suspicion_scores: dict[str, float] = Field(default_factory=dict)
    model_version: str = ""
    architecture: str = ""
