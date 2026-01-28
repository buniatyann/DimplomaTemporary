"""Global configuration for the trojan detection system."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Application-wide configuration settings."""

    # File ingestion
    allowed_extensions: set[str] = Field(default={".v", ".sv", ".vh"})

    # Synthesis
    yosys_timeout: int = Field(default=300, ge=10)
    synthesis_mode: str = Field(default="elaborate")  # "elaborate" or "synthesize"

    # Graph builder
    node_feature_dim: int = Field(default=17)

    # Classifier
    architecture: str = Field(default="gcn")  # "gcn", "gat", or "gin"
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    model_weights_path: Path | None = None
    device: str | None = None  # None for auto-detect

    # Output
    default_export_formats: list[str] = Field(default=["json"])
    output_dir: Path = Field(default=Path("."))

    # Logging
    log_level: str = Field(default="INFO")

    model_config = {"arbitrary_types_allowed": True}
