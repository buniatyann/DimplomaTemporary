#!/usr/bin/env python3
"""Training script for TrustHub-based GNN trojan detection models.

Usage:
    python -m backend.training.train --data-dir ./data/trusthub --architecture gcn
    python -m backend.training.train --data-dir ./data/trusthub --architecture gat --epochs 100
    python -m backend.training.train --data-dir ./data/trusthub --architecture gin --batch-size 16

This script:
1. Loads TrustHub benchmarks (trojan + trojan-free pairs)
2. Processes them into labeled circuit graphs
3. Trains a GNN model with both graph-level and node-level classification
4. Saves weights to backend/trojan_classifier/weights/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch
from torch_geometric.data import Data

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train GNN models on TrustHub trojan benchmarks"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Path to TrustHub dataset directory",
    )
    parser.add_argument(
        "--architecture",
        choices=["gcn", "gat", "gin"],
        default="gcn",
        help="GNN architecture to train (default: gcn)",
    )
    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=64,
        help="Hidden layer dimensionality (default: 64)",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=3,
        help="Number of GNN layers (default: 3)",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        default=0.5,
        help="Dropout probability (default: 0.5)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.001,
        help="Initial learning rate (default: 0.001)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Training batch size (default: 32)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=200,
        help="Maximum training epochs (default: 200)",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=20,
        help="Early stopping patience (default: 20)",
    )
    parser.add_argument(
        "--node-weight",
        type=float,
        default=0.5,
        help="Weight for node classification loss (default: 0.5)",
    )
    parser.add_argument(
        "--graph-weight",
        type=float,
        default=0.5,
        help="Weight for graph classification loss (default: 0.5)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Computation device: cpu, cuda, cuda:0, etc. (default: auto)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backend/trojan_classifier/weights"),
        help="Directory for saving model weights",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.2,
        help="Validation set fraction (default: 0.2)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    return parser.parse_args()


def setup_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_dataset(data_dir: Path) -> tuple[list[Data], list[Data]]:
    """Load and split the TrustHub dataset.

    Returns:
        Tuple of (train_dataset, val_dataset).
    """
    from backend.training.trusthub_dataset import TrustHubDataset, BenchmarkFamily

    logger.info(f"Loading TrustHub dataset from {data_dir}")

    # Load all available benchmark families
    dataset = TrustHubDataset(
        root=data_dir,
        benchmark_families=list(BenchmarkFamily),
        download=True,
    )

    if len(dataset) == 0:
        raise ValueError(
            f"No processed graphs found in {data_dir}. "
            "Please download TrustHub benchmarks and place them in the raw/ subdirectory."
        )

    stats = dataset.get_statistics()
    logger.info(f"Dataset statistics: {stats}")

    return dataset, stats


def split_dataset(
    graphs: list[Data],
    val_split: float = 0.2,
) -> tuple[list[Data], list[Data]]:
    """Split graphs into train and validation sets, stratified by label."""
    import random

    trojan_graphs = [g for g in graphs if g.y.item() == 1]
    clean_graphs = [g for g in graphs if g.y.item() == 0]

    random.shuffle(trojan_graphs)
    random.shuffle(clean_graphs)

    # Split each class proportionally
    n_trojan_val = max(1, int(len(trojan_graphs) * val_split))
    n_clean_val = max(1, int(len(clean_graphs) * val_split))

    val_graphs = trojan_graphs[:n_trojan_val] + clean_graphs[:n_clean_val]
    train_graphs = trojan_graphs[n_trojan_val:] + clean_graphs[n_clean_val:]

    random.shuffle(train_graphs)
    random.shuffle(val_graphs)

    logger.info(f"Train set: {len(train_graphs)} graphs")
    logger.info(f"Validation set: {len(val_graphs)} graphs")

    return train_graphs, val_graphs


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    logger.info("TrustHub GNN Training Script")
    logger.info(f"Architecture: {args.architecture}")
    logger.info(f"Device: {args.device or 'auto'}")

    # Load dataset
    try:
        dataset, stats = load_dataset(args.data_dir)
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return 1

    # Get all graphs
    graphs = [dataset.get(i) for i in range(len(dataset))]

    if len(graphs) < 4:
        logger.error(f"Need at least 4 graphs for training, got {len(graphs)}")
        logger.error("Please download more TrustHub benchmarks.")
        return 1

    # Split into train/val
    train_graphs, val_graphs = split_dataset(graphs, args.val_split)

    # Create training config
    from backend.training.trainer import TrainingConfig, TrojanTrainer

    config = TrainingConfig(
        architecture=args.architecture,
        hidden_dim=args.hidden_dim,
        num_layers=args.num_layers,
        dropout=args.dropout,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        epochs=args.epochs,
        patience=args.patience,
        node_weight=args.node_weight,
        graph_weight=args.graph_weight,
        device=args.device,
        checkpoint_dir=args.output_dir,
    )

    logger.info(f"Training config: {config.to_dict()}")

    # Create trainer and train
    trainer = TrojanTrainer(config)

    try:
        model = trainer.train(train_graphs, val_graphs)
    except Exception as e:
        logger.error(f"Training failed: {e}")
        return 1

    # Report final metrics
    history = trainer.get_training_history()
    if history:
        final = history[-1]
        logger.info("=" * 60)
        logger.info("Training Complete!")
        logger.info(f"Final Validation Loss: {final['val_loss']:.4f}")
        logger.info(f"Final Graph Accuracy: {final['val_graph_acc']:.4f}")
        logger.info(f"Final Node F1 Score: {final['val_node_f1']:.4f}")
        logger.info(f"Model saved to: {args.output_dir / f'{args.architecture}_weights.pt'}")
        logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
