"""Algorithmic trojan localization via structural anomaly detection.

Instead of relying on GNN node-level predictions (which suffer from extreme
class imbalance), this module uses graph-structural heuristics to identify
suspicious gates after the GNN has flagged a circuit as trojan-infected.

Strategies:
    1. Connectivity anomaly — gates with unusual fan-in/fan-out for their type
    2. Neighborhood entropy — gates surrounded by unusual type diversity
    3. Isolation detection — gates weakly connected to primary I/O
    4. Rare subgraph patterns — small clusters disconnected from main logic
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque

import torch

from backend.netlist_graph_builder.models import CircuitGraph
from backend.netlist_graph_builder.node_encoder import VOCAB_SIZE

logger = logging.getLogger(__name__)


def localize_trojans(
    circuit_graph: CircuitGraph,
    suspicion_threshold: float = 0.5,
) -> dict[str, float]:
    """Compute per-gate suspicion scores using structural heuristics.

    Args:
        circuit_graph: The circuit graph to analyze.
        suspicion_threshold: Not used for filtering here — all scores returned.

    Returns:
        Dict mapping gate name -> suspicion score in [0, 1].
    """
    data = circuit_graph.graph_data
    if data is None or data.x is None:
        return {}

    num_nodes = data.x.shape[0]
    if num_nodes == 0:
        return {}

    # Build adjacency lists
    edge_index = data.edge_index
    adj_out: dict[int, list[int]] = defaultdict(list)
    adj_in: dict[int, list[int]] = defaultdict(list)
    for i in range(edge_index.shape[1]):
        src = edge_index[0, i].item()
        dst = edge_index[1, i].item()
        adj_out[src].append(dst)
        adj_in[dst].append(src)

    # Extract per-node info from features
    x = data.x
    gate_types = _get_gate_types(x)
    fan_ins = [len(adj_in.get(i, [])) for i in range(num_nodes)]
    fan_outs = [len(adj_out.get(i, [])) for i in range(num_nodes)]

    # Compute individual anomaly signals
    scores = torch.zeros(num_nodes, dtype=torch.float)

    _score_connectivity_anomaly(scores, gate_types, fan_ins, fan_outs)
    _score_neighborhood_entropy(scores, adj_out, adj_in, gate_types, num_nodes)
    _score_io_isolation(scores, adj_out, adj_in, gate_types, num_nodes)
    _score_rare_clusters(scores, adj_out, adj_in, gate_types, num_nodes)

    # Normalize to [0, 1]
    max_score = scores.max().item()
    if max_score > 0:
        scores = scores / max_score

    # Build result dict
    gate_scores: dict[str, float] = {}
    for idx in range(num_nodes):
        gate_name = circuit_graph.node_to_gate.get(idx, f"node_{idx}")
        gate_scores[gate_name] = round(scores[idx].item(), 6)

    return gate_scores


def _get_gate_types(x: torch.Tensor) -> list[str]:
    """Extract canonical gate type from one-hot encoding."""
    type_names = [
        "INPUT", "OUTPUT", "WIRE", "DFF", "AND", "OR", "NOT",
        "NAND", "NOR", "XOR", "XNOR", "BUF", "MUX", "LATCH", "UNKNOWN",
    ]
    types = []
    for i in range(x.shape[0]):
        one_hot = x[i, :VOCAB_SIZE]
        idx = one_hot.argmax().item()
        types.append(type_names[idx] if idx < len(type_names) else "UNKNOWN")
    return types


def _score_connectivity_anomaly(
    scores: torch.Tensor,
    gate_types: list[str],
    fan_ins: list[int],
    fan_outs: list[int],
) -> None:
    """Score gates whose fan-in/fan-out deviates from their type's average.

    Trojan gates often have atypical connectivity for their gate type
    (e.g., an AND gate with unusually high fan-out feeding a trigger).
    """
    # Compute per-type statistics
    type_stats: dict[str, list[float]] = defaultdict(list)
    for i, gt in enumerate(gate_types):
        if gt not in ("INPUT", "OUTPUT"):
            type_stats[gt].append(fan_ins[i] + fan_outs[i])

    type_mean: dict[str, float] = {}
    type_std: dict[str, float] = {}
    for gt, vals in type_stats.items():
        m = sum(vals) / len(vals) if vals else 0
        type_mean[gt] = m
        type_std[gt] = math.sqrt(sum((v - m) ** 2 for v in vals) / max(len(vals), 1))

    for i, gt in enumerate(gate_types):
        if gt in ("INPUT", "OUTPUT"):
            continue
        total = fan_ins[i] + fan_outs[i]
        mean = type_mean.get(gt, 0)
        std = type_std.get(gt, 1)
        if std > 0:
            z_score = abs(total - mean) / std
            # Convert z-score to 0-1 signal (z >= 3 -> ~1.0)
            scores[i] += min(z_score / 3.0, 1.0) * 0.3


def _score_neighborhood_entropy(
    scores: torch.Tensor,
    adj_out: dict[int, list[int]],
    adj_in: dict[int, list[int]],
    gate_types: list[str],
    num_nodes: int,
) -> None:
    """Score gates surrounded by unusually diverse gate types.

    Trojan circuitry often mixes gate types that wouldn't normally
    appear together in standard logic cones.
    """
    for i in range(num_nodes):
        if gate_types[i] in ("INPUT", "OUTPUT"):
            continue
        neighbors = set(adj_out.get(i, [])) | set(adj_in.get(i, []))
        if not neighbors:
            scores[i] += 0.2  # isolated gates are suspicious
            continue

        # Shannon entropy of neighbor gate types
        type_counts: dict[str, int] = defaultdict(int)
        for n in neighbors:
            type_counts[gate_types[n]] += 1
        total = len(neighbors)
        entropy = 0.0
        for count in type_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        # Normalize: max entropy = log2(num_types), high entropy = unusual
        max_entropy = math.log2(max(len(type_counts), 2))
        norm_entropy = entropy / max_entropy if max_entropy > 0 else 0
        scores[i] += norm_entropy * 0.25


def _score_io_isolation(
    scores: torch.Tensor,
    adj_out: dict[int, list[int]],
    adj_in: dict[int, list[int]],
    gate_types: list[str],
    num_nodes: int,
) -> None:
    """Score gates that are far from primary inputs AND outputs.

    Trojan gates are often inserted in locations not on the main
    functional data path — they're far from both inputs and outputs.
    """
    input_nodes = {i for i, t in enumerate(gate_types) if t == "INPUT"}
    output_nodes = {i for i, t in enumerate(gate_types) if t == "OUTPUT"}

    # BFS forward from inputs
    dist_from_input = _bfs_distances(input_nodes, adj_out, num_nodes)
    # BFS backward from outputs
    dist_from_output = _bfs_distances(output_nodes, adj_in, num_nodes)

    max_dist = max(max(dist_from_input), max(dist_from_output), 1)

    for i in range(num_nodes):
        if gate_types[i] in ("INPUT", "OUTPUT"):
            continue
        d_in = dist_from_input[i] / max_dist
        d_out = dist_from_output[i] / max_dist
        # Gates far from both I/O are more suspicious
        isolation = min(d_in, 1.0) * min(d_out, 1.0)
        scores[i] += isolation * 0.35


def _bfs_distances(
    sources: set[int],
    adj: dict[int, list[int]],
    num_nodes: int,
) -> list[float]:
    """BFS from source nodes, return distance per node (inf if unreachable)."""
    dist = [float("inf")] * num_nodes
    queue = deque()
    for s in sources:
        dist[s] = 0
        queue.append(s)
    while queue:
        node = queue.popleft()
        for neighbor in adj.get(node, []):
            if dist[neighbor] > dist[node] + 1:
                dist[neighbor] = dist[node] + 1
                queue.append(neighbor)
    # Replace inf with max finite distance + 1
    finite = [d for d in dist if d != float("inf")]
    replacement = max(finite, default=0) + 1
    return [d if d != float("inf") else replacement for d in dist]


def _score_rare_clusters(
    scores: torch.Tensor,
    adj_out: dict[int, list[int]],
    adj_in: dict[int, list[int]],
    gate_types: list[str],
    num_nodes: int,
) -> None:
    """Score gates in small weakly-connected components.

    Trojan logic is often a small circuit fragment inserted alongside
    the main design. Gates in tiny connected components are suspicious.
    """
    # Find weakly connected components
    visited = [False] * num_nodes
    components: list[list[int]] = []

    for start in range(num_nodes):
        if visited[start] or gate_types[start] in ("INPUT", "OUTPUT"):
            continue
        component: list[int] = []
        queue = deque([start])
        visited[start] = True
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbor in adj_out.get(node, []) + adj_in.get(node, []):
                if not visited[neighbor] and gate_types[neighbor] not in ("INPUT", "OUTPUT"):
                    visited[neighbor] = True
                    queue.append(neighbor)
        components.append(component)

    if not components:
        return

    # Largest component is assumed to be the main design
    largest_size = max(len(c) for c in components)

    for component in components:
        if len(component) == largest_size:
            continue  # skip main design
        # Smaller components are more suspicious
        size_ratio = len(component) / largest_size
        suspicion = max(1.0 - size_ratio, 0.0) * 0.35
        for node in component:
            scores[node] += suspicion
