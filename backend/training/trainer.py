"""Training infrastructure for GNN-based trojan detection models.

Supports training with:
- Graph-level classification (trojan vs clean circuit)
- Node-level classification (which gates are trojan)
- Combined multi-task learning
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam, AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau, CosineAnnealingLR
from torch_geometric.loader import DataLoader
from torch_geometric.data import Data

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for model training.

    Attributes:
        architecture: GNN architecture ("gcn", "gat", "gin")
        hidden_dim: Hidden layer dimensionality
        num_layers: Number of GNN layers
        dropout: Dropout probability
        learning_rate: Initial learning rate
        weight_decay: L2 regularization weight
        batch_size: Training batch size
        epochs: Maximum training epochs
        patience: Early stopping patience
        node_weight: Weight for node classification loss
        graph_weight: Weight for graph classification loss
        device: Computation device
    """
    architecture: str = "gcn"
    hidden_dim: int = 64
    num_layers: int = 3
    dropout: float = 0.5
    learning_rate: float = 0.001
    weight_decay: float = 1e-4
    batch_size: int = 32
    epochs: int = 200
    patience: int = 20
    node_weight: float = 0.5  # Weight for node-level loss
    graph_weight: float = 0.5  # Weight for graph-level loss
    device: str | None = None
    save_best: bool = True
    checkpoint_dir: Path = field(default_factory=lambda: Path("backend/trojan_classifier/weights"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "architecture": self.architecture,
            "hidden_dim": self.hidden_dim,
            "num_layers": self.num_layers,
            "dropout": self.dropout,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "patience": self.patience,
            "node_weight": self.node_weight,
            "graph_weight": self.graph_weight,
            "device": self.device,
        }


@dataclass
class TrainingMetrics:
    """Metrics collected during training."""
    epoch: int = 0
    train_loss: float = 0.0
    train_graph_acc: float = 0.0
    train_node_acc: float = 0.0
    val_loss: float = 0.0
    val_graph_acc: float = 0.0
    val_node_acc: float = 0.0
    val_node_precision: float = 0.0
    val_node_recall: float = 0.0
    val_node_f1: float = 0.0
    learning_rate: float = 0.0
    epoch_time: float = 0.0


class TrojanClassifierWithNodeLabels(nn.Module):
    """GNN model that predicts both graph-level and node-level labels.

    This model extends the base classifiers to output:
    1. Graph-level prediction: Is the circuit trojan-infected?
    2. Node-level predictions: Which gates are part of the trojan?
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int = 64,
        num_layers: int = 3,
        dropout: float = 0.5,
        architecture: str = "gcn",
    ) -> None:
        super().__init__()

        self.architecture = architecture

        # Import the base architecture
        if architecture == "gcn":
            from backend.trojan_classifier.architectures.gcn import GCNClassifier
            self.base_model = GCNClassifier(input_dim, hidden_dim, num_layers, dropout)
        elif architecture == "gat":
            from backend.trojan_classifier.architectures.gat import GATClassifier
            self.base_model = GATClassifier(input_dim, hidden_dim, num_layers, dropout)
        elif architecture == "gin":
            from backend.trojan_classifier.architectures.gin import GINClassifier
            self.base_model = GINClassifier(input_dim, hidden_dim, num_layers, dropout)
        else:
            raise ValueError(f"Unknown architecture: {architecture}")

        # Node-level classification head
        self.node_classifier = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 2),  # Binary: trojan or not
        )

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        batch: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward pass returning both graph and node predictions.

        Args:
            x: Node feature matrix (N x F)
            edge_index: Edge connectivity (2 x E)
            batch: Batch assignment for nodes

        Returns:
            Tuple of (graph_logits, node_logits)
            - graph_logits: (B x 2) for graph classification
            - node_logits: (N x 2) for node classification
        """
        # Get node embeddings from base model
        node_embeddings = self.base_model.get_node_embeddings(x, edge_index)

        # Graph-level prediction
        graph_logits = self.base_model(x, edge_index, batch)

        # Node-level prediction
        node_logits = self.node_classifier(node_embeddings)

        return graph_logits, node_logits

    def get_node_embeddings(
        self, x: torch.Tensor, edge_index: torch.Tensor
    ) -> torch.Tensor:
        """Get node embeddings for attribution analysis."""
        return self.base_model.get_node_embeddings(x, edge_index)


class TrojanTrainer:
    """Trainer for GNN-based trojan detection models.

    Supports:
    - Multi-task learning (graph + node classification)
    - Class imbalance handling (trojans are sparse)
    - Early stopping and checkpointing
    - Detailed metrics tracking
    """

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()
        self.model: TrojanClassifierWithNodeLabels | None = None
        self.optimizer: torch.optim.Optimizer | None = None
        self.scheduler: Any = None
        self.history: list[TrainingMetrics] = []
        self.best_val_loss = float("inf")
        self.patience_counter = 0

        # Set device
        if self.config.device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(self.config.device)

        logger.info(f"Using device: {self.device}")

    def train(
        self,
        train_dataset: list[Data],
        val_dataset: list[Data],
        input_dim: int | None = None,
    ) -> TrojanClassifierWithNodeLabels:
        """Train the model on TrustHub data.

        Args:
            train_dataset: Training graphs with node_labels attribute.
            val_dataset: Validation graphs with node_labels attribute.
            input_dim: Input feature dimensionality (auto-detected if None).

        Returns:
            Trained model.
        """
        if not train_dataset:
            raise ValueError("Training dataset is empty")

        # Auto-detect input dimension
        if input_dim is None:
            input_dim = train_dataset[0].x.shape[1]

        logger.info(f"Input dimension: {input_dim}")
        logger.info(f"Training samples: {len(train_dataset)}")
        logger.info(f"Validation samples: {len(val_dataset)}")

        # Initialize model
        self.model = TrojanClassifierWithNodeLabels(
            input_dim=input_dim,
            hidden_dim=self.config.hidden_dim,
            num_layers=self.config.num_layers,
            dropout=self.config.dropout,
            architecture=self.config.architecture,
        ).to(self.device)

        # Compute class weights for node classification (trojan nodes are rare)
        node_class_weights = self._compute_class_weights(train_dataset)
        logger.info(f"Node class weights: {node_class_weights}")

        # Initialize optimizer
        self.optimizer = AdamW(
            self.model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        # Learning rate scheduler
        self.scheduler = ReduceLROnPlateau(
            self.optimizer,
            mode="min",
            factor=0.5,
            patience=10,
            min_lr=1e-6,
        )

        # Data loaders
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
        )
        val_loader = DataLoader(
            val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
        )

        # Training loop
        logger.info("Starting training...")
        for epoch in range(1, self.config.epochs + 1):
            epoch_start = time.time()

            # Train epoch
            train_metrics = self._train_epoch(train_loader, node_class_weights)

            # Validate
            val_metrics = self._validate(val_loader, node_class_weights)

            # Update scheduler (skip if val loss is NaN)
            val_loss = val_metrics["loss"]
            if not (val_loss != val_loss):  # NaN check
                self.scheduler.step(val_loss)

            # Record metrics
            metrics = TrainingMetrics(
                epoch=epoch,
                train_loss=train_metrics["loss"],
                train_graph_acc=train_metrics["graph_acc"],
                train_node_acc=train_metrics["node_acc"],
                val_loss=val_metrics["loss"],
                val_graph_acc=val_metrics["graph_acc"],
                val_node_acc=val_metrics["node_acc"],
                val_node_precision=val_metrics["node_precision"],
                val_node_recall=val_metrics["node_recall"],
                val_node_f1=val_metrics["node_f1"],
                learning_rate=self.optimizer.param_groups[0]["lr"],
                epoch_time=time.time() - epoch_start,
            )
            self.history.append(metrics)

            # Logging
            logger.info(
                f"Epoch {epoch:3d} | "
                f"Train Loss: {train_metrics['loss']:.4f} | "
                f"Val Loss: {val_metrics['loss']:.4f} | "
                f"Graph Acc: {val_metrics['graph_acc']:.4f} | "
                f"Node F1: {val_metrics['node_f1']:.4f}"
            )

            # Checkpointing (skip NaN losses)
            if not (val_loss != val_loss) and val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self.patience_counter = 0
                if self.config.save_best:
                    self._save_checkpoint(epoch)
            else:
                self.patience_counter += 1

            # Early stopping
            if self.patience_counter >= self.config.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

        # Load best model if checkpointing was enabled
        if self.config.save_best:
            self._load_best_checkpoint()

        return self.model

    def _train_epoch(
        self,
        loader: DataLoader,
        node_class_weights: torch.Tensor,
    ) -> dict[str, float]:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0
        total_graph_correct = 0
        total_graphs = 0
        total_node_correct = 0
        total_nodes = 0

        for batch in loader:
            batch = batch.to(self.device)
            self.optimizer.zero_grad()

            # Forward pass
            graph_logits, node_logits = self.model(
                batch.x, batch.edge_index, batch.batch
            )

            # Graph classification loss
            graph_loss = F.cross_entropy(graph_logits, batch.y)

            # Node classification loss (with class weighting)
            if hasattr(batch, "node_labels"):
                node_loss = F.cross_entropy(
                    node_logits,
                    batch.node_labels,
                    weight=node_class_weights.to(self.device),
                )
            else:
                node_loss = torch.tensor(0.0, device=self.device)

            # Combined loss
            loss = (
                self.config.graph_weight * graph_loss +
                self.config.node_weight * node_loss
            )

            # Backward pass
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            # Track metrics
            total_loss += loss.item() * batch.num_graphs
            total_graphs += batch.num_graphs

            graph_pred = graph_logits.argmax(dim=1)
            total_graph_correct += (graph_pred == batch.y).sum().item()

            if hasattr(batch, "node_labels"):
                node_pred = node_logits.argmax(dim=1)
                total_node_correct += (node_pred == batch.node_labels).sum().item()
                total_nodes += batch.node_labels.shape[0]

        return {
            "loss": total_loss / total_graphs,
            "graph_acc": total_graph_correct / total_graphs,
            "node_acc": total_node_correct / total_nodes if total_nodes > 0 else 0.0,
        }

    @torch.no_grad()
    def _validate(
        self,
        loader: DataLoader,
        node_class_weights: torch.Tensor,
    ) -> dict[str, float]:
        """Validate the model."""
        self.model.eval()
        total_loss = 0.0
        total_graph_correct = 0
        total_graphs = 0

        # For node-level metrics
        all_node_preds = []
        all_node_labels = []

        for batch in loader:
            batch = batch.to(self.device)

            graph_logits, node_logits = self.model(
                batch.x, batch.edge_index, batch.batch
            )

            # Loss computation
            graph_loss = F.cross_entropy(graph_logits, batch.y)

            if hasattr(batch, "node_labels"):
                node_loss = F.cross_entropy(
                    node_logits,
                    batch.node_labels,
                    weight=node_class_weights.to(self.device),
                )
                all_node_preds.append(node_logits.argmax(dim=1).cpu())
                all_node_labels.append(batch.node_labels.cpu())
            else:
                node_loss = torch.tensor(0.0, device=self.device)

            loss = (
                self.config.graph_weight * graph_loss +
                self.config.node_weight * node_loss
            )

            total_loss += loss.item() * batch.num_graphs
            total_graphs += batch.num_graphs

            graph_pred = graph_logits.argmax(dim=1)
            total_graph_correct += (graph_pred == batch.y).sum().item()

        # Compute node-level metrics
        if all_node_preds:
            node_preds = torch.cat(all_node_preds)
            node_labels = torch.cat(all_node_labels)
            node_metrics = self._compute_node_metrics(node_preds, node_labels)
        else:
            node_metrics = {"acc": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}

        return {
            "loss": total_loss / total_graphs,
            "graph_acc": total_graph_correct / total_graphs,
            "node_acc": node_metrics["acc"],
            "node_precision": node_metrics["precision"],
            "node_recall": node_metrics["recall"],
            "node_f1": node_metrics["f1"],
        }

    def _compute_class_weights(self, dataset: list[Data]) -> torch.Tensor:
        """Compute class weights to handle imbalanced trojan nodes."""
        import math
        total_nodes = 0
        trojan_nodes = 0

        for data in dataset:
            if hasattr(data, "node_labels"):
                total_nodes += data.node_labels.shape[0]
                trojan_nodes += data.node_labels.sum().item()

        if trojan_nodes == 0 or total_nodes == 0:
            return torch.tensor([1.0, 1.0])

        # sqrt-dampened inverse frequency weighting
        benign_nodes = total_nodes - trojan_nodes
        raw_ratio = benign_nodes / trojan_nodes
        dampened_ratio = min(math.sqrt(raw_ratio), 50.0)
        weights = torch.tensor([1.0, dampened_ratio])

        return weights

    def _compute_node_metrics(
        self,
        preds: torch.Tensor,
        labels: torch.Tensor,
    ) -> dict[str, float]:
        """Compute precision, recall, F1 for node classification."""
        # True positives, false positives, false negatives for trojan class (1)
        tp = ((preds == 1) & (labels == 1)).sum().item()
        fp = ((preds == 1) & (labels == 0)).sum().item()
        fn = ((preds == 0) & (labels == 1)).sum().item()

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        acc = (preds == labels).float().mean().item()

        return {
            "acc": acc,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    def _save_checkpoint(self, epoch: int) -> None:
        """Save model checkpoint."""
        checkpoint_dir = Path(self.config.checkpoint_dir)
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Save model weights
        weight_path = checkpoint_dir / f"{self.config.architecture}_weights.pt"
        torch.save(self.model.state_dict(), weight_path)

        # Save training config and metrics
        meta_path = checkpoint_dir / f"{self.config.architecture}_training_meta.json"
        meta = {
            "config": self.config.to_dict(),
            "best_epoch": epoch,
            "best_val_loss": self.best_val_loss,
            "history": [
                {
                    "epoch": m.epoch,
                    "train_loss": m.train_loss,
                    "val_loss": m.val_loss,
                    "val_graph_acc": m.val_graph_acc,
                    "val_node_f1": m.val_node_f1,
                }
                for m in self.history
            ],
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        logger.info(f"Saved checkpoint at epoch {epoch} to {weight_path}")

    def _load_best_checkpoint(self) -> None:
        """Load the best checkpoint."""
        weight_path = Path(self.config.checkpoint_dir) / f"{self.config.architecture}_weights.pt"
        if weight_path.exists():
            self.model.load_state_dict(
                torch.load(weight_path, map_location=self.device, weights_only=True)
            )
            logger.info(f"Loaded best checkpoint from {weight_path}")

    def get_training_history(self) -> list[dict[str, Any]]:
        """Get training history as list of dicts."""
        return [
            {
                "epoch": m.epoch,
                "train_loss": m.train_loss,
                "train_graph_acc": m.train_graph_acc,
                "train_node_acc": m.train_node_acc,
                "val_loss": m.val_loss,
                "val_graph_acc": m.val_graph_acc,
                "val_node_acc": m.val_node_acc,
                "val_node_precision": m.val_node_precision,
                "val_node_recall": m.val_node_recall,
                "val_node_f1": m.val_node_f1,
                "learning_rate": m.learning_rate,
                "epoch_time": m.epoch_time,
            }
            for m in self.history
        ]
