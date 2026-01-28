"""NodeEncoder for transforming gate types into numerical feature vectors."""

from __future__ import annotations

import logging

import torch

logger = logging.getLogger(__name__)

DEFAULT_VOCABULARY: dict[str, int] = {
    "AND": 0,
    "NAND": 1,
    "OR": 2,
    "NOR": 3,
    "XOR": 4,
    "XNOR": 5,
    "NOT": 6,
    "BUF": 7,
    "INV": 8,
    "MUX": 9,
    "DFF": 10,
    "LATCH": 11,
    "INPUT": 12,
    "OUTPUT": 13,
    "UNKNOWN": 14,
}


class NodeEncoder:
    """Encodes gate type information into numerical feature vectors."""

    def __init__(self, vocabulary: dict[str, int] | None = None) -> None:
        self._vocab = vocabulary if vocabulary is not None else dict(DEFAULT_VOCABULARY)
        self._unknown_idx = self._vocab.get("UNKNOWN", len(self._vocab) - 1)
        self._unknown_types: set[str] = set()

    @property
    def vocabulary(self) -> dict[str, int]:
        return dict(self._vocab)

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    @property
    def feature_dim(self) -> int:
        """Total feature dimensionality: one-hot encoding + fan-in + fan-out."""
        return self.vocab_size + 2

    @property
    def unknown_types(self) -> set[str]:
        return set(self._unknown_types)

    def encode(
        self,
        canonical_type: str,
        fan_in: int = 0,
        fan_out: int = 0,
    ) -> torch.Tensor:
        """Encode a single gate into a feature vector.

        Args:
            canonical_type: Normalized gate type string.
            fan_in: Number of input connections.
            fan_out: Number of output connections driven.

        Returns:
            1D tensor of shape (feature_dim,).
        """
        idx = self._vocab.get(canonical_type, self._unknown_idx)
        if canonical_type not in self._vocab:
            self._unknown_types.add(canonical_type)

        one_hot = torch.zeros(self.vocab_size, dtype=torch.float32)
        one_hot[idx] = 1.0

        extras = torch.tensor([float(fan_in), float(fan_out)], dtype=torch.float32)

        return torch.cat([one_hot, extras])

    def encode_batch(
        self,
        types: list[str],
        fan_ins: list[int],
        fan_outs: list[int],
    ) -> torch.Tensor:
        """Encode a batch of gates into a feature matrix.

        Returns:
            2D tensor of shape (num_gates, feature_dim).
        """
        features = [
            self.encode(t, fi, fo) for t, fi, fo in zip(types, fan_ins, fan_outs)
        ]
        return torch.stack(features)
