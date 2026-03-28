"""Graph Invariant Comparison for resolving UNCERTAIN verdicts.

When the GNN ensemble produces an UNCERTAIN verdict (low confidence or
false-positive downgrade), this module computes structural metrics on the
suspect circuit and compares them against a baseline derived from known-clean
training graphs.  Significant deviations suggest trojan insertion; metrics
within the normal range suggest a clean circuit.

Metrics computed (all O(N + E)):
    1. Degree distribution moments (mean, std of in-degree and out-degree)
    2. Graph density (E / N^2)
    3. Weakly connected component count and size distribution
    4. Gate type distribution (entropy and dominant-type ratio)
    5. Primary I/O ratio (fraction of nodes that are inputs or outputs)

Time complexity: O(N + E) at inference.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import torch

from backend.netlist_graph_builder.models import CircuitGraph
from backend.netlist_graph_builder.node_encoder import VOCAB_SIZE
from backend.trojan_classifier.models import TrojanVerdict

logger = logging.getLogger(__name__)

# Where the precomputed baseline lives alongside model weights.
BASELINE_PATH = Path(__file__).parent / "weights" / "structural_baseline.json"

# z-score threshold: metrics deviating more than this are "anomalous".
# Raised from 2.0 → 2.5 to reduce false positives on clean circuits with unusual structure.
DEFAULT_Z_THRESHOLD = 2.5

# Minimum number of anomalous metrics to call INFECTED.
# Raised from 3 → 5 to reduce false positives on structurally unusual but clean circuits.
MIN_ANOMALIES_FOR_INFECTED = 5

# Gate type names matching the one-hot encoding in node_encoder.
_GATE_TYPE_NAMES = [
    "INPUT", "OUTPUT", "WIRE", "DFF", "AND", "OR", "NOT",
    "NAND", "NOR", "XOR", "XNOR", "BUF", "MUX", "LATCH", "UNKNOWN",
]


class StructuralVerifier:
    """Resolves UNCERTAIN GNN verdicts via graph invariant comparison.

    Usage:
        # Once, after training:
        verifier = StructuralVerifier()
        verifier.precompute_baseline(list_of_clean_circuit_graphs)
        verifier.save_baseline()

        # At inference:
        verifier = StructuralVerifier()
        verifier.load_baseline()
        verdict, reason = verifier.verify(suspect_graph)
    """

    def __init__(
        self,
        z_threshold: float = DEFAULT_Z_THRESHOLD,
        min_anomalies: int = MIN_ANOMALIES_FOR_INFECTED,
        baseline_path: Path | None = None,
    ) -> None:
        self._z_threshold = z_threshold
        self._min_anomalies = min_anomalies
        self._baseline_path = baseline_path or BASELINE_PATH
        self._baseline: dict[str, dict[str, float]] | None = None

    # ------------------------------------------------------------------
    # Baseline computation
    # ------------------------------------------------------------------

    def precompute_baseline(self, clean_graphs: list[CircuitGraph]) -> None:
        """Compute mean and std for each structural metric from clean graphs.

        Args:
            clean_graphs: List of CircuitGraph objects from known-clean circuits.
        """
        if not clean_graphs:
            raise ValueError("Need at least one clean graph to compute baseline")

        all_metrics: dict[str, list[float]] = defaultdict(list)

        for graph in clean_graphs:
            metrics = self._compute_metrics(graph)
            for key, value in metrics.items():
                all_metrics[key].append(value)

        baseline: dict[str, dict[str, float]] = {}
        for key, values in all_metrics.items():
            n = len(values)
            mean = sum(values) / n
            variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
            std = math.sqrt(variance)
            baseline[key] = {
                "mean": mean,
                "std": std,
                "min": min(values),
                "max": max(values),
                "n": n,
            }

        self._baseline = baseline
        logger.info(
            "Computed structural baseline from %d clean graphs (%d metrics)",
            len(clean_graphs),
            len(baseline),
        )

    def save_baseline(self, path: Path | None = None) -> Path:
        """Save the baseline to a JSON file."""
        if self._baseline is None:
            raise RuntimeError("No baseline computed — call precompute_baseline() first")

        out = path or self._baseline_path
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self._baseline, f, indent=2)
        logger.info("Saved structural baseline to %s", out)
        return out

    def load_baseline(self, path: Path | None = None) -> bool:
        """Load a precomputed baseline from JSON. Returns True if successful."""
        p = path or self._baseline_path
        if not p.exists():
            logger.warning("No structural baseline found at %s", p)
            return False
        try:
            with open(p, "r", encoding="utf-8") as f:
                self._baseline = json.load(f)
            logger.info("Loaded structural baseline from %s", p)
            return True
        except Exception as e:
            logger.error("Failed to load structural baseline: %s", e)
            return False

    @property
    def has_baseline(self) -> bool:
        return self._baseline is not None

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self, circuit_graph: CircuitGraph,
    ) -> tuple[TrojanVerdict, str]:
        """Compare a suspect circuit against the clean baseline.

        Args:
            circuit_graph: The circuit graph to verify.

        Returns:
            (verdict, reason) — CLEAN or INFECTED with explanation.
        """
        if self._baseline is None:
            return TrojanVerdict.UNCERTAIN, "No structural baseline available"

        metrics = self._compute_metrics(circuit_graph)
        anomalies: list[str] = []
        details: list[str] = []

        for key, value in metrics.items():
            baseline = self._baseline.get(key)
            if baseline is None:
                continue

            mean = baseline["mean"]
            std = baseline["std"]
            n = baseline.get("n", 0)

            if std > 1e-9 and n >= 5:
                z = abs(value - mean) / std
            else:
                # Baseline from < 5 samples or zero variance — not enough data
                # to make a meaningful comparison; skip this metric entirely.
                continue

            status = "OK"
            if z > self._z_threshold:
                anomalies.append(key)
                status = f"ANOMALY (z={z:.2f})"

            details.append(
                f"  {key}: {value:.4f} (baseline: {mean:.4f} +/- {std:.4f}) {status}"
            )

        num_anomalies = len(anomalies)
        total_metrics = len(metrics)

        if num_anomalies >= self._min_anomalies:
            verdict = TrojanVerdict.INFECTED
            reason = (
                f"Structural verification: {num_anomalies}/{total_metrics} metrics "
                f"deviate significantly from clean baseline. "
                f"Anomalous metrics: {', '.join(anomalies)}"
            )
        else:
            verdict = TrojanVerdict.CLEAN
            reason = (
                f"Structural verification: only {num_anomalies}/{total_metrics} "
                f"metrics deviate — circuit structure matches clean baseline."
            )

        logger.info(
            "Structural verification: %s (%d/%d anomalies)\n%s",
            verdict.value, num_anomalies, total_metrics, "\n".join(details),
        )

        return verdict, reason

    # ------------------------------------------------------------------
    # Metric computation — all O(N + E)
    # ------------------------------------------------------------------

    def _compute_metrics(self, circuit_graph: CircuitGraph) -> dict[str, float]:
        """Compute all structural metrics for a single graph."""
        data = circuit_graph.graph_data
        if data is None or data.x is None:
            return {}

        num_nodes = data.x.shape[0]
        if num_nodes == 0:
            return {}

        edge_index = data.edge_index
        num_edges = edge_index.shape[1]

        # Build adjacency
        in_degree = [0] * num_nodes
        out_degree = [0] * num_nodes
        adj_undirected: dict[int, list[int]] = defaultdict(list)

        for i in range(num_edges):
            src = edge_index[0, i].item()
            dst = edge_index[1, i].item()
            out_degree[src] += 1
            in_degree[dst] += 1
            adj_undirected[src].append(dst)
            adj_undirected[dst].append(src)

        # Gate types
        gate_types = self._get_gate_types(data.x)

        metrics: dict[str, float] = {}

        # 1. Degree distribution moments
        metrics["in_degree_mean"] = sum(in_degree) / num_nodes
        metrics["out_degree_mean"] = sum(out_degree) / num_nodes
        in_std = math.sqrt(
            sum((d - metrics["in_degree_mean"]) ** 2 for d in in_degree) / num_nodes
        )
        out_std = math.sqrt(
            sum((d - metrics["out_degree_mean"]) ** 2 for d in out_degree) / num_nodes
        )
        metrics["in_degree_std"] = in_std
        metrics["out_degree_std"] = out_std

        # 2. Graph density
        metrics["density"] = num_edges / max(num_nodes * num_nodes, 1)

        # 3. Connected components (weakly connected)
        num_components, component_sizes = self._count_components(
            adj_undirected, num_nodes
        )
        metrics["num_components"] = float(num_components)
        if component_sizes:
            largest = max(component_sizes)
            metrics["largest_component_ratio"] = largest / num_nodes
        else:
            metrics["largest_component_ratio"] = 0.0

        # 4. Gate type distribution
        type_counts: dict[str, int] = defaultdict(int)
        for gt in gate_types:
            type_counts[gt] += 1

        # Shannon entropy of gate type distribution
        entropy = 0.0
        for count in type_counts.values():
            p = count / num_nodes
            if p > 0:
                entropy -= p * math.log2(p)
        metrics["gate_type_entropy"] = entropy

        # Dominant type ratio
        if type_counts:
            metrics["dominant_type_ratio"] = max(type_counts.values()) / num_nodes
        else:
            metrics["dominant_type_ratio"] = 0.0

        # 5. Primary I/O ratio
        io_count = sum(1 for gt in gate_types if gt in ("INPUT", "OUTPUT"))
        metrics["io_ratio"] = io_count / num_nodes

        # 6. Edge-to-node ratio (captures circuit complexity)
        metrics["edge_node_ratio"] = num_edges / max(num_nodes, 1)

        return metrics

    @staticmethod
    def _get_gate_types(x: torch.Tensor) -> list[str]:
        """Extract canonical gate type from one-hot encoding."""
        types = []
        for i in range(x.shape[0]):
            one_hot = x[i, :VOCAB_SIZE]
            idx = one_hot.argmax().item()
            types.append(
                _GATE_TYPE_NAMES[idx] if idx < len(_GATE_TYPE_NAMES) else "UNKNOWN"
            )
        return types

    @staticmethod
    def _count_components(
        adj: dict[int, list[int]], num_nodes: int,
    ) -> tuple[int, list[int]]:
        """Count weakly connected components and their sizes. O(N + E)."""
        visited = [False] * num_nodes
        component_sizes: list[int] = []

        for start in range(num_nodes):
            if visited[start]:
                continue
            size = 0
            stack = [start]
            visited[start] = True
            while stack:
                node = stack.pop()
                size += 1
                for neighbor in adj.get(node, []):
                    if not visited[neighbor]:
                        visited[neighbor] = True
                        stack.append(neighbor)
            component_sizes.append(size)

        return len(component_sizes), component_sizes
