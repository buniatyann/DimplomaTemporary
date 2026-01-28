"""TrojanClassifier facade for GNN-based trojan detection."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

from backend.core.exceptions import ClassificationError
from backend.core.history import History
from backend.core.outcome import StageOutcome
from backend.netlist_graph_builder.models import CircuitGraph
from backend.trojan_classifier.architectures.gat import GATClassifier
from backend.trojan_classifier.architectures.gcn import GCNClassifier
from backend.trojan_classifier.architectures.gin import GINClassifier
from backend.trojan_classifier.models import (
    ClassificationResult,
    TrojanVerdict,
)

logger = logging.getLogger(__name__)

STAGE = "trojan_classifier"

WEIGHTS_DIR = Path(__file__).parent / "weights"

ARCHITECTURE_MAP = {
    "gcn": GCNClassifier,
    "gat": GATClassifier,
    "gin": GINClassifier,
}


class TrojanClassifier:
    """Applies trained GNN models to circuit graphs for trojan detection."""

    def __init__(
        self,
        history: History,
        architecture: str = "gcn",
        model_path: Path | None = None,
        confidence_threshold: float = 0.7,
        device: str | None = None,
    ) -> None:
        self._history = history
        self._architecture = architecture
        self._model_path = model_path
        self._confidence_threshold = confidence_threshold
        self._model: torch.nn.Module | None = None
        self._model_version = "0.1.0"

        if device is None:
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self._device = torch.device(device)

    def process(
        self, circuit_graph: CircuitGraph
    ) -> StageOutcome[ClassificationResult]:
        """Classify a circuit graph as clean or trojan-infected.

        Args:
            circuit_graph: CircuitGraph from netlist_graph_builder.

        Returns:
            StageOutcome wrapping a ClassificationResult.
        """
        self._history.begin_stage(STAGE)
        start = time.time()

        try:
            self._load_model(circuit_graph)
        except ClassificationError as e:
            self._history.error(STAGE, str(e), data=e.context)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(str(e), stage_name=STAGE)

        try:
            result = self._classify(circuit_graph)
        except Exception as e:
            msg = f"Classification failed: {e}"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        duration = time.time() - start

        # Record in history
        self._history.record(STAGE, "verdict", result.verdict.value)
        self._history.record(STAGE, "confidence", result.confidence)
        self._history.record(STAGE, "trojan_probability", result.trojan_probability)
        self._history.record(STAGE, "model_version", result.model_version)
        self._history.record(STAGE, "architecture", result.architecture)
        self._history.record(STAGE, "inference_duration", duration)
        self._history.record(STAGE, "device", str(self._device))

        if result.verdict == TrojanVerdict.INFECTED:
            top_suspicious = sorted(
                result.gate_suspicion_scores.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )[:10]
            self._history.record(
                STAGE,
                "top_suspicious_gates",
                [{"gate": g, "score": s} for g, s in top_suspicious],
            )

        self._history.info(
            STAGE,
            f"Classification: {result.verdict.value} "
            f"(confidence={result.confidence:.4f}, p(trojan)={result.trojan_probability:.4f})",
        )
        self._history.end_stage(STAGE, status="completed")

        return StageOutcome.ok(result, stage_name=STAGE)

    def _load_model(self, circuit_graph: CircuitGraph) -> None:
        """Load the GNN model, initializing with random weights if no checkpoint exists."""
        if self._model is not None:
            return

        if self._architecture not in ARCHITECTURE_MAP:
            raise ClassificationError(
                f"Unknown architecture: {self._architecture}",
                model_name=self._architecture,
            )

        input_dim = circuit_graph.graph_data.x.shape[1] if circuit_graph.graph_data is not None else 17

        model_cls = ARCHITECTURE_MAP[self._architecture]
        self._model = model_cls(input_dim=input_dim)

        # Try to load pretrained weights
        if self._model_path is not None:
            weight_file = self._model_path
        else:
            weight_file = WEIGHTS_DIR / f"{self._architecture}_weights.pt"

        if weight_file.exists():
            try:
                state_dict = torch.load(weight_file, map_location=self._device, weights_only=True)
                self._model.load_state_dict(state_dict)
                self._history.info(STAGE, f"Loaded weights from {weight_file}")
            except Exception as e:
                self._history.warning(
                    STAGE,
                    f"Failed to load weights from {weight_file}: {e}. Using random initialization.",
                )
        else:
            self._history.warning(
                STAGE,
                f"No pretrained weights found at {weight_file}. Using random initialization.",
            )

        self._model.to(self._device)
        self._model.eval()

    def _classify(self, circuit_graph: CircuitGraph) -> ClassificationResult:
        """Run inference on a circuit graph."""
        assert self._model is not None

        data = circuit_graph.graph_data
        data = data.to(self._device)

        # Create batch tensor (single graph)
        batch = torch.zeros(data.x.shape[0], dtype=torch.long, device=self._device)

        with torch.no_grad():
            logits = self._model(data.x, data.edge_index, batch)
            probs = F.softmax(logits, dim=1)

        # Class 0 = clean, Class 1 = infected
        trojan_prob = probs[0, 1].item()
        clean_prob = probs[0, 0].item()
        confidence = max(trojan_prob, clean_prob)

        if confidence < self._confidence_threshold:
            verdict = TrojanVerdict.UNCERTAIN
        elif trojan_prob > clean_prob:
            verdict = TrojanVerdict.INFECTED
        else:
            verdict = TrojanVerdict.CLEAN

        # Get per-node suspicion scores
        gate_scores = self._compute_node_attributions(circuit_graph)

        return ClassificationResult(
            verdict=verdict,
            confidence=confidence,
            trojan_probability=trojan_prob,
            gate_suspicion_scores=gate_scores,
            model_version=self._model_version,
            architecture=self._architecture,
        )

    def _compute_node_attributions(
        self, circuit_graph: CircuitGraph
    ) -> dict[str, float]:
        """Compute per-node suspicion scores using gradient-based attribution."""
        assert self._model is not None

        data = circuit_graph.graph_data
        data = data.to(self._device)

        x = data.x.clone().requires_grad_(True)

        # Get node embeddings
        node_embeddings = self._model.get_node_embeddings(x, data.edge_index)

        # Compute gradient of trojan class score w.r.t. node embeddings
        trojan_signal = node_embeddings.sum(dim=1)
        trojan_signal.sum().backward()

        if x.grad is not None:
            # Use L2 norm of input gradients as attribution
            attributions = x.grad.norm(dim=1).cpu().tolist()
        else:
            attributions = [0.0] * data.x.shape[0]

        # Normalize to [0, 1]
        max_attr = max(attributions) if attributions else 1.0
        if max_attr > 0:
            attributions = [a / max_attr for a in attributions]

        # Map node indices to gate names
        gate_scores: dict[str, float] = {}
        for idx, score in enumerate(attributions):
            gate_name = circuit_graph.node_to_gate.get(idx, f"node_{idx}")
            gate_scores[gate_name] = round(score, 6)

        return gate_scores
