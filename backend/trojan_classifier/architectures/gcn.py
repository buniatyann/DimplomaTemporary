"""Graph Convolutional Network architecture for trojan classification."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch_geometric.nn import GCNConv, global_mean_pool


class GCNClassifier(torch.nn.Module):
    """GCN-based binary classifier for circuit graphs.

    Applies spectral convolutions over the graph structure, aggregating
    neighbor information through normalized adjacency multiplication.
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
        self.convs.append(GCNConv(input_dim, hidden_dim))
        for _ in range(num_layers - 2):
            self.convs.append(GCNConv(hidden_dim, hidden_dim))
        self.convs.append(GCNConv(hidden_dim, hidden_dim))

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
        for conv in self.convs[:-1]:
            x = conv(x, edge_index)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.convs[-1](x, edge_index)

        # Global mean pooling
        x = global_mean_pool(x, batch)

        return self.classifier(x)

    def get_node_embeddings(
        self, x: torch.Tensor, edge_index: torch.Tensor
    ) -> torch.Tensor:
        """Return per-node embeddings before pooling (for attribution)."""
        for conv in self.convs[:-1]:
            x = conv(x, edge_index)
            x = F.relu(x)
        x = self.convs[-1](x, edge_index)
        return x
