"""Data models for circuit graph representations."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NodeFeatures(BaseModel):
    """Describes the node feature vector format."""

    dimensionality: int
    vocabulary: dict[str, int] = Field(default_factory=dict)
    additional_features: list[str] = Field(default_factory=list)


class CircuitGraph(BaseModel):
    """Wraps a PyTorch Geometric Data object with metadata.

    The actual torch_geometric.data.Data object is stored in the
    `graph_data` field as an arbitrary type.
    """

    graph_data: Any = None
    node_to_gate: dict[int, str] = Field(default_factory=dict)
    node_src_map: dict[int, tuple[str, int]] = Field(default_factory=dict)
    module_name: str = ""
    node_features_info: NodeFeatures | None = None
    node_count: int = 0
    edge_count: int = 0

    model_config = {"arbitrary_types_allowed": True}
