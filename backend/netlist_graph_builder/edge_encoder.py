"""EdgeEncoder for generating optional edge features."""

from __future__ import annotations

import torch

class EdgeEncoder:
    """Generates edge features capturing connection properties."""

    def __init__(self, feature_dim: int = 1) -> None:
        self._feature_dim = feature_dim

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def encode(self, bit_index: int = 0, is_inverted: bool = False) -> torch.Tensor:
        """Encode a single edge.

        Args:
            bit_index: Bus bit index for the connection.
            is_inverted: Whether the connection passes through an inverter.

        Returns:
            1D tensor of edge features.
        """
        features = [float(bit_index)]
        if self._feature_dim > 1:
            features.append(1.0 if is_inverted else 0.0)
        return torch.tensor(features[: self._feature_dim], dtype=torch.float32)

    def encode_default_batch(self, num_edges: int) -> torch.Tensor | None:
        """Create default edge features for a batch of edges.

        Returns:
            2D tensor of shape (num_edges, feature_dim), or None if no edges.
        """
        if num_edges == 0:
            return None
        return torch.zeros(num_edges, self._feature_dim, dtype=torch.float32)
