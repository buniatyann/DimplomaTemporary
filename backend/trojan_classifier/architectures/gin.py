"""Graph Isomorphism Network architecture for trojan classification."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch_geometric.nn import GINConv, global_mean_pool


class GINClassifier(torch.nn.Module):
    """GIN-based binary classifier for circuit graphs.

    Maximizes expressive power through injective aggregation functions,
    often achieving best performance for structural classification tasks.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 3,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.convs = torch.nn.ModuleList()
        self.batch_norms = torch.nn.ModuleList()

        # First layer
        nn1 = torch.nn.Sequential(
            torch.nn.Linear(input_dim, hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Linear(hidden_dim, hidden_dim),
        )
        self.convs.append(GINConv(nn1))
        self.batch_norms.append(torch.nn.BatchNorm1d(hidden_dim))

        # Hidden layers
        for _ in range(num_layers - 1):
            nn_hidden = torch.nn.Sequential(
                torch.nn.Linear(hidden_dim, hidden_dim),
                torch.nn.ReLU(),
                torch.nn.Linear(hidden_dim, hidden_dim),
            )
            self.convs.append(GINConv(nn_hidden))
            self.batch_norms.append(torch.nn.BatchNorm1d(hidden_dim))

        self.classifier = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim // 2, 2),
        )
        self.dropout = dropout

    def forward(
        self, x: torch.Tensor, edge_index: torch.Tensor, batch: torch.Tensor | None = None
    ) -> torch.Tensor:
        for conv, bn in zip(self.convs, self.batch_norms):
            x = conv(x, edge_index)
            x = bn(x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)

        x = global_mean_pool(x, batch)

        return self.classifier(x)

    def get_node_embeddings(
        self, x: torch.Tensor, edge_index: torch.Tensor
    ) -> torch.Tensor:
        """Return per-node embeddings before pooling."""
        for conv, bn in zip(self.convs, self.batch_norms):
            x = conv(x, edge_index)
            x = bn(x)
            x = F.relu(x)
        return x
