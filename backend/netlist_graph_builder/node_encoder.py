"""NodeEncoder for transforming gate types into numerical feature vectors.

Feature vector layout (26 dimensions total):
    [ 0..14] one-hot gate type (matching training vocabulary)
    [15..18] basic features: fan_in, fan_out, depth, is_seq
    [19..25] structural features (computed separately by builder)
"""

from __future__ import annotations
import logging
import torch

logger = logging.getLogger(__name__)

# Vocabulary must match the training order exactly (train_local.py)
DEFAULT_VOCABULARY: dict[str, int] = {
    "INPUT": 0,
    "OUTPUT": 1,
    "WIRE": 2,
    "DFF": 3,
    "AND": 4,
    "OR": 5,
    "NOT": 6,
    "NAND": 7,
    "NOR": 8,
    "XOR": 9,
    "XNOR": 10,
    "BUF": 11,
    "MUX": 12,
    "LATCH": 13,
    "UNKNOWN": 14,
}

# Total feature dimension: 15 one-hot + 4 basic + 7 structural
FEATURE_DIM = 26
VOCAB_SIZE = 15


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
        """Total feature dimensionality: 15 one-hot + 4 basic + 7 structural = 26."""
        return FEATURE_DIM

    @property
    def unknown_types(self) -> set[str]:
        return set(self._unknown_types)

    def encode(
        self,
        canonical_type: str,
        fan_in: int = 0,
        fan_out: int = 0,
    ) -> torch.Tensor:
        """Encode a single gate into a feature vector (basic features only).

        Structural features (indices 19-25) are left as zero and must be
        filled in by the builder after edges are available.

        Args:
            canonical_type: Normalized gate type string.
            fan_in: Number of input connections.
            fan_out: Number of output connections driven.

        Returns:
            1D tensor of shape (feature_dim,).
        """
        idx = self._vocab.get(canonical_type, self._unknown_idx)
        if canonical_type not in self._vocab:
            # Map INV -> NOT (canonical alias)
            if canonical_type == "INV":
                idx = self._vocab.get("NOT", self._unknown_idx)
            else:
                self._unknown_types.add(canonical_type)

        vec = torch.zeros(FEATURE_DIM, dtype=torch.float32)

        # One-hot gate type [0..14]
        vec[idx] = 1.0

        # Basic features [15..18] — will be normalized by encode_batch
        vec[VOCAB_SIZE + 0] = float(fan_in)
        vec[VOCAB_SIZE + 1] = float(fan_out)
        vec[VOCAB_SIZE + 2] = (fan_in + 1) / (fan_out + fan_in + 2)  # depth proxy
        vec[VOCAB_SIZE + 3] = 1.0 if canonical_type == "DFF" else 0.0  # is_seq

        # Structural features [19..25] left as 0 — filled by builder
        return vec

    def encode_batch(
        self,
        types: list[str],
        fan_ins: list[int],
        fan_outs: list[int],
    ) -> torch.Tensor:
        """Encode a batch of gates into a feature matrix.

        Fan-in and fan-out are normalized by the batch maximum.

        Returns:
            2D tensor of shape (num_gates, feature_dim).
        """
        features = [
            self.encode(t, fi, fo) for t, fi, fo in zip(types, fan_ins, fan_outs)
        ]
        x = torch.stack(features)

        # Normalize fan_in/fan_out by max in the batch
        max_fan = max(
            max(fan_ins, default=1),
            max(fan_outs, default=1),
            1,
        )

        x[:, VOCAB_SIZE + 0] /= max_fan  # fan_in normalized
        x[:, VOCAB_SIZE + 1] /= max_fan  # fan_out normalized

        return x
