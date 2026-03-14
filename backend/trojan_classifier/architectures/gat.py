"""Graph Attention Network architecture for trojan classification."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch_geometric.nn import GATConv, global_max_pool, global_mean_pool


class GATClassifier(torch.nn.Module):
    """GAT-based classifier matching the TrojanGNN training architecture.

    Includes input projection, LayerNorm, residual connections, and
    separate graph-level and node-level classification heads.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 128,
        num_layers: int = 3,
        heads: int = 4,
        dropout: float = 0.3,
    ) -> None:
        super().__init__()
        self.dropout = dropout
        self.num_layers = num_layers

        # Input projection
        self.input_proj = torch.nn.Linear(input_dim, hidden_dim)

        # GNN conv layers + LayerNorm (batch-size agnostic, no NaN in eval mode)
        self.convs = torch.nn.ModuleList()
        self.bns = torch.nn.ModuleList()
        for _ in range(num_layers):
            self.convs.append(GATConv(hidden_dim, hidden_dim, heads=heads, concat=False))
            self.bns.append(torch.nn.LayerNorm(hidden_dim))

        # Graph-level head (mean + max pooling → hidden_dim*2)
        self.graph_head = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim * 2, hidden_dim),
            torch.nn.LayerNorm(hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim // 2, 2),
        )

        # Node-level head
        self.node_head = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim, hidden_dim),
            torch.nn.LayerNorm(hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim // 2, 2),
        )

    def forward(
        self, x: torch.Tensor, edge_index: torch.Tensor, batch: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        x = F.relu(self.input_proj(x))

        for i in range(self.num_layers):
            identity = x
            x = self.convs[i](x, edge_index)
            x = self.bns[i](x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
            x = x + identity  # residual

        node_emb = x

        g_mean = global_mean_pool(node_emb, batch)
        g_max = global_max_pool(node_emb, batch)
        graph_emb = torch.cat([g_mean, g_max], dim=1)

        graph_logits = self.graph_head(graph_emb)
        node_logits = self.node_head(node_emb)

        return graph_logits, node_logits

    def get_node_embeddings(
        self, x: torch.Tensor, edge_index: torch.Tensor,
    ) -> torch.Tensor:
        """Return per-node embeddings before pooling."""
        x = F.relu(self.input_proj(x))
        for i in range(self.num_layers):
            identity = x
            x = self.convs[i](x, edge_index)
            x = self.bns[i](x)
            x = F.relu(x)
            x = x + identity
        return x
