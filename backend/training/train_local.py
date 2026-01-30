#!/usr/bin/env python3
"""GNN training script for hardware trojan detection.

Features:
    - AdamW optimizer with weight decay
    - Cosine-annealing + warm-restart LR scheduler
    - Early stopping on validation F1
    - Dropout + weight decay regularization
    - Class-imbalance handling (weighted loss + oversampling)
    - Graph data augmentation (node drop, edge perturb, feature mask, subgraph)
    - Full GPU acceleration with mixed-precision (AMP)
    - Comprehensive sklearn metrics
    - Train / validation / test splits via sklearn train_test_split (60/20/20)
    - Matplotlib training history plots (loss, accuracy, F1, LR)

Usage:
    python -m backend.training.train_local --architecture gcn
    python -m backend.training.train_local --architecture gat --epochs 200
    python -m backend.training.train_local --data-dir backend/training/data/trusthub_large/raw
"""

from __future__ import annotations

import argparse
import copy
import logging
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
import matplotlib
matplotlib.use("Agg")  # non-interactive backend for headless environments
import matplotlib.pyplot as plt
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from torch.amp import GradScaler, autocast
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train GNN on trojan benchmarks")
    p.add_argument("--architecture", choices=["gcn", "gat", "gin"], default="gcn")
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--hidden-dim", type=int, default=128)
    p.add_argument("--num-layers", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--weight-decay", type=float, default=1e-2)
    p.add_argument("--dropout", type=float, default=0.3)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--patience", type=int, default=30, help="Early-stopping patience")
    p.add_argument("--augment", action="store_true", default=True, help="Enable graph augmentation")
    p.add_argument("--no-augment", dest="augment", action="store_false")
    p.add_argument("--oversample", action="store_true", default=True, help="Oversample minority class")
    p.add_argument("--no-oversample", dest="oversample", action="store_false")
    p.add_argument("--data-dir", type=Path, default=None, help="Data directory override")
    p.add_argument("--plot-dir", type=Path, default=None, help="Directory to save training plots (default: backend/training/plots)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("-v", "--verbose", action="count", default=0)
    return p.parse_args()


def setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = True  # faster convs for fixed-size inputs


# ---------------------------------------------------------------------------
# Verilog parser
# ---------------------------------------------------------------------------

TROJAN_NAME_PATTERNS = [
    r"(?i)trojan", r"(?i)^tj_", r"(?i)_tj$", r"(?i)trigger",
    r"(?i)payload", r"(?i)^mal_", r"(?i)^ht_", r"(?i)backdoor",
    r"(?i)leak", r"(?i)snoop", r"(?i)capture", r"(?i)hidden",
    r"(?i)kill", r"(?i)armed", r"(?i)corrupt",
]


def is_trojan_name(name: str) -> bool:
    return any(re.search(p, name) for p in TROJAN_NAME_PATTERNS)


TYPE_VOCAB = [
    "INPUT", "OUTPUT", "WIRE", "DFF", "AND", "OR", "NOT", "NAND",
    "NOR", "XOR", "XNOR", "BUF", "MUX", "LATCH", "UNKNOWN",
]
TYPE_TO_IDX = {t: i for i, t in enumerate(TYPE_VOCAB)}
FEATURE_DIM = len(TYPE_VOCAB) + 4  # one-hot + fan_in + fan_out + depth + is_seq


def parse_verilog_simple(file_path: Path) -> tuple[list[str], list[tuple[int, int]], list[str]]:
    """Extract signals and connectivity from a Verilog file."""
    content = file_path.read_text(errors="replace")

    nodes: list[str] = []
    node_types: list[str] = []
    seen: set[str] = set()

    def _add(name: str, ntype: str) -> None:
        if name not in seen:
            seen.add(name)
            nodes.append(name)
            node_types.append(ntype)

    for m in re.finditer(r'\binput\s+(?:\[\d+:\d+\])?\s*(\w+)', content):
        _add(m.group(1), "INPUT")
    for m in re.finditer(r'\boutput\s+(?:reg\s+)?(?:\[\d+:\d+\])?\s*(\w+)', content):
        _add(m.group(1), "OUTPUT")
    for m in re.finditer(r'\bwire\s+(?:\[\d+:\d+\])?\s*(\w+)', content):
        _add(m.group(1), "WIRE")
    for m in re.finditer(r'\breg\s+(?:\[\d+:\d+\])?\s*(\w+)', content):
        _add(m.group(1), "DFF")

    gate_pats = [
        (r'\band\s+(\w+)\s*\(', "AND"), (r'\bor\s+(\w+)\s*\(', "OR"),
        (r'\bnot\s+(\w+)\s*\(', "NOT"), (r'\bnand\s+(\w+)\s*\(', "NAND"),
        (r'\bnor\s+(\w+)\s*\(', "NOR"), (r'\bxor\s+(\w+)\s*\(', "XOR"),
        (r'\bxnor\s+(\w+)\s*\(', "XNOR"), (r'\bbuf\s+(\w+)\s*\(', "BUF"),
    ]
    for pat, gt in gate_pats:
        for m in re.finditer(pat, content):
            _add(m.group(1), gt)

    node_map = {name: i for i, name in enumerate(nodes)}
    edges: list[tuple[int, int]] = []

    for m in re.finditer(r'(\w+)\s*<?=\s*([^;]+);', content):
        tgt = m.group(1)
        if tgt not in node_map:
            continue
        ti = node_map[tgt]
        for src in re.findall(r'\b(\w+)\b', m.group(2)):
            if src in node_map and src != tgt:
                edges.append((node_map[src], ti))

    return nodes, edges, node_types


def create_graph_from_verilog(file_path: Path, is_trojan_file: bool) -> Data | None:
    """Build a PyG Data object from a Verilog source file."""
    try:
        nodes, edges, node_types = parse_verilog_simple(file_path)
    except Exception as e:
        logger.debug(f"Parse error {file_path}: {e}")
        return None

    if len(nodes) < 3:
        return None

    num_nodes = len(nodes)

    # --- node features ---
    x = torch.zeros((num_nodes, FEATURE_DIM), dtype=torch.float)

    fan_in = [0] * num_nodes
    fan_out = [0] * num_nodes
    for s, t in edges:
        fan_out[s] += 1
        fan_in[t] += 1
    max_fan = max(max(fan_in, default=1), max(fan_out, default=1), 1)

    for i, (_, ntype) in enumerate(zip(nodes, node_types)):
        idx = TYPE_TO_IDX.get(ntype, TYPE_TO_IDX["UNKNOWN"])
        x[i, idx] = 1.0
        x[i, -4] = fan_in[i] / max_fan
        x[i, -3] = fan_out[i] / max_fan
        # simple topological depth estimate (normalised)
        x[i, -2] = (fan_in[i] + 1) / (fan_out[i] + fan_in[i] + 2)
        # sequential flag
        x[i, -1] = 1.0 if ntype == "DFF" else 0.0

    # --- edges ---
    if edges:
        edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
    else:
        edge_index = torch.stack([
            torch.arange(num_nodes, dtype=torch.long),
            torch.arange(num_nodes, dtype=torch.long),
        ])

    # --- labels ---
    node_labels = torch.zeros(num_nodes, dtype=torch.long)
    if is_trojan_file:
        for i, name in enumerate(nodes):
            if is_trojan_name(name):
                node_labels[i] = 1

    graph_label = torch.tensor([1 if is_trojan_file else 0], dtype=torch.long)

    data = Data(
        x=x, edge_index=edge_index, y=graph_label,
        node_labels=node_labels, num_nodes=num_nodes,
    )
    # Store metadata as plain Python attrs (not in PyG's _store)
    data._file_path = str(file_path)
    data._node_names = nodes
    return data


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_benchmark_files(
    data_dir: Path | None = None,
    seed: int = 42,
) -> tuple[list[Data], list[Data], list[Data]]:
    """Load benchmarks and split into train / val / test (60/20/20).

    Uses sklearn.model_selection.train_test_split with stratification on the
    graph label so that each split preserves the trojan/clean ratio.
    """
    base = Path(__file__).parent / "data"

    search_dirs: list[Path] = []
    if data_dir is not None:
        search_dirs.append(data_dir)
    else:
        for name in ("trusthub/raw", "trusthub_large/raw"):
            d = base / name
            if d.exists():
                search_dirs.append(d)

    if not search_dirs:
        raise FileNotFoundError(f"No data directory found under {base}")

    all_graphs: list[Data] = []

    for sdir in search_dirs:
        benchmarks = sorted(sdir.iterdir())
        trojan_dirs = [b for b in benchmarks if b.is_dir() and ("_T" in b.name or "-T" in b.name)]
        golden_dirs = [b for b in benchmarks if b.is_dir() and "_T" not in b.name and "-T" not in b.name]

        logger.info(f"[{sdir.name}] Found {len(trojan_dirs)} trojan, {len(golden_dirs)} golden dirs")

        for td in trojan_dirs:
            for vf in td.glob("*.v"):
                g = create_graph_from_verilog(vf, is_trojan_file=True)
                if g is not None:
                    all_graphs.append(g)

        for gd in golden_dirs:
            for vf in gd.glob("*.v"):
                g = create_graph_from_verilog(vf, is_trojan_file=False)
                if g is not None:
                    all_graphs.append(g)

    n_trojan = sum(1 for g in all_graphs if g.y.item() == 1)
    n_clean = len(all_graphs) - n_trojan
    logger.info(f"Total graphs: {len(all_graphs)} — {n_trojan} trojan, {n_clean} clean")

    # --- stratified train / val / test split (60 / 20 / 20) ---
    labels = [int(g.y.item()) for g in all_graphs]

    # First split: 80% train+val, 20% test
    trainval, test_graphs, trainval_labels, _ = train_test_split(
        all_graphs, labels, test_size=0.20, random_state=seed, stratify=labels,
    )
    # Second split: from 80% take 75% train, 25% val -> overall 60/20/20
    train_graphs, val_graphs, _, _ = train_test_split(
        trainval, trainval_labels, test_size=0.25, random_state=seed, stratify=trainval_labels,
    )

    def _dist(gs: list[Data]) -> str:
        t = sum(1 for g in gs if g.y.item() == 1)
        return f"{len(gs)} ({t} trojan, {len(gs)-t} clean)"

    logger.info(f"  Train : {_dist(train_graphs)}")
    logger.info(f"  Val   : {_dist(val_graphs)}")
    logger.info(f"  Test  : {_dist(test_graphs)}")

    return train_graphs, val_graphs, test_graphs


# ---------------------------------------------------------------------------
# Graph data augmentation
# ---------------------------------------------------------------------------

class GraphAugmentor:
    """Stochastic graph augmentation for training robustness."""

    def __init__(
        self,
        node_drop_rate: float = 0.1,
        edge_perturb_rate: float = 0.05,
        feature_mask_rate: float = 0.15,
        subgraph_rate: float = 0.2,
    ):
        self.node_drop_rate = node_drop_rate
        self.edge_perturb_rate = edge_perturb_rate
        self.feature_mask_rate = feature_mask_rate
        self.subgraph_rate = subgraph_rate

    def __call__(self, data: Data) -> Data:
        """Apply a random augmentation."""
        r = random.random()
        if r < 0.25:
            return self.node_dropping(data)
        elif r < 0.50:
            return self.edge_perturbation(data)
        elif r < 0.75:
            return self.feature_masking(data)
        else:
            return self.subgraph_sampling(data)

    def node_dropping(self, data: Data) -> Data:
        """Randomly drop nodes (and their edges)."""
        n = data.num_nodes
        keep_mask = torch.rand(n) > self.node_drop_rate
        if keep_mask.sum() < 3:
            return data  # keep at least 3 nodes

        keep_idx = keep_mask.nonzero(as_tuple=True)[0]
        mapping = torch.full((n,), -1, dtype=torch.long)
        mapping[keep_idx] = torch.arange(keep_idx.size(0))

        new_x = data.x[keep_idx]
        new_node_labels = data.node_labels[keep_idx]

        src, dst = data.edge_index
        edge_mask = keep_mask[src] & keep_mask[dst]
        new_edges = data.edge_index[:, edge_mask]
        new_edges = mapping[new_edges]

        return Data(
            x=new_x, edge_index=new_edges, y=data.y,
            node_labels=new_node_labels, num_nodes=new_x.size(0),
        )

    def edge_perturbation(self, data: Data) -> Data:
        """Randomly add/remove edges."""
        edge_index = data.edge_index.clone()
        num_edges = edge_index.size(1)
        n = data.num_nodes

        # Remove edges
        n_remove = int(num_edges * self.edge_perturb_rate)
        if n_remove > 0 and num_edges > n_remove:
            keep = torch.randperm(num_edges)[n_remove:]
            edge_index = edge_index[:, keep]

        # Add edges
        n_add = int(num_edges * self.edge_perturb_rate)
        if n_add > 0 and n > 1:
            new_src = torch.randint(0, n, (n_add,))
            new_dst = torch.randint(0, n, (n_add,))
            valid = new_src != new_dst
            if valid.any():
                added = torch.stack([new_src[valid], new_dst[valid]])
                edge_index = torch.cat([edge_index, added], dim=1)

        return Data(
            x=data.x.clone(), edge_index=edge_index, y=data.y,
            node_labels=data.node_labels.clone(), num_nodes=data.num_nodes,
        )

    def feature_masking(self, data: Data) -> Data:
        """Randomly mask node features with zeros."""
        x = data.x.clone()
        mask = torch.rand_like(x) < self.feature_mask_rate
        x[mask] = 0.0
        return Data(
            x=x, edge_index=data.edge_index.clone(), y=data.y,
            node_labels=data.node_labels.clone(), num_nodes=data.num_nodes,
        )

    def subgraph_sampling(self, data: Data) -> Data:
        """Sample a connected subgraph via BFS from a random root."""
        n = data.num_nodes
        keep_n = max(3, int(n * (1.0 - self.subgraph_rate)))

        # Build adjacency list
        adj: dict[int, list[int]] = {i: [] for i in range(n)}
        src, dst = data.edge_index
        for s, d in zip(src.tolist(), dst.tolist()):
            adj[s].append(d)
            adj[d].append(s)

        root = random.randint(0, n - 1)
        visited = {root}
        queue = [root]
        while queue and len(visited) < keep_n:
            cur = queue.pop(0)
            for nb in adj[cur]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
                    if len(visited) >= keep_n:
                        break

        keep_idx = torch.tensor(sorted(visited), dtype=torch.long)
        mapping = torch.full((n,), -1, dtype=torch.long)
        mapping[keep_idx] = torch.arange(keep_idx.size(0))

        new_x = data.x[keep_idx]
        new_nl = data.node_labels[keep_idx]

        edge_mask = torch.zeros(data.edge_index.size(1), dtype=torch.bool)
        for i in range(data.edge_index.size(1)):
            if data.edge_index[0, i].item() in visited and data.edge_index[1, i].item() in visited:
                edge_mask[i] = True
        new_ei = mapping[data.edge_index[:, edge_mask]]

        return Data(
            x=new_x, edge_index=new_ei, y=data.y,
            node_labels=new_nl, num_nodes=new_x.size(0),
        )


class AugmentedDataset:
    """Wraps a list of graphs and returns augmented copies."""

    def __init__(self, graphs: list[Data], augmentor: GraphAugmentor, copies: int = 2):
        self.original = graphs
        self.augmentor = augmentor
        self.copies = copies
        self._build()

    def _build(self) -> None:
        self.graphs = list(self.original)
        for _ in range(self.copies):
            for g in self.original:
                self.graphs.append(self.augmentor(g))
        random.shuffle(self.graphs)

    def __len__(self) -> int:
        return len(self.graphs)

    def __getitem__(self, idx: int) -> Data:
        return self.graphs[idx]


# ---------------------------------------------------------------------------
# Class imbalance: oversample minority class
# ---------------------------------------------------------------------------

def oversample_minority(graphs: list[Data]) -> list[Data]:
    """Duplicate minority-class graphs until classes are balanced."""
    trojan = [g for g in graphs if g.y.item() == 1]
    clean = [g for g in graphs if g.y.item() == 0]

    if not trojan or not clean:
        return graphs

    majority, minority = (clean, trojan) if len(clean) >= len(trojan) else (trojan, clean)
    ratio = len(majority) / len(minority)

    oversampled = list(majority) + minority * int(ratio)
    # add leftover
    remainder = len(majority) - len(minority) * int(ratio)
    if remainder > 0:
        oversampled.extend(random.sample(minority, min(remainder, len(minority))))

    random.shuffle(oversampled)
    logger.info(f"Oversampled: {len(majority)} majority + {len(minority)}x{int(ratio)} minority = {len(oversampled)}")
    return oversampled


# ---------------------------------------------------------------------------
# GNN model (deeper, with BatchNorm, configurable dropout, residual connections)
# ---------------------------------------------------------------------------

class TrojanGNN(torch.nn.Module):
    """Multi-layer GNN with BatchNorm, residual connections, and separate heads."""

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 128,
        num_layers: int = 4,
        dropout: float = 0.3,
        architecture: str = "gcn",
    ):
        super().__init__()
        self.architecture = architecture
        self.dropout = dropout
        self.num_layers = num_layers

        from torch_geometric.nn import BatchNorm

        # Input projection
        self.input_proj = torch.nn.Linear(input_dim, hidden_dim)

        # GNN conv layers
        self.convs = torch.nn.ModuleList()
        self.bns = torch.nn.ModuleList()

        for _ in range(num_layers):
            self.convs.append(self._make_conv(hidden_dim, hidden_dim, architecture))
            self.bns.append(BatchNorm(hidden_dim))

        # Graph-level head
        self.graph_head = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim * 2, hidden_dim),  # *2 for concat(mean, max)
            torch.nn.BatchNorm1d(hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim // 2, 2),
        )

        # Node-level head
        self.node_head = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim, hidden_dim // 2),
            torch.nn.ReLU(),
            torch.nn.Dropout(dropout),
            torch.nn.Linear(hidden_dim // 2, 2),
        )

    @staticmethod
    def _make_conv(in_dim: int, out_dim: int, arch: str):
        if arch == "gcn":
            from torch_geometric.nn import GCNConv
            return GCNConv(in_dim, out_dim)
        elif arch == "gat":
            from torch_geometric.nn import GATConv
            return GATConv(in_dim, out_dim, heads=4, concat=False)
        elif arch == "gin":
            from torch_geometric.nn import GINConv
            nn = torch.nn.Sequential(
                torch.nn.Linear(in_dim, out_dim),
                torch.nn.BatchNorm1d(out_dim),
                torch.nn.ReLU(),
                torch.nn.Linear(out_dim, out_dim),
            )
            return GINConv(nn)
        raise ValueError(f"Unknown architecture: {arch}")

    def forward(self, x, edge_index, batch=None):
        from torch_geometric.nn import global_max_pool, global_mean_pool

        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        # Project input
        x = F.relu(self.input_proj(x))

        # GNN layers with residual connections
        for i in range(self.num_layers):
            identity = x
            x = self.convs[i](x, edge_index)
            x = self.bns[i](x)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)
            x = x + identity  # residual

        node_emb = x

        # Graph pooling: concat mean + max
        g_mean = global_mean_pool(node_emb, batch)
        g_max = global_max_pool(node_emb, batch)
        graph_emb = torch.cat([g_mean, g_max], dim=1)

        graph_logits = self.graph_head(graph_emb)
        node_logits = self.node_head(node_emb)

        return graph_logits, node_logits

    def get_node_embeddings(self, x, edge_index):
        x = F.relu(self.input_proj(x))
        for i in range(self.num_layers):
            identity = x
            x = self.convs[i](x, edge_index)
            x = self.bns[i](x)
            x = F.relu(x)
            x = x + identity
        return x


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(y_true: list, y_pred: list, y_proba: list | None = None, prefix: str = "") -> dict:
    y_true_a = np.array(y_true)
    y_pred_a = np.array(y_pred)

    m: dict = {}
    m[f"{prefix}accuracy"] = accuracy_score(y_true_a, y_pred_a)
    m[f"{prefix}precision"] = precision_score(y_true_a, y_pred_a, zero_division=0)
    m[f"{prefix}recall"] = recall_score(y_true_a, y_pred_a, zero_division=0)
    m[f"{prefix}f1"] = f1_score(y_true_a, y_pred_a, zero_division=0)

    if y_proba is not None and len(np.unique(y_true_a)) > 1:
        try:
            m[f"{prefix}roc_auc"] = roc_auc_score(y_true_a, np.array(y_proba))
        except ValueError:
            m[f"{prefix}roc_auc"] = 0.0

    cm = confusion_matrix(y_true_a, y_pred_a, labels=[0, 1])
    m[f"{prefix}confusion_matrix"] = cm
    m[f"{prefix}tn"] = int(cm[0, 0])
    m[f"{prefix}fp"] = int(cm[0, 1])
    m[f"{prefix}fn"] = int(cm[1, 0])
    m[f"{prefix}tp"] = int(cm[1, 1])

    return m


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_training_history(history: list[dict], architecture: str, plot_dir: Path) -> None:
    """Save matplotlib figures of training history."""
    plot_dir.mkdir(parents=True, exist_ok=True)
    epochs = [r["epoch"] for r in history]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f"Training History — {architecture.upper()}", fontsize=15, fontweight="bold")

    # --- 1. Loss ---
    ax = axes[0, 0]
    ax.plot(epochs, [r["train_loss"] for r in history], label="Train Loss", linewidth=1.5)
    ax.plot(epochs, [r["val_loss"] for r in history], label="Val Loss", linewidth=1.5)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Loss")
    ax.set_title("Loss")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # --- 2. Accuracy ---
    ax = axes[0, 1]
    ax.plot(epochs, [r["train_accuracy"] for r in history], label="Train Acc", linewidth=1.5)
    ax.plot(epochs, [r["val_accuracy"] for r in history], label="Val Acc", linewidth=1.5)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy")
    ax.set_ylim(-0.05, 1.05)
    ax.legend()
    ax.grid(True, alpha=0.3)

    # --- 3. F1 Score ---
    ax = axes[1, 0]
    ax.plot(epochs, [r["train_f1"] for r in history], label="Train F1", linewidth=1.5)
    ax.plot(epochs, [r["val_f1"] for r in history], label="Val F1", linewidth=1.5)
    if history[0].get("train_node_f1") is not None:
        ax.plot(epochs, [r.get("train_node_f1", 0) for r in history], label="Train Node F1", linestyle="--", linewidth=1)
        ax.plot(epochs, [r.get("val_node_f1", 0) for r in history], label="Val Node F1", linestyle="--", linewidth=1)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("F1 Score")
    ax.set_title("F1 Score (graph & node level)")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # --- 4. Learning Rate ---
    ax = axes[1, 1]
    ax.plot(epochs, [r["lr"] for r in history], color="tab:green", linewidth=1.5)
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Learning Rate")
    ax.set_title("Learning Rate Schedule")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    path = plot_dir / f"{architecture}_training_history.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved training history plot: {path}")


