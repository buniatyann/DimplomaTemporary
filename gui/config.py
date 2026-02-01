"""Persistent GUI configuration stored as JSON."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path.home() / ".config" / "trojan_detector"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


@dataclass
class GUIConfig:
    """Serialisable GUI preferences."""

    window_width: int = 1280
    window_height: int = 720
    splitter_sizes: list[int] = field(default_factory=lambda: [300, 700])
    auto_scroll: bool = True
    max_log_lines: int = 10_000
    last_directory: str = ""

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> GUIConfig:
        """Read config from disk, returning defaults on any error."""
        try:
            if _CONFIG_FILE.exists():
                data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        except Exception:
            logger.warning("Failed to load GUI config – using defaults", exc_info=True)
        return cls()

    def save(self) -> None:
        """Write current config to disk."""
        try:
            _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            _CONFIG_FILE.write_text(
                json.dumps(asdict(self), indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Failed to save GUI config", exc_info=True)
