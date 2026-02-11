#!/usr/bin/env python3
"""Evaluate pretrained GNN models without retraining.

Loads the existing weights for GCN, GAT, and GIN, runs inference on
the test split of the local benchmark data (TRIT + ISCAS + EPFL), and
prints graph-level and node-level metrics for each architecture plus
a weighted-average ensemble.

Usage:
    python -m backend.training.eval_models
    python -m backend.training.eval_models -v         # verbose
    python -m backend.training.eval_models --data-dir backend/training/data
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader

from backend.training.train_local import (
    FEATURE_DIM,
    TrojanGNN,
    load_benchmark_files,
    seed_everything,
)

logger = logging.getLogger(__name__)

WEIGHTS_DIR = Path(__file__).parent.parent / "trojan_classifier" / "weights"

ARCHITECTURES = ["gcn", "gat", "gin"]

ENSEMBLE_WEIGHTS = {"gcn": 0.30, "gat": 0.35, "gin": 0.35}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_metrics(
    y_true: list[int],
    y_pred: list[int],
    y_proba: list[float] | None = None,
) -> dict[str, float]:
    """Compute classification metrics."""
    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    m: dict[str, float] = {
        "accuracy": acc,
        "precision": prec,
        "recall": rec,
        "f1": f1,
    }

    if y_proba is not None and len(set(y_true)) > 1:
        try:
            m["roc_auc"] = roc_auc_score(y_true, y_proba)
        except ValueError:
            pass

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    m["tn"] = float(cm[0, 0])
    m["fp"] = float(cm[0, 1])
    m["fn"] = float(cm[1, 0])
    m["tp"] = float(cm[1, 1])

    return m


def load_model(arch: str, input_dim: int, device: torch.device) -> TrojanGNN:
    """Instantiate a TrojanGNN and load pretrained weights."""
    model = TrojanGNN(
        input_dim=input_dim,
        hidden_dim=128,
        num_layers=4,
        dropout=0.3,
        architecture=arch,
    ).to(device)

    weight_file = WEIGHTS_DIR / f"{arch}_weights.pt"
    if not weight_file.exists():
        raise FileNotFoundError(f"No weights found at {weight_file}")

    state_dict = torch.load(weight_file, map_location=device, weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()
    logger.info(f"Loaded {arch} weights from {weight_file}")
    return model


@torch.no_grad()
def evaluate_model(
    model: TrojanGNN,
    loader: DataLoader,
    device: torch.device,
) -> dict[str, dict[str, float]]:
    """Run inference and compute graph-level and node-level metrics."""
    model.eval()

    graph_labels: list[int] = []
    graph_preds: list[int] = []
    graph_probs: list[float] = []

    node_labels: list[int] = []
    node_preds: list[int] = []
    node_probs: list[float] = []

    for batch in loader:
        batch = batch.to(device)
        graph_logits, node_logits = model(batch.x, batch.edge_index, batch.batch)

        # Graph-level
        probs = F.softmax(graph_logits, dim=1)[:, 1]
        graph_labels.extend(batch.y.cpu().numpy().tolist())
        graph_preds.extend(graph_logits.argmax(1).cpu().numpy().tolist())
        graph_probs.extend(probs.cpu().numpy().tolist())

        # Node-level
        if hasattr(batch, "node_labels"):
            n_probs = F.softmax(node_logits, dim=1)[:, 1]
            node_labels.extend(batch.node_labels.cpu().numpy().tolist())
            node_preds.extend(node_logits.argmax(1).cpu().numpy().tolist())
            node_probs.extend(n_probs.cpu().numpy().tolist())

    graph_m = compute_metrics(graph_labels, graph_preds, graph_probs)

    node_m: dict[str, float] = {}
    if node_labels:
        node_m = compute_metrics(node_labels, node_preds, node_probs)

    return {"graph": graph_m, "node": node_m}


@torch.no_grad()
def evaluate_ensemble(
    models: dict[str, TrojanGNN],
    loader: DataLoader,
    device: torch.device,
    weights: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Weighted-average ensemble over all models."""
    for m in models.values():
        m.eval()

    graph_labels: list[int] = []
    graph_preds: list[int] = []
    graph_probs: list[float] = []

    node_labels: list[int] = []
    node_preds: list[int] = []
    node_probs_combined: list[float] = []

    total_weight = sum(weights[a] for a in models)

    for batch in loader:
        batch = batch.to(device)

        # Accumulate weighted graph and node probabilities
        ens_graph_prob = torch.zeros(batch.y.size(0), 2, device=device)
        ens_node_prob = None

        for arch, model in models.items():
            gl, nl = model(batch.x, batch.edge_index, batch.batch)
            gp = F.softmax(gl, dim=1)
            np_ = F.softmax(nl, dim=1)
            w = weights[arch]
            ens_graph_prob += w * gp
            if ens_node_prob is None:
                ens_node_prob = w * np_
            else:
                ens_node_prob += w * np_

        ens_graph_prob /= total_weight
        if ens_node_prob is not None:
            ens_node_prob /= total_weight

        # Graph-level
        trojan_p = ens_graph_prob[:, 1]
        pred = (trojan_p > 0.5).long()
        graph_labels.extend(batch.y.cpu().numpy().tolist())
        graph_preds.extend(pred.cpu().numpy().tolist())
        graph_probs.extend(trojan_p.cpu().numpy().tolist())

        # Node-level
        if hasattr(batch, "node_labels") and ens_node_prob is not None:
            n_trojan_p = ens_node_prob[:, 1]
            n_pred = (n_trojan_p > 0.5).long()
            node_labels.extend(batch.node_labels.cpu().numpy().tolist())
            node_preds.extend(n_pred.cpu().numpy().tolist())
            node_probs_combined.extend(n_trojan_p.cpu().numpy().tolist())

    graph_m = compute_metrics(graph_labels, graph_preds, graph_probs)

    node_m: dict[str, float] = {}
    if node_labels:
        node_m = compute_metrics(node_labels, node_preds, node_probs_combined)

    return {"graph": graph_m, "node": node_m}


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_metrics(label: str, metrics: dict[str, dict[str, float]]) -> None:
    """Pretty-print graph-level and node-level metrics."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  {label}")
    print(sep)

    gm = metrics["graph"]
    print("  Graph-Level:")
    print(f"    Accuracy  : {gm['accuracy']:.4f}")
    print(f"    Precision : {gm['precision']:.4f}")
    print(f"    Recall    : {gm['recall']:.4f}")
    print(f"    F1        : {gm['f1']:.4f}")
    if "roc_auc" in gm:
        print(f"    ROC-AUC   : {gm['roc_auc']:.4f}")
    print(f"    Confusion : TN={gm['tn']:.0f}  FP={gm['fp']:.0f}")
    print(f"                FN={gm['fn']:.0f}  TP={gm['tp']:.0f}")

    nm = metrics.get("node", {})
    if nm:
        print("  Node-Level:")
        print(f"    Accuracy  : {nm['accuracy']:.4f}")
        print(f"    Precision : {nm['precision']:.4f}")
        print(f"    Recall    : {nm['recall']:.4f}")
        print(f"    F1        : {nm['f1']:.4f}")
        if "roc_auc" in nm:
            print(f"    ROC-AUC   : {nm['roc_auc']:.4f}")
        print(f"    Confusion : TN={nm['tn']:.0f}  FP={nm['fp']:.0f}")
        print(f"                FN={nm['fn']:.0f}  TP={nm['tp']:.0f}")
    else:
        print("  Node-Level: (no node labels available)")


def print_summary_table(all_results: dict[str, dict[str, dict[str, float]]]) -> None:
    """Print a compact comparison table."""
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80)

    header = f"  {'Model':<12} | {'Graph Acc':>9} {'Graph F1':>9} {'Graph AUC':>9} | {'Node Acc':>9} {'Node F1':>9} {'Node AUC':>9}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for name, metrics in all_results.items():
        gm = metrics["graph"]
        nm = metrics.get("node", {})
        g_acc = f"{gm['accuracy']:.4f}"
        g_f1 = f"{gm['f1']:.4f}"
        g_auc = f"{gm.get('roc_auc', 0):.4f}" if "roc_auc" in gm else "   N/A  "
        n_acc = f"{nm['accuracy']:.4f}" if nm else "   N/A  "
        n_f1 = f"{nm['f1']:.4f}" if nm else "   N/A  "
        n_auc = f"{nm.get('roc_auc', 0):.4f}" if nm and "roc_auc" in nm else "   N/A  "
        print(f"  {name:<12} | {g_acc:>9} {g_f1:>9} {g_auc:>9} | {n_acc:>9} {n_f1:>9} {n_auc:>9}")

    print("=" * 80)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate pretrained GNN models")
    p.add_argument("--data-dir", type=Path, default=None, help="Data directory override")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("-v", "--verbose", action="count", default=0)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    level = logging.WARNING
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")

    seed_everything(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    # Load data (reuse the same 60/20/20 split as training)
    print("\nLoading benchmark data...")
    try:
        train_graphs, val_graphs, test_graphs = load_benchmark_files(
            args.data_dir, seed=args.seed,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    n_test_trojan = sum(1 for g in test_graphs if g.y.item() == 1)
    n_test_clean = len(test_graphs) - n_test_trojan
    print(f"Test set: {len(test_graphs)} graphs ({n_test_trojan} trojan, {n_test_clean} clean)")

    # Count test node labels
    total_nodes = 0
    trojan_nodes = 0
    for g in test_graphs:
        if hasattr(g, "node_labels"):
            total_nodes += g.node_labels.shape[0]
            trojan_nodes += g.node_labels.sum().item()
    print(f"Test set: {total_nodes} nodes ({trojan_nodes} trojan, {total_nodes - trojan_nodes} benign)")

    test_loader = DataLoader(test_graphs, batch_size=args.batch_size, shuffle=False)

    input_dim = test_graphs[0].x.shape[1]
    print(f"Input feature dim: {input_dim}")

    # Evaluate each architecture
    all_results: dict[str, dict[str, dict[str, float]]] = {}
    models: dict[str, TrojanGNN] = {}

    for arch in ARCHITECTURES:
        print(f"\nEvaluating {arch.upper()}...")
        try:
            model = load_model(arch, input_dim, device)
        except FileNotFoundError as e:
            print(f"  Skipping {arch}: {e}")
            continue

        metrics = evaluate_model(model, test_loader, device)
        all_results[arch.upper()] = metrics
        models[arch] = model
        print_metrics(f"{arch.upper()} (individual)", metrics)

    # Ensemble evaluation
    if len(models) >= 2:
        print(f"\nEvaluating ENSEMBLE (weights: {ENSEMBLE_WEIGHTS})...")
        ens_metrics = evaluate_ensemble(models, test_loader, device, ENSEMBLE_WEIGHTS)
        all_results["ENSEMBLE"] = ens_metrics
        print_metrics("ENSEMBLE (weighted average)", ens_metrics)
    else:
        print("\nSkipping ensemble: need at least 2 models loaded.")

    # Summary
    print_summary_table(all_results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