def plot_test_confusion_matrix(cm: np.ndarray, architecture: str, plot_dir: Path) -> None:
    """Save a confusion matrix heatmap for the test set."""
    plot_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(5, 4))
    im = ax.imshow(cm, interpolation="nearest", cmap=plt.cm.Blues)
    ax.figure.colorbar(im, ax=ax)

    classes = ["Clean", "Trojan"]
    ax.set(
        xticks=[0, 1], yticks=[0, 1],
        xticklabels=classes, yticklabels=classes,
        xlabel="Predicted", ylabel="True",
        title=f"Test Confusion Matrix — {architecture.upper()}",
    )

    thresh = cm.max() / 2.0
    for i in range(2):
        for j in range(2):
            ax.text(j, i, format(cm[i, j], "d"),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black",
                    fontsize=16, fontweight="bold")

    plt.tight_layout()
    path = plot_dir / f"{architecture}_test_confusion_matrix.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved test confusion matrix: {path}")


# ---------------------------------------------------------------------------
# Early stopping
# ---------------------------------------------------------------------------

class EarlyStopping:
    def __init__(self, patience: int = 30, min_delta: float = 1e-4):
        self.patience = patience
        self.min_delta = min_delta
        self.best_score: float | None = None
        self.counter = 0
        self.should_stop = False

    def step(self, score: float) -> bool:
        """Higher score is better (e.g. F1). Returns True when training should stop."""
        if self.best_score is None or score > self.best_score + self.min_delta:
            self.best_score = score
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
        return self.should_stop


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_model(
    model: torch.nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    test_loader: DataLoader,
    epochs: int,
    lr: float,
    weight_decay: float,
    patience: int,
    device: torch.device,
) -> dict:
    # ---- optimizer: AdamW ----
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    # ---- LR scheduler: cosine annealing with warm restarts ----
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=20, T_mult=2, eta_min=1e-6,
    )

    # ---- mixed-precision scaler for GPU ----
    use_amp = device.type == "cuda"
    scaler = GradScaler(device=device.type, enabled=use_amp)

    # ---- early stopping ----
    stopper = EarlyStopping(patience=patience)

    # ---- pre-compute global class weights for node loss ----
    all_node_labels = []
    for batch in train_loader:
        if hasattr(batch, "node_labels"):
            all_node_labels.extend(batch.node_labels.numpy())
    all_node_labels = np.array(all_node_labels)
    n_clean_nodes = (all_node_labels == 0).sum()
    n_trojan_nodes = (all_node_labels == 1).sum()
    if n_trojan_nodes > 0:
        node_weight = torch.tensor(
            [1.0, float(n_clean_nodes) / float(n_trojan_nodes)], device=device,
        )
    else:
        node_weight = torch.tensor([1.0, 1.0], device=device)
    logger.info(f"Node class weights: clean=1.0, trojan={node_weight[1]:.2f}")

    # ---- graph-level class weights ----
    graph_labels = []
    for batch in train_loader:
        graph_labels.extend(batch.y.numpy())
    graph_labels = np.array(graph_labels)
    n_clean_g = (graph_labels == 0).sum()
    n_trojan_g = (graph_labels == 1).sum()
    if n_trojan_g > 0 and n_clean_g > 0:
        graph_weight = torch.tensor(
            [1.0, float(n_clean_g) / float(n_trojan_g)], device=device,
        )
    else:
        graph_weight = torch.tensor([1.0, 1.0], device=device)
    logger.info(f"Graph class weights: clean=1.0, trojan={graph_weight[1]:.2f}")

    best_val_loss = float("inf")
    best_val_f1 = 0.0
    best_state = None
    history: list[dict] = []

    for epoch in range(1, epochs + 1):
        t0 = time.time()

        # ===== TRAIN =====
        model.train()
        train_loss = 0.0
        train_total = 0
        train_labels_ep: list[int] = []
        train_preds_ep: list[int] = []
        train_probs_ep: list[float] = []
        train_nlabels: list[int] = []
        train_npreds: list[int] = []

        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad(set_to_none=True)

            with autocast(device_type=device.type, enabled=use_amp):
                graph_logits, node_logits = model(batch.x, batch.edge_index, batch.batch)

                g_loss = F.cross_entropy(graph_logits, batch.y, weight=graph_weight)

                if hasattr(batch, "node_labels"):
                    n_loss = F.cross_entropy(node_logits, batch.node_labels, weight=node_weight)
                    train_nlabels.extend(batch.node_labels.cpu().numpy())
                    train_npreds.extend(node_logits.argmax(1).detach().cpu().numpy())
                else:
                    n_loss = torch.tensor(0.0, device=device)

                loss = 0.6 * g_loss + 0.4 * n_loss  # weight graph-level more

            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item() * batch.num_graphs
            train_total += batch.num_graphs

            probs = F.softmax(graph_logits.detach(), dim=1)[:, 1]
            train_labels_ep.extend(batch.y.cpu().numpy())
            train_preds_ep.extend(graph_logits.argmax(1).detach().cpu().numpy())
            train_probs_ep.extend(probs.cpu().numpy())

        scheduler.step()
        train_loss /= max(train_total, 1)
        train_m = compute_metrics(train_labels_ep, train_preds_ep, train_probs_ep, "train_")

        # ===== VALIDATE =====
        model.eval()
        val_loss = 0.0
        val_total = 0
        val_labels_ep: list[int] = []
        val_preds_ep: list[int] = []
        val_probs_ep: list[float] = []
        val_nlabels: list[int] = []
        val_npreds: list[int] = []

        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                with autocast(device_type=device.type, enabled=use_amp):
                    gl, nl = model(batch.x, batch.edge_index, batch.batch)
                    g_loss = F.cross_entropy(gl, batch.y, weight=graph_weight)
                    if hasattr(batch, "node_labels"):
                        n_loss = F.cross_entropy(nl, batch.node_labels, weight=node_weight)
                        val_nlabels.extend(batch.node_labels.cpu().numpy())
                        val_npreds.extend(nl.argmax(1).cpu().numpy())
                    else:
                        n_loss = torch.tensor(0.0, device=device)
                    loss = 0.6 * g_loss + 0.4 * n_loss

                val_loss += loss.item() * batch.num_graphs
                val_total += batch.num_graphs
                probs = F.softmax(gl, dim=1)[:, 1]
                val_labels_ep.extend(batch.y.cpu().numpy())
                val_preds_ep.extend(gl.argmax(1).cpu().numpy())
                val_probs_ep.extend(probs.cpu().numpy())

        val_loss /= max(val_total, 1)
        val_m = compute_metrics(val_labels_ep, val_preds_ep, val_probs_ep, "val_")

        tn_m = compute_metrics(train_nlabels, train_npreds, prefix="train_node_") if train_nlabels else {}
        vn_m = compute_metrics(val_nlabels, val_npreds, prefix="val_node_") if val_nlabels else {}

        # ---- record ----
        rec = {
            "epoch": epoch, "train_loss": train_loss, "val_loss": val_loss,
            "lr": optimizer.param_groups[0]["lr"],
            **{k: v for k, v in train_m.items() if "confusion" not in k},
            **{k: v for k, v in val_m.items() if "confusion" not in k},
            **{k: v for k, v in tn_m.items() if "confusion" not in k},
            **{k: v for k, v in vn_m.items() if "confusion" not in k},
        }
        history.append(rec)

        elapsed = time.time() - t0

        if epoch % 10 == 0 or epoch == 1 or epoch == epochs:
            lr_now = optimizer.param_groups[0]["lr"]
            logger.info(
                f"Epoch {epoch:3d}/{epochs} ({elapsed:.1f}s) lr={lr_now:.2e} | "
                f"Train Loss={train_loss:.4f} Acc={train_m['train_accuracy']:.3f} F1={train_m['train_f1']:.3f} | "
                f"Val Loss={val_loss:.4f} Acc={val_m['val_accuracy']:.3f} F1={val_m['val_f1']:.3f}"
            )
            if vn_m:
                logger.info(
                    f"         Node | Train F1={tn_m.get('train_node_f1',0):.3f} | "
                    f"Val F1={vn_m.get('val_node_f1',0):.3f}"
                )

        # ---- checkpoint ----
        cur_f1 = val_m["val_f1"]
        improved = False
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            improved = True
        if cur_f1 > best_val_f1:
            best_val_f1 = cur_f1
            improved = True

        if improved:
            best_state = copy.deepcopy(model.state_dict())
            weights_dir = Path(__file__).parent.parent / "trojan_classifier" / "weights"
            weights_dir.mkdir(parents=True, exist_ok=True)
            torch.save(best_state, weights_dir / f"{model.architecture}_weights.pt")
            if epoch % 10 == 0 or epoch == 1:
                logger.info(f"  -> Saved best (val_loss={val_loss:.4f}, val_f1={cur_f1:.4f})")

        # ---- early stopping ----
        if stopper.step(cur_f1):
            logger.info(f"Early stopping at epoch {epoch} (no improvement for {patience} epochs)")
            break

    # Restore best weights
    if best_state is not None:
        model.load_state_dict(best_state)

    # ===== TEST SET EVALUATION =====
    model.eval()
    test_labels_all: list[int] = []
    test_preds_all: list[int] = []
    test_probs_all: list[float] = []
    test_nlabels_all: list[int] = []
    test_npreds_all: list[int] = []

    with torch.no_grad():
        for batch in test_loader:
            batch = batch.to(device)
            with autocast(device_type=device.type, enabled=use_amp):
                gl, nl = model(batch.x, batch.edge_index, batch.batch)

            probs = F.softmax(gl, dim=1)[:, 1]
            test_labels_all.extend(batch.y.cpu().numpy())
            test_preds_all.extend(gl.argmax(1).cpu().numpy())
            test_probs_all.extend(probs.cpu().numpy())

            if hasattr(batch, "node_labels"):
                test_nlabels_all.extend(batch.node_labels.cpu().numpy())
                test_npreds_all.extend(nl.argmax(1).cpu().numpy())

    test_m = compute_metrics(test_labels_all, test_preds_all, test_probs_all, "test_")
    test_node_m = compute_metrics(test_nlabels_all, test_npreds_all, prefix="test_node_") if test_nlabels_all else {}

    return {
        "history": history,
        "best_val_loss": best_val_loss,
        "best_val_f1": best_val_f1,
        "final_train_metrics": train_m,
        "final_val_metrics": val_m,
        "final_train_node_metrics": tn_m,
        "final_val_node_metrics": vn_m,
        "test_metrics": test_m,
        "test_node_metrics": test_node_m,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    seed_everything(args.seed)

    logger.info("=" * 70)
    logger.info("TrustHub GNN Trojan Detection Training")
    logger.info("=" * 70)
    logger.info(f"Architecture : {args.architecture}")
    logger.info(f"Epochs       : {args.epochs}")
    logger.info(f"Hidden dim   : {args.hidden_dim}")
    logger.info(f"Num layers   : {args.num_layers}")
    logger.info(f"LR           : {args.lr}")
    logger.info(f"Weight decay : {args.weight_decay}")
    logger.info(f"Dropout      : {args.dropout}")
    logger.info(f"Batch size   : {args.batch_size}")
    logger.info(f"Patience     : {args.patience}")
    logger.info(f"Augmentation : {args.augment}")
    logger.info(f"Oversample   : {args.oversample}")

    # ---- device ----
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        logger.info(f"GPU          : {torch.cuda.get_device_name(0)}")
        logger.info(f"GPU Memory   : {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        logger.info("WARNING: Training on CPU — this will be slow!")

    # ---- data (train / val / test split via sklearn) ----
    try:
        train_graphs, val_graphs, test_graphs = load_benchmark_files(args.data_dir, seed=args.seed)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1

    if not train_graphs:
        logger.error("No training graphs!")
        return 1

    # ---- oversample minority class ----
    if args.oversample:
        train_graphs = oversample_minority(train_graphs)

    # ---- augmentation ----
    if args.augment and len(train_graphs) > 0:
        augmentor = GraphAugmentor()
        aug_copies = max(1, 200 // max(len(train_graphs), 1))  # aim for ~200+ effective samples
        aug_dataset = AugmentedDataset(train_graphs, augmentor, copies=aug_copies)
        train_data = list(aug_dataset.graphs)
        logger.info(f"Augmented training set: {len(train_graphs)} -> {len(train_data)} graphs")
    else:
        train_data = train_graphs

    # ---- loaders (pin_memory for GPU) ----
    pin = device.type == "cuda"
    num_workers = 0  # PyG Data objects don't serialise well across workers
    train_loader = DataLoader(train_data, batch_size=args.batch_size, shuffle=True, pin_memory=pin, num_workers=num_workers)
    val_loader = DataLoader(val_graphs, batch_size=args.batch_size, shuffle=False, pin_memory=pin, num_workers=num_workers)
    test_loader = DataLoader(test_graphs, batch_size=args.batch_size, shuffle=False, pin_memory=pin, num_workers=num_workers)

    # ---- model ----
    input_dim = train_graphs[0].x.shape[1]
    model = TrojanGNN(
        input_dim=input_dim,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        dropout=args.dropout,
        architecture=args.architecture,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    logger.info(f"Model params : {n_params:,}")

    # ---- train ----
    result = train_model(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        test_loader=test_loader,
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        patience=args.patience,
        device=device,
    )

    # ---- final report ----
    logger.info("=" * 70)
    logger.info("TRAINING COMPLETE")
    logger.info("=" * 70)

    fv = result["final_val_metrics"]
    logger.info("Validation — Graph-Level:")
    logger.info(f"  Best Val Loss : {result['best_val_loss']:.4f}")
    logger.info(f"  Best Val F1   : {result['best_val_f1']:.4f}")
    logger.info(f"  Accuracy      : {fv['val_accuracy']:.4f}")
    logger.info(f"  Precision     : {fv['val_precision']:.4f}")
    logger.info(f"  Recall        : {fv['val_recall']:.4f}")
    logger.info(f"  F1            : {fv['val_f1']:.4f}")
    if "val_roc_auc" in fv:
        logger.info(f"  ROC-AUC       : {fv['val_roc_auc']:.4f}")

    cm = fv["val_confusion_matrix"]
    logger.info(f"  Confusion: TN={cm[0,0]}  FP={cm[0,1]}")
    logger.info(f"             FN={cm[1,0]}  TP={cm[1,1]}")

    fn = result["final_val_node_metrics"]
    if fn:
        logger.info("Validation — Node-Level:")
        logger.info(f"  Accuracy  : {fn.get('val_node_accuracy', 0):.4f}")
        logger.info(f"  Precision : {fn.get('val_node_precision', 0):.4f}")
        logger.info(f"  Recall    : {fn.get('val_node_recall', 0):.4f}")
        logger.info(f"  F1        : {fn.get('val_node_f1', 0):.4f}")

    # ---- test set results ----
    tm = result["test_metrics"]
    logger.info("-" * 40)
    logger.info("TEST SET — Graph-Level:")
    logger.info(f"  Accuracy  : {tm['test_accuracy']:.4f}")
    logger.info(f"  Precision : {tm['test_precision']:.4f}")
    logger.info(f"  Recall    : {tm['test_recall']:.4f}")
    logger.info(f"  F1        : {tm['test_f1']:.4f}")
    if "test_roc_auc" in tm:
        logger.info(f"  ROC-AUC   : {tm['test_roc_auc']:.4f}")

    tcm = tm["test_confusion_matrix"]
    logger.info(f"  Confusion: TN={tcm[0,0]}  FP={tcm[0,1]}")
    logger.info(f"             FN={tcm[1,0]}  TP={tcm[1,1]}")

    tnm = result["test_node_metrics"]
    if tnm:
        logger.info("TEST SET — Node-Level:")
        logger.info(f"  Accuracy  : {tnm.get('test_node_accuracy', 0):.4f}")
        logger.info(f"  Precision : {tnm.get('test_node_precision', 0):.4f}")
        logger.info(f"  Recall    : {tnm.get('test_node_recall', 0):.4f}")
        logger.info(f"  F1        : {tnm.get('test_node_f1', 0):.4f}")

    logger.info(f"\nWeights: backend/trojan_classifier/weights/{args.architecture}_weights.pt")

    # ---- matplotlib plots ----
    plot_dir = args.plot_dir or (Path(__file__).parent / "plots")
    plot_training_history(result["history"], args.architecture, plot_dir)
    plot_test_confusion_matrix(tcm, args.architecture, plot_dir)

    logger.info("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
