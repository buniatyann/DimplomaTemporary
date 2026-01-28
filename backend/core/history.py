"""History class providing central communication between pipeline modules."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HistoryEntry:
    """A single timestamped entry in the history log."""

    timestamp: float
    stage: str
    severity: Severity
    message: str
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "stage": self.stage,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result


@dataclass
class StageRecord:
    """Tracks lifecycle and data for a single pipeline stage."""

    name: str
    started_at: float | None = None
    ended_at: float | None = None
    status: str = "pending"
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float | None:
        if self.started_at is not None and self.ended_at is not None:
            return self.ended_at - self.started_at
        return None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "duration": self.duration,
            "warnings": self.warnings,
            "errors": self.errors,
            "data": self.data,
        }
        if self.started_at is not None:
            result["started_at"] = self.started_at
        if self.ended_at is not None:
            result["ended_at"] = self.ended_at
        return result


class History:
    """Central communication channel between pipeline modules.

    Maintains a chronological log of events and per-stage structured records
    that the analysis_summarizer consumes to generate reports.
    """

    def __init__(self) -> None:
        self._created_at: float = time.time()
        self._entries: list[HistoryEntry] = []
        self._stages: dict[str, StageRecord] = {}
        self._stage_order: list[str] = []

    @property
    def created_at(self) -> float:
        return self._created_at

    @property
    def entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    @property
    def stages(self) -> dict[str, StageRecord]:
        return dict(self._stages)

    @property
    def stage_order(self) -> list[str]:
        return list(self._stage_order)

    def begin_stage(self, stage: str) -> None:
        """Mark the start of a pipeline stage."""
        record = StageRecord(name=stage, started_at=time.time(), status="running")
        self._stages[stage] = record
        self._stage_order.append(stage)
        self._log(stage, Severity.INFO, f"Stage '{stage}' started")

    def end_stage(self, stage: str, status: str = "completed") -> None:
        """Mark the end of a pipeline stage."""
        if stage in self._stages:
            self._stages[stage].ended_at = time.time()
            self._stages[stage].status = status
        self._log(stage, Severity.INFO, f"Stage '{stage}' ended with status: {status}")

    def record(self, stage: str, key: str, value: Any) -> None:
        """Store arbitrary key-value data for a stage."""
        if stage not in self._stages:
            self._stages[stage] = StageRecord(name=stage)
        self._stages[stage].data[key] = value

    def get_record(self, stage: str, key: str, default: Any = None) -> Any:
        """Retrieve recorded data from a stage."""
        if stage in self._stages:
            return self._stages[stage].data.get(key, default)
        return default

    def debug(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        self._log(stage, Severity.DEBUG, message, data)

    def info(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        self._log(stage, Severity.INFO, message, data)

    def warning(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        if stage in self._stages:
            self._stages[stage].warnings.append(message)
        self._log(stage, Severity.WARNING, message, data)

    def error(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        if stage in self._stages:
            self._stages[stage].errors.append(message)
        self._log(stage, Severity.ERROR, message, data)

    def critical(self, stage: str, message: str, data: dict[str, Any] | None = None) -> None:
        if stage in self._stages:
            self._stages[stage].errors.append(message)
        self._log(stage, Severity.CRITICAL, message, data)

    def _log(
        self,
        stage: str,
        severity: Severity,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        entry = HistoryEntry(
            timestamp=time.time(),
            stage=stage,
            severity=severity,
            message=message,
            data=data,
        )
        self._entries.append(entry)

    def get_warnings(self) -> list[HistoryEntry]:
        """Return all warning entries."""
        return [e for e in self._entries if e.severity == Severity.WARNING]

    def get_errors(self) -> list[HistoryEntry]:
        """Return all error and critical entries."""
        return [
            e
            for e in self._entries
            if e.severity in (Severity.ERROR, Severity.CRITICAL)
        ]

    def total_duration(self) -> float | None:
        """Calculate total processing duration across all stages."""
        durations = [
            s.duration for s in self._stages.values() if s.duration is not None
        ]
        return sum(durations) if durations else None

    def to_dict(self) -> dict[str, Any]:
        """Serialize history to dictionary format."""
        return {
            "created_at": self._created_at,
            "total_duration": self.total_duration(),
            "stages": {
                name: self._stages[name].to_dict() for name in self._stage_order
            },
            "entries": [e.to_dict() for e in self._entries],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize history to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
