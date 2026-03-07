#!/usr/bin/env python3
"""Evaluate GNN models on TrustHub benchmarks using Yosys-only pipeline.

Bypasses pyverilog entirely — feeds all .v files per benchmark directory
directly to Yosys for elaboration, builds graphs from the JSON netlist,
then runs GCN/GAT/GIN ensemble classification.

Testbench files (tb*.v, *_tb.v, *test*.v) are automatically excluded.

Usage:
    python -m backend.training.eval_trusthub_yosys
    python -m backend.training.eval_trusthub_yosys -v
    python -m backend.training.eval_trusthub_yosys --data-dir backend/training/data
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import torch
import torch.nn.functional as F
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from backend.core.history import History
from backend.netlist_graph_builder.builder import NetlistGraphBuilder
from backend.training.train_local import FEATURE_DIM, TrojanGNN

logger = logging.getLogger(__name__)

WEIGHTS_DIR = Path(__file__).parent.parent / "trojan_classifier" / "weights"
DEFAULT_DATA_DIR = Path(__file__).parent / "data"
ARCHITECTURES = ["gcn", "gat", "gin"]
ENSEMBLE_WEIGHTS = {"gcn": 0.30, "gat": 0.35, "gin": 0.35}

# Patterns to exclude testbench files
_TB_PATTERNS = [
    re.compile(r"^tb", re.IGNORECASE),         # tbTOP.v, tb_*.v
    re.compile(r"_tb\.v$", re.IGNORECASE),      # AES_tb.v, battery_tb.v
    re.compile(r"test", re.IGNORECASE),         # test_*.v, *test*.v
]


def _is_testbench(filename: str) -> bool:
    """Check if a filename matches testbench patterns."""
    return any(pat.search(filename) for pat in _TB_PATTERNS)


def _collect_benchmarks(base: Path) -> list[tuple[str, Path, bool]]:
    """Collect TrustHub benchmark directories.

    Returns:
        List of (benchmark_name, dir_path, is_trojan) tuples.
    """
    trusthub_dir = base / "trusthub"
    if not trusthub_dir.exists():
        raise FileNotFoundError(f"TrustHub data not found at {trusthub_dir}")

    benchmarks: list[tuple[str, Path, bool]] = []
    for bench_dir in sorted(trusthub_dir.iterdir()):
        if not bench_dir.is_dir():
            continue
        trojan_dir = bench_dir / "trojan"
        golden_dir = bench_dir / "golden"
        if trojan_dir.exists():
            benchmarks.append((bench_dir.name, trojan_dir, True))
        if golden_dir.exists():
            benchmarks.append((bench_dir.name, golden_dir, False))

    return benchmarks


def _collect_verilog_files(directory: Path) -> list[Path]:
    """Collect .v files from a directory, excluding testbenches."""
    files = []
    for vf in sorted(directory.glob("*.v")):
        if _is_testbench(vf.name):
            logger.info(f"  Excluding testbench: {vf.name}")
            continue
        files.append(vf.resolve())
    return files


def _synthesize_flat(
    vfiles: list[Path], timeout: int = 300,
) -> tuple[dict | None, str]:
    """Synthesize .v files with Yosys using flatten + techmap.

    The standard synthesize.ys doesn't flatten, so the graph builder
    only sees the top-level module's ports. We need to flatten the
    hierarchy to get all gates in a single module.

    Returns:
        (json_netlist, error_message) — one will be None.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    yosys = shutil.which("yosys")
    if yosys is None:
        return None, "Yosys not found in PATH"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        json_output = tmpdir_path / "netlist.json"

        read_cmds = "\n".join(f"read_verilog {p}" for p in vfiles)
        script = (
            f"{read_cmds}\n"
            "hierarchy -auto-top\n"
            "proc\n"
            "flatten\n"
            "opt\n"
            "techmap\n"
            "opt\n"
            "clean\n"
            f"write_json {json_output}\n"
        )

        script_path = tmpdir_path / "run.ys"
        script_path.write_text(script)

        try:
            result = subprocess.run(
                [yosys, "-s", str(script_path)],
                capture_output=True, text=True, timeout=timeout, cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            return None, f"Yosys timed out after {timeout}s"

        if result.returncode != 0:
            stderr = result.stderr or result.stdout
            # Extract the key error line
            for line in stderr.splitlines():
                if "ERROR" in line:
                    return None, line.strip()
            return None, f"Yosys exited with code {result.returncode}"

        if not json_output.exists():
            return None, "Yosys did not produce JSON output"

        try:
            netlist = json.loads(json_output.read_text())
            return netlist, ""
        except json.JSONDecodeError as e:
            return None, f"JSON parse error: {e}"


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
    return model


@torch.no_grad()
def predict_ensemble(
    models: dict[str, TrojanGNN],
    graph_data,
    device: torch.device,
    weights: dict[str, float],
) -> tuple[int, float, dict[str, float]]:
    """Run ensemble prediction on a single graph.

    Returns:
        (prediction, trojan_probability, per_model_probs)
    """
    total_weight = sum(weights[a] for a in models)
    ens_prob = 0.0
    per_model: dict[str, float] = {}

    batch = torch.zeros(graph_data.x.size(0), dtype=torch.long, device=device)

    for arch, model in models.items():
        model.eval()
        gl, nl = model(graph_data.x.to(device), graph_data.edge_index.to(device), batch)
        prob = F.softmax(gl, dim=1)[0, 1].item()
        per_model[arch] = prob
        ens_prob += weights[arch] * prob

    ens_prob /= total_weight
    pred = 1 if ens_prob > 0.5 else 0
    return pred, ens_prob, per_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate GNNs on TrustHub via Yosys")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    level = logging.WARNING
    if args.verbose >= 2:
        level = logging.DEBUG
    elif args.verbose >= 1:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")

    base = args.data_dir if args.data_dir else DEFAULT_DATA_DIR
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Collect benchmarks
    benchmarks = _collect_benchmarks(base)
    print(f"Found {len(benchmarks)} benchmark directories "
          f"({sum(1 for _, _, t in benchmarks if t)} trojan, "
          f"{sum(1 for _, _, t in benchmarks if not t)} golden)")

    # Load models
    print("\nLoading models...")
    models: dict[str, TrojanGNN] = {}
    for arch in ARCHITECTURES:
        try:
            model = load_model(arch, FEATURE_DIM, device)
            models[arch] = model
            print(f"  Loaded {arch.upper()}")
        except FileNotFoundError as e:
            print(f"  Skipping {arch}: {e}")

    if not models:
        print("ERROR: No models loaded.", file=sys.stderr)
        return 1

    # Process each benchmark
    import shutil
    if shutil.which("yosys") is None:
        print("ERROR: Yosys not found in PATH.", file=sys.stderr)
        return 1

    print("\n" + "=" * 70)
    print("  Processing benchmarks")
    print("=" * 70)

    y_true: list[int] = []
    y_pred: list[int] = []
    y_prob: list[float] = []
    results_detail: list[dict] = []
    failed = 0

    for bench_name, bench_dir, is_trojan in benchmarks:
        label_str = "TROJAN" if is_trojan else "GOLDEN"
        print(f"\n[{bench_name}/{label_str}]")

        # Collect .v files (excluding testbenches)
        vfiles = _collect_verilog_files(bench_dir)
        if not vfiles:
            print(f"  SKIP: No Verilog files after excluding testbenches")
            failed += 1
            continue

        print(f"  Files: {[f.name for f in vfiles]}")

        # Synthesize with Yosys (flatten + techmap for gate-level netlist)
        json_netlist, error = _synthesize_flat(vfiles)
        if json_netlist is None:
            print(f"  FAIL (Yosys): {error[:120]}")
            failed += 1
            continue

        # Pick the top-level module (largest by cell count)
        modules = json_netlist.get("modules", {})
        if not modules:
            print(f"  FAIL: No modules in JSON netlist")
            failed += 1
            continue

        top_module = max(
            modules.keys(),
            key=lambda m: len(modules[m].get("cells", {})),
        )
        # Keep only the top module in the netlist for the graph builder
        filtered_netlist = {"modules": {top_module: modules[top_module]}}
        logger.info(f"  Selected top module: {top_module} "
                     f"({len(modules[top_module].get('cells', {}))} cells)")

        # Build graph
        history = History()
        graph_builder = NetlistGraphBuilder(history)
        try:
            circuit_graph_outcome = graph_builder.process(
                type("SynthResult", (), {"json_netlist": filtered_netlist})()
            )
            if not circuit_graph_outcome.success:
                print(f"  FAIL (Graph): {circuit_graph_outcome.error_message}")
                failed += 1
                continue
            circuit_graph = circuit_graph_outcome.data
        except Exception as e:
            print(f"  FAIL (Graph): {e}")
            failed += 1
            continue

        print(f"  Graph: {circuit_graph.node_count} nodes, {circuit_graph.edge_count} edges")

        # Run ensemble prediction
        graph_data = circuit_graph.graph_data
        pred, prob, per_model = predict_ensemble(models, graph_data, device, ENSEMBLE_WEIGHTS)

        true_label = 1 if is_trojan else 0
        verdict = "TROJAN" if pred == 1 else "CLEAN"
        correct = "OK" if pred == true_label else "WRONG"

        y_true.append(true_label)
        y_pred.append(pred)
        y_prob.append(prob)

        model_strs = " | ".join(f"{a}={p:.3f}" for a, p in per_model.items())
        print(f"  Prediction: {verdict} (prob={prob:.4f}) [{correct}]")
        print(f"  Per-model:  {model_strs}")

        results_detail.append({
            "benchmark": bench_name,
            "label": label_str,
            "true": true_label,
            "pred": pred,
            "prob": prob,
            "nodes": circuit_graph.node_count,
            "edges": circuit_graph.edge_count,
        })

    # Compute and display metrics
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)

    total = len(y_true)
    print(f"\nProcessed: {total} / {len(benchmarks)} benchmarks (failed: {failed})")

    if total == 0:
        print("No benchmarks successfully processed.")
        return 1

    acc = accuracy_score(y_true, y_pred)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    print(f"\nGraph-Level Metrics:")
    print(f"  Accuracy  : {acc:.4f}")
    print(f"  Precision : {prec:.4f}")
    print(f"  Recall    : {rec:.4f}")
    print(f"  F1 Score  : {f1:.4f}")

    if len(set(y_true)) > 1:
        try:
            auc = roc_auc_score(y_true, y_prob)
            print(f"  ROC-AUC   : {auc:.4f}")
        except ValueError:
            pass

    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    print(f"\n  Confusion Matrix:")
    print(f"    TN={cm[0, 0]:3d}  FP={cm[0, 1]:3d}")
    print(f"    FN={cm[1, 0]:3d}  TP={cm[1, 1]:3d}")

    # Per-benchmark detail table
    print(f"\n{'Benchmark':<14} {'Label':<8} {'Pred':<8} {'Prob':>6} {'Nodes':>6} {'Edges':>6} {'Result':<6}")
    print("-" * 60)
    for r in results_detail:
        pred_str = "TROJAN" if r["pred"] == 1 else "CLEAN"
        ok = "OK" if r["pred"] == r["true"] else "WRONG"
        print(f"{r['benchmark']:<14} {r['label']:<8} {pred_str:<8} {r['prob']:>6.3f} {r['nodes']:>6} {r['edges']:>6} {ok:<6}")

    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
