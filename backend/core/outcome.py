"""StageOutcome result type for pipeline stage outputs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass
class StageOutcome(Generic[T]):
    """Wraps a pipeline stage result with success/failure status and metadata.

    Attributes:
        success: Whether the stage completed successfully.
        data: The result data if successful, None otherwise.
        error_message: Human-readable error description if failed.
        stage_name: Name of the pipeline stage that produced this outcome.
        duration: Execution time in seconds.
        metadata: Additional key-value information about the execution.
    """

    success: bool
    data: T | None = None
    error_message: str | None = None
    stage_name: str = ""
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, data: T, stage_name: str = "", **metadata: Any) -> StageOutcome[T]:
        """Create a successful outcome."""
        return cls(
            success=True,
            data=data,
            stage_name=stage_name,
            metadata=metadata,
        )

    @classmethod
    def fail(
        cls, error_message: str, stage_name: str = "", **metadata: Any
    ) -> StageOutcome[Any]:
        """Create a failure outcome."""
        return cls(
            success=False,
            error_message=error_message,
            stage_name=stage_name,
            metadata=metadata,
        )

    @classmethod
    def timed(cls, stage_name: str) -> _TimedContext:
        """Context manager that measures execution time.

        Usage::

            with StageOutcome.timed("my_stage") as ctx:
                result = do_work()
                ctx.set_data(result)
            outcome = ctx.outcome
        """
        return _TimedContext(stage_name)


class _TimedContext:
    """Context manager for timing stage execution."""

    def __init__(self, stage_name: str) -> None:
        self._stage_name = stage_name
        self._start: float = 0.0
        self._data: Any = None
        self._error: str | None = None
        self._metadata: dict[str, Any] = {}
        self.outcome: StageOutcome[Any] | None = None

    def set_data(self, data: Any) -> None:
        self._data = data

    def set_error(self, message: str) -> None:
        self._error = message

    def set_metadata(self, **kwargs: Any) -> None:
        self._metadata.update(kwargs)

    def __enter__(self) -> _TimedContext:
        self._start = time.time()
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        duration = time.time() - self._start
        if exc_val is not None:
            self.outcome = StageOutcome(
                success=False,
                error_message=str(exc_val),
                stage_name=self._stage_name,
                duration=duration,
                metadata=self._metadata,
            )
           
            return True  # suppress exception
        
        if self._error is not None:
            self.outcome = StageOutcome(
                success=False,
                error_message=self._error,
                stage_name=self._stage_name,
                duration=duration,
                metadata=self._metadata,
            )
        else:
            self.outcome = StageOutcome(
                success=True,
                data=self._data,
                stage_name=self._stage_name,
                duration=duration,
                metadata=self._metadata,
            )

        return False
