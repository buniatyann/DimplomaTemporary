"""Graph Attention Network architecture for trojan classification."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch_geometric.nn import GATConv, global_mean_pool


class GATClassifier(torch.nn.Module):
    """GAT-based binary classifier for circuit graphs.

    Learns attention weights over edges, allowing the model to focus
    on the most relevant connections for each node.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 3,
        heads: int = 4,
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.convs = torch.nn.ModuleList()
        self.convs.append(GATConv(input_dim, hidden_dim, heads=heads, concat=False))
        for _ in range(num_layers - 2):
            self.convs.append(GATConv(hidden_dim, hidden_dim, heads=heads, concat=False))
        self.convs.append(GATConv(hidden_dim, hidden_dim, heads=1, concat=False))

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
            x = F.elu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
        x = self.convs[-1](x, edge_index)

        x = global_mean_pool(x, batch)

        return self.classifier(x)

    def get_node_embeddings(
        self, x: torch.Tensor, edge_index: torch.Tensor
    ) -> torch.Tensor:
        """Return per-node embeddings before pooling."""
        for conv in self.convs[:-1]:
            x = conv(x, edge_index)
            x = F.elu(x)
        x = self.convs[-1](x, edge_index)
        return x
