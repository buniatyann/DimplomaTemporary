"""Ensemble classifier using cascade + weighted average over GCN, GAT, GIN."""

from __future__ import annotations

import logging
import math
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import torch
import torch.nn.functional as F

from backend.core.exceptions import ClassificationError
from backend.core.history import History
from backend.core.outcome import StageOutcome
from backend.netlist_graph_builder.models import CircuitGraph
from backend.trojan_classifier.algorithmic_analyzer import AlgorithmicAnalyzer
from backend.trojan_classifier.architectures.gat import GATClassifier
from backend.trojan_classifier.architectures.gcn import GCNClassifier
from backend.trojan_classifier.architectures.gin import GINClassifier
from backend.trojan_classifier.models import (
    AlgorithmicResult,
    ClassificationResult,
    TrojanLocation,
    TrojanVerdict,
)
from backend.trojan_classifier.structural_verifier import StructuralVerifier

if TYPE_CHECKING:
    from backend.syntax_parser.models import ParsedModule

logger = logging.getLogger(__name__)

STAGE = "trojan_classifier"

_HDL_SUFFIXES = frozenset({".v", ".sv", ".vh", ".svh"})


def _validate_source_path(
    path: str | None,
    parsed_modules: "list[ParsedModule] | None",
) -> str | None:
    """Return `path` only if it's a real user-supplied HDL source file.

    Filters out pyslang/Yosys internal paths (.cc, techlib cells, temp-dir
    copies) by enforcing three constraints:
      1. Suffix must be .v / .sv / .vh / .svh.
      2. File must exist on disk.
      3. When parsed_modules is available, the resolved path must match one
         of the source files the parser actually consumed (allowlist).

    This is the single choke point for TrojanLocation.source_file — every
    resolved path goes through here before leaving the classifier.
    """
    if not path:
        return None
    try:
        p = Path(path)
    except (TypeError, ValueError):
        return None
    if p.suffix.lower() not in _HDL_SUFFIXES:
        return None
    if not p.is_file():
        return None
    if parsed_modules:
        allowed: set[str] = set()
        for mod in parsed_modules:
            if mod.source_path:
                try:
                    allowed.add(str(Path(mod.source_path).resolve()))
                except (OSError, ValueError):
                    continue
        if allowed:
            try:
                resolved = str(p.resolve())
            except (OSError, ValueError):
                return None
            if resolved not in allowed:
                return None
    return str(p)

WEIGHTS_DIR = Path(__file__).parent / "weights"

ARCHITECTURE_MAP: dict[str, type[torch.nn.Module]] = {
    "gcn": GCNClassifier,
    "gat": GATClassifier,
    "gin": GINClassifier,
}

# Default model weights for weighted averaging (tunable per validation set).
# GIN gets a slight edge for its stronger graph-isomorphism properties.
DEFAULT_WEIGHTS: dict[str, float] = {
    "gcn": 0.30,
    "gat": 0.35,
    "gin": 0.35,
}

# Cascade: if the first model is this confident, skip the rest.
DEFAULT_CASCADE_THRESHOLD = 0.92

# Algorithmic analysis decision thresholds (graph_algo_score)
ALGO_CONFIRMS_THRESHOLD  = 0.15   # >= this → algo confirms trojan
ALGO_DISAGREES_THRESHOLD = 0.05   # <= this → algo disagrees (circuit looks clean)

# Score fusion weights: combined_score = GNN_W * gnn + ALGO_W * algo
GNN_SCORE_WEIGHT  = 0.6
ALGO_SCORE_WEIGHT = 0.4

# Node-level suspicion threshold for location reporting.
# With 2-class softmax, a random node scores ~0.5; 0.3 is far too permissive
# and causes near-universal false positives on large circuits.  0.6 requires
# the model to lean clearly toward "trojan" before flagging a node.
SUSPICION_THRESHOLD = 0.6

# Percentage of trojan nodes to trigger high-risk alert.
HIGH_RISK_THRESHOLD = 5.0

# Order in which models are evaluated in cascade (cheapest first).
CASCADE_ORDER = ["gcn", "gin", "gat"]


class EnsembleClassifier:
    """Cascade + weighted-average ensemble over separately trained GCN, GAT, GIN.

    Graph-level detection:
        Runs models in cascade order (cheapest first).  If the first model's
        confidence exceeds ``cascade_threshold``, the remaining models are
        skipped.  Otherwise all models run and their graph-level trojan
        probabilities are combined via a weighted average.

    Node-level detection:
        Node-level softmax outputs from every model that ran are combined
        with the same weights.  The resulting per-node scores are used to
        locate suspicious gates, which are then mapped back to source
        file:line via the parsed module data.
    """

    def __init__(
        self,
        history: History,
        model_weights: dict[str, float] | None = None,
        cascade_threshold: float = DEFAULT_CASCADE_THRESHOLD,
        confidence_threshold: float = 0.7,
        suspicion_threshold: float = SUSPICION_THRESHOLD,
        risk_threshold: float = HIGH_RISK_THRESHOLD,
        device: str | None = None,
        selected_models: list[str] | None = None,
        disable_cascade: bool = False,
    ) -> None:
        self._history = history
        self._model_weights = model_weights or dict(DEFAULT_WEIGHTS)
        self._cascade_threshold = cascade_threshold
        self._confidence_threshold = confidence_threshold
        self._suspicion_threshold = suspicion_threshold
        self._risk_threshold = risk_threshold
        self._disable_cascade = disable_cascade
        self._model_version = "0.1.0"
        self._parsed_modules: list[ParsedModule] | None = None

        # Filter cascade order to only the selected models
        if selected_models is not None:
            self._active_models = [m for m in CASCADE_ORDER if m in selected_models]
            if not self._active_models:
                self._active_models = list(CASCADE_ORDER)
        else:
            self._active_models = list(CASCADE_ORDER)

        if device is None:
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self._device = torch.device(device)

        # Lazily loaded models: arch_name -> nn.Module
        self._models: dict[str, torch.nn.Module] = {}

        # Structural verifier for resolving UNCERTAIN verdicts
        self._structural_verifier = StructuralVerifier()
        self._structural_verifier.load_baseline()

        # Algorithmic analyzer (SCOAP + CoI)
        self._algorithmic_analyzer = AlgorithmicAnalyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_parsed_modules(self, modules: list[ParsedModule]) -> None:
        """Set parsed module data for source location resolution."""
        self._parsed_modules = modules

    def process(
        self,
        circuit_graph: CircuitGraph,
        parsed_modules: list[ParsedModule] | None = None,
    ) -> StageOutcome[ClassificationResult]:
        """Run ensemble classification on a circuit graph.

        Args:
            circuit_graph: CircuitGraph from netlist_graph_builder.
            parsed_modules: Optional parsed modules for source location resolution.

        Returns:
            StageOutcome wrapping a ClassificationResult.
        """
        if parsed_modules is not None:
            self._parsed_modules = parsed_modules

        self._history.begin_stage(STAGE)
        start = time.time()

        # Load all model weights up front so failures are caught early.
        try:
            self._load_models(circuit_graph)
        except ClassificationError as e:
            self._history.error(STAGE, str(e), data=e.context)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(str(e), stage_name=STAGE)

        try:
            result = self._classify_ensemble(circuit_graph)
        except Exception as e:
            msg = f"Ensemble classification failed: {e}"
            self._history.error(STAGE, msg)
            self._history.end_stage(STAGE, status="failed")
            return StageOutcome.fail(msg, stage_name=STAGE)

        duration = time.time() - start
        self._record_history(result, duration)
        self._history.end_stage(STAGE, status="completed")

        return StageOutcome.ok(result, stage_name=STAGE)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_models(self, circuit_graph: CircuitGraph) -> None:
        """Load selected architectures (skip those already loaded)."""
        input_dim = (
            circuit_graph.graph_data.x.shape[1]
            if circuit_graph.graph_data is not None
            else 17
        )

        for arch_name in self._active_models:
            if arch_name in self._models:
                continue

            model_cls = ARCHITECTURE_MAP[arch_name]
            model = model_cls(input_dim=input_dim)

            weight_file = WEIGHTS_DIR / f"{arch_name}_weights.pt"
            if weight_file.exists():
                try:
                    state_dict = torch.load(
                        weight_file, map_location=self._device, weights_only=True,
                    )
                    model.load_state_dict(state_dict)
                    self._history.info(STAGE, f"[ensemble] Loaded {arch_name} weights from {weight_file}")
                except Exception as e:
                    self._history.warning(
                        STAGE,
                        f"[ensemble] Failed to load {arch_name} weights: {e}. "
                        f"Using random initialization.",
                    )
            else:
                self._history.warning(
                    STAGE,
                    f"[ensemble] No weights found for {arch_name} at {weight_file}. "
                    f"Using random initialization.",
                )

            model.to(self._device)
            model.eval()
            self._models[arch_name] = model

    # ------------------------------------------------------------------
    # Cascade + weighted-average inference
    # ------------------------------------------------------------------

    def _run_single_model(
        self,
        arch_name: str,
        data: torch.Tensor,
        batch: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Run a single model forward pass and return (graph_probs, node_probs)."""
        model = self._models[arch_name]
        with torch.no_grad():
            graph_logits, node_logits = model(data.x, data.edge_index, batch)
            graph_probs = F.softmax(graph_logits, dim=1)
            node_probs = F.softmax(node_logits, dim=1)
        
        return graph_probs, node_probs

    def _classify_ensemble(self, circuit_graph: CircuitGraph) -> ClassificationResult:
        """Cascade through models, combine with weighted average."""
        data = circuit_graph.graph_data.to(self._device)
        num_nodes = data.x.shape[0]
        batch = torch.zeros(num_nodes, dtype=torch.long, device=self._device)

        # Collect per-model outputs.
        model_graph_probs: dict[str, torch.Tensor] = {}
        model_node_probs: dict[str, torch.Tensor] = {}
        models_run: list[str] = []

        for arch_name in self._active_models:
            graph_probs, node_probs = self._run_single_model(arch_name, data, batch)
            model_graph_probs[arch_name] = graph_probs
            model_node_probs[arch_name] = node_probs
            models_run.append(arch_name)

            # Cascade early-exit: if this model is very confident, skip remaining.
            trojan_p = graph_probs[0, 1].item()
            clean_p = graph_probs[0, 0].item()
            conf = max(trojan_p, clean_p)

            self._history.info(
                STAGE,
                f"[ensemble] {arch_name}: p(trojan)={trojan_p:.4f}, "
                f"confidence={conf:.4f}",
            )

            if (
                not self._disable_cascade
                and conf >= self._cascade_threshold
                and len(models_run) < len(self._active_models)
            ):
                self._history.info(
                    STAGE,
                    f"[ensemble] Cascade early-exit after {arch_name} "
                    f"(confidence {conf:.4f} >= {self._cascade_threshold})",
                )
                break

        # ── Graph-level: weighted average ────────────────────────────
        per_model_results: dict[str, dict[str, float]] = {}
        total_weight = 0.0
        weighted_trojan_prob = 0.0

        for arch_name in models_run:
            w = self._model_weights.get(arch_name, 1.0 / len(models_run))
            tp = model_graph_probs[arch_name][0, 1].item()
            cp = model_graph_probs[arch_name][0, 0].item()
            per_model_results[arch_name] = {
                "trojan_probability": round(tp, 6),
                "confidence": round(max(tp, cp), 6),
            }
        
            weighted_trojan_prob += w * tp
            total_weight += w

        if total_weight > 0:
            weighted_trojan_prob /= total_weight
        
        ensemble_clean_prob = 1.0 - weighted_trojan_prob
        ensemble_confidence = max(weighted_trojan_prob, ensemble_clean_prob)

        # Verdict
        if ensemble_confidence < self._confidence_threshold:
            verdict = TrojanVerdict.UNCERTAIN
        elif weighted_trojan_prob > ensemble_clean_prob:
            verdict = TrojanVerdict.INFECTED
        else:
            verdict = TrojanVerdict.CLEAN

        # Model agreement: what fraction of models agree on the majority verdict?
        majority_infected = weighted_trojan_prob > 0.5
        agree_count = sum(
            1
            for a in models_run
            if (model_graph_probs[a][0, 1].item() > 0.5) == majority_infected
        )
        model_agreement = agree_count / len(models_run) if models_run else 1.0

        # ── Node-level: weighted average of node probs ───────────────
        combined_node_probs = torch.zeros(num_nodes, 2, device=self._device)
        total_nw = 0.0
        for arch_name in models_run:
            w = self._model_weights.get(arch_name, 1.0 / len(models_run))
            combined_node_probs += w * model_node_probs[arch_name]
            total_nw += w
        
        if total_nw > 0:
            combined_node_probs /= total_nw

        gnn_gate_scores = self._extract_node_scores(circuit_graph, combined_node_probs)

        # ── Algorithmic analysis (SCOAP + CoI) ──────────────────────────────
        algo_result = self._run_algorithmic_analysis(circuit_graph)
        self._history.info(
            STAGE,
            f"[algorithmic] graph_algo_score={algo_result.graph_algo_score:.4f}, "
            f"zero_coi={len(algo_result.zero_coi_output_nodes)}, "
            f"isolated={len(algo_result.isolated_nodes)}, "
            f"high_cc1={len(algo_result.high_cc1_nodes)}",
        )

        # Merge GNN + algorithmic per-node scores
        gate_scores = self._merge_node_scores(gnn_gate_scores, algo_result)

        # Combined decision: may upgrade UNCERTAIN or downgrade INFECTED
        verdict, algo_reason = self._apply_combined_decision_logic(
            verdict, weighted_trojan_prob, algo_result,
        )
        if algo_reason:
            self._history.info(STAGE, f"[algorithmic_decision] {algo_reason}")

        trojan_locations = self._locate_trojans(circuit_graph, gate_scores, algo_result)

        total_nodes = len(gate_scores)
        suspicious_count = len(trojan_locations)
        trojan_percentage = (suspicious_count / total_nodes * 100) if total_nodes > 0 else 0.0
        high_risk = trojan_percentage >= self._risk_threshold
        trojan_modules = list({loc.module_name for loc in trojan_locations})

        # High-risk override: when node-level analysis finds a significant
        # fraction of suspicious gates (>= risk threshold) but the graph-level
        # GNN still says CLEAN, the node evidence should prevail.  This catches
        # cases where the GNN graph-level head is confused by the dominant clean
        # logic in a large design, but the node-level scores correctly identify
        # the trojan subgraph.
        if high_risk and verdict == TrojanVerdict.CLEAN:
            verdict = TrojanVerdict.INFECTED
            self._history.info(
                STAGE,
                f"[high_risk_override] Upgraded CLEAN -> INFECTED: "
                f"{trojan_percentage:.2f}% of nodes flagged (>= {self._risk_threshold}%) "
                f"with algo_score={algo_result.graph_algo_score:.4f}",
            )

        # False-positive sanity check
        if verdict == TrojanVerdict.INFECTED:
            should_downgrade, reason = self._is_likely_false_positive(
                total_nodes, suspicious_count, trojan_percentage,
                trojan_locations, gate_scores, model_agreement,
            )

            if should_downgrade:
                verdict = TrojanVerdict.UNCERTAIN
                self._history.warning(STAGE, f"Downgraded INFECTED -> UNCERTAIN: {reason}")

        # Structural verifier: last-resort for remaining UNCERTAIN verdicts
        if verdict == TrojanVerdict.UNCERTAIN and self._structural_verifier.has_baseline:
            sv_verdict, sv_reason = self._structural_verifier.verify(circuit_graph)
            self._history.info(STAGE, f"[structural_verifier] {sv_reason}")
            if sv_verdict == TrojanVerdict.INFECTED and weighted_trojan_prob > 0.4:
                verdict = TrojanVerdict.INFECTED
                self._history.info(
                    STAGE,
                    f"[structural_verifier] Confirmed INFECTED "
                    f"(GNN p(trojan)={weighted_trojan_prob:.4f} > 0.4 + structural anomalies)",
                )
            elif sv_verdict == TrojanVerdict.CLEAN:
                verdict = TrojanVerdict.CLEAN
            else:
                self._history.info(
                    STAGE,
                    f"[structural_verifier] Structural anomalies detected but GNN "
                    f"p(trojan)={weighted_trojan_prob:.4f} <= 0.4 — keeping UNCERTAIN",
                )

        return ClassificationResult(
            verdict=verdict,
            confidence=round(ensemble_confidence, 6),
            trojan_probability=round(weighted_trojan_prob, 6),
            gate_suspicion_scores=gate_scores,
            model_version=self._model_version,
            architecture="ensemble",
            trojan_locations=trojan_locations,
            trojan_node_percentage=round(trojan_percentage, 4),
            trojan_modules=trojan_modules,
            high_risk=high_risk,
            risk_threshold=self._risk_threshold,
            ensemble_used=True,
            ensemble_models_run=models_run,
            per_model_results=per_model_results,
            model_agreement=round(model_agreement, 4),
            algorithmic_result=algo_result,
        )

    # ------------------------------------------------------------------
    # Node-level helpers (reused from TrojanClassifier)
    # ------------------------------------------------------------------

    def _extract_node_scores(
        self, circuit_graph: CircuitGraph, node_probs: torch.Tensor,
    ) -> dict[str, float]:
        scores = node_probs[:, 1].cpu().tolist()
        gate_scores: dict[str, float] = {}
        for idx, score in enumerate(scores):
            gate_name = circuit_graph.node_to_gate.get(idx, f"node_{idx}")
            gate_scores[gate_name] = round(score, 6)

        return gate_scores

    def _run_algorithmic_analysis(
        self, circuit_graph: CircuitGraph,
    ) -> AlgorithmicResult:
        """Run SCOAP + CoI analysis; return empty result on failure."""
        try:
            return self._algorithmic_analyzer.analyze(circuit_graph)
        except Exception as e:
            self._history.warning(STAGE, f"[algorithmic] Analysis failed: {e}")
            return AlgorithmicResult()

    def _merge_node_scores(
        self,
        gnn_scores: dict[str, float],
        algo_result: AlgorithmicResult,
    ) -> dict[str, float]:
        """Fuse GNN and algorithmic per-node scores: 0.6*gnn + 0.4*algo."""
        merged: dict[str, float] = {}
        for gate_name, gnn_score in gnn_scores.items():
            info = algo_result.node_info.get(gate_name)
            a_score = info.algo_suspicion_score if info is not None else 0.0
            merged[gate_name] = round(
                GNN_SCORE_WEIGHT * gnn_score + ALGO_SCORE_WEIGHT * a_score, 6,
            )
        
        return merged

    def _apply_combined_decision_logic(
        self,
        gnn_verdict: TrojanVerdict,
        weighted_trojan_prob: float,
        algo_result: AlgorithmicResult,
    ) -> tuple[TrojanVerdict, str]:
        """Apply combined GNN + algorithmic decision logic.

        Decision matrix:
            GNN=INFECTED + algo confirms  → INFECTED  (high confidence)
            GNN=INFECTED + algo disagrees → UNCERTAIN (GNN likely confused)
            GNN=CLEAN    + algo confirms  → UNCERTAIN (stealthy trojan possible)
            GNN=CLEAN    + algo disagrees → CLEAN
            GNN=UNCERTAIN + algo confirms + p>0.4 → INFECTED
            GNN=UNCERTAIN + algo disagrees        → CLEAN
            GNN=UNCERTAIN + neither               → UNCERTAIN
        """
        gas = algo_result.graph_algo_score
        n   = algo_result.analysis_node_count
        large_circuit = n >= 200
        confirms_threshold = ALGO_CONFIRMS_THRESHOLD if not large_circuit else 0.60
        algo_confirms  = gas >= confirms_threshold
        algo_disagrees = gas <= ALGO_DISAGREES_THRESHOLD

        if gnn_verdict == TrojanVerdict.INFECTED:
            if algo_confirms:
                return TrojanVerdict.INFECTED, (
                    f"GNN=INFECTED confirmed by algo (gas={gas:.4f})"
                )
            elif algo_disagrees and not large_circuit:
                return TrojanVerdict.UNCERTAIN, (
                    f"GNN=INFECTED downgraded: algo disagrees (gas={gas:.4f})"
                )
            return TrojanVerdict.INFECTED, ""

        elif gnn_verdict == TrojanVerdict.CLEAN:
            if algo_confirms and not large_circuit:
                return TrojanVerdict.UNCERTAIN, (
                    f"GNN=CLEAN upgraded to UNCERTAIN: algo suspicious (gas={gas:.4f})"
                )
            return TrojanVerdict.CLEAN, ""

        else:  # UNCERTAIN
            if algo_confirms and weighted_trojan_prob > 0.4:
                return TrojanVerdict.INFECTED, (
                    f"GNN=UNCERTAIN resolved to INFECTED: algo confirms (gas={gas:.4f}) "
                    f"+ p(trojan)={weighted_trojan_prob:.4f} > 0.4"
                )
            elif algo_disagrees:
                return TrojanVerdict.CLEAN, (
                    f"GNN=UNCERTAIN resolved to CLEAN: algo disagrees (gas={gas:.4f})"
                )
            return TrojanVerdict.UNCERTAIN, ""

    def _locate_trojans(
        self,
        circuit_graph: CircuitGraph,
        gate_scores: dict[str, float],
        algo_result: AlgorithmicResult | None = None,
    ) -> list[TrojanLocation]:
        locations: list[TrojanLocation] = []
        module_lookup = self._build_module_lookup()
        gate_lookup = self._build_gate_lookup()

        for node_idx, gate_name in circuit_graph.node_to_gate.items():
            score = gate_scores.get(gate_name, 0.0)
            if score < self._suspicion_threshold:
                continue

            gate_info = gate_lookup.get(gate_name, {})
            module_name = gate_info.get("module_name", "unknown")
            gate_type = gate_info.get("gate_type", "unknown")

            # Primary source: Yosys `src` attribute resolved by the builder.
            # This maps cells to the exact line in the user's source file
            # (including cells that Yosys renamed during synthesis).
            src_entry = circuit_graph.node_src_map.get(node_idx)
            if src_entry is not None:
                source_file, line_number = src_entry
            else:
                # Secondary: parsed-module lookup by gate instance name.
                source_file = None
                line_number = gate_info.get("line_number")
                module_info = module_lookup.get(module_name)
                if module_info:
                    source_path = module_info.get("source_path")
                    if source_path:
                        source_file = source_path
                        # Fall back to regex search if parser didn't capture line number
                        if line_number is None:
                            result = self._find_gate_line(Path(source_path), gate_name)
                            if result is not None:
                                line_number, found_type = result
                                if gate_type == "unknown":
                                    gate_type = found_type

                # Tertiary: regex scan across all parsed source files.
                if source_file is None and self._parsed_modules:
                    for mod in self._parsed_modules:
                        if mod.source_path:
                            result = self._find_gate_line(Path(mod.source_path), gate_name)
                            if result is not None:
                                line_number, found_type = result
                                source_file = mod.source_path
                                if module_name == "unknown":
                                    module_name = mod.name
                                if gate_type == "unknown":
                                    gate_type = found_type
                                break

            # Validate: strip anything that isn't a real user HDL file on disk.
            # This catches pyslang `.cc` leaks, techlib cells, and temp-dir
            # copies that Yosys may emit in `src` attributes.
            source_file = _validate_source_path(source_file, self._parsed_modules)
            if source_file is None:
                line_number = None

            if self._matches_trojan_pattern(gate_name):
                detection_method = "name_pattern"
            else:
                detection_method = "gnn_ensemble"

            # Enrich with algorithmic metadata
            scoap_cc1_val: float | None = None
            scoap_co_val:  float | None = None
            coi_out_names: list[str] = []
            algo_score_val: float | None = None

            if algo_result is not None:
                ainfo = algo_result.node_info.get(gate_name)
                if ainfo is not None:
                    scoap_cc1_val  = ainfo.scoap_cc1
                    scoap_co_val   = ainfo.scoap_co
                    coi_out_names  = ainfo.coi_outputs
                    algo_score_val = ainfo.algo_suspicion_score
                    if detection_method == "gnn_ensemble":
                        detection_method = "gnn+algorithmic"
                    elif detection_method == "name_pattern" and ainfo.algo_suspicion_score > 0.5:
                        detection_method = "name_pattern+algorithmic"

            locations.append(
                TrojanLocation(
                    node_index=node_idx,
                    gate_name=gate_name,
                    gate_type=gate_type,
                    module_name=module_name,
                    source_file=source_file,
                    line_number=line_number,
                    suspicion_score=score,
                    detection_method=detection_method,
                    scoap_cc1=scoap_cc1_val,
                    scoap_co=scoap_co_val,
                    coi_outputs=coi_out_names,
                    algo_suspicion_score=algo_score_val,
                )
            )

        locations.sort(key=lambda x: x.suspicion_score, reverse=True)
        return locations

    def _build_module_lookup(self) -> dict[str, dict]:
        if not self._parsed_modules:
            return {}
        return {
            m.name: {"source_path": m.source_path, "gate_count": len(m.gates)}
            for m in self._parsed_modules
        }

    def _build_gate_lookup(self) -> dict[str, dict]:
        if not self._parsed_modules:
            return {}
        
        lookup: dict[str, dict] = {}
        for module in self._parsed_modules:
            for gate in module.gates:
                lookup[gate.instance_name] = {
                    "module_name": module.name,
                    "gate_type": gate.canonical_type or gate.gate_type,
                    "line_number": gate.line_number,
                }
            # Also index ports and wires so Yosys-synthesized names resolve
            for port in module.ports:
                if port.name not in lookup:
                    direction = port.direction.value if hasattr(port.direction, "value") else str(port.direction)
                    lookup[port.name] = {
                        "module_name": module.name,
                        "gate_type": direction,
                        "line_number": port.line_number,
                    }
        
            for wire in module.wires:
                if wire.name not in lookup:
                    lookup[wire.name] = {
                        "module_name": module.name,
                        "gate_type": "wire",
                        "line_number": wire.line_number,
                    }
        
        return lookup

    def _find_gate_line(
        self, source_file: Path, gate_name: str,
    ) -> tuple[int, str] | None:
        """Search source file for gate_name, return (line_number, hdl_type) or None."""
        if not source_file.exists():
            return None
        
        escaped = re.escape(gate_name)
        try:
            with open(source_file, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    # Input/output/inout declaration
                    m = re.search(rf'\b(input|output|inout)\b.*\b{escaped}\b', line)
                    if m:
                        return line_num, m.group(1)
                    # Wire/reg declaration
                    m = re.search(rf'\b(wire|reg)\b.*\b{escaped}\b', line)
                    if m:
                        return line_num, m.group(1)
                    # Gate instantiation: gate_name(
                    if re.search(rf'\b{escaped}\s*\(', line):
                        return line_num, "gate"
                    # Port connection: .port(gate_name)
                    if re.search(rf'\.\w+\s*\(\s*{escaped}\s*\)', line):
                        return line_num, "net"
                    # Assignment: assign gate_name = or gate_name <=
                    if re.search(rf'\b{escaped}\s*(<?\s*=)', line):
                        return line_num, "assign"
        except Exception as e:
            logger.debug(f"Could not search {source_file}: {e}")
        
        return None

    @staticmethod
    def _matches_trojan_pattern(name: str) -> bool:
        patterns = [
            r"(?i)trojan", r"(?i)^tj_", r"(?i)_tj$",
            r"(?i)trigger", r"(?i)payload", r"(?i)^mal_",
            r"(?i)^ht_", r"(?i)backdoor", r"(?i)leak",
        ]
        
        return any(re.search(p, name) for p in patterns)

    # ------------------------------------------------------------------
    # False positive detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_likely_false_positive(
        total_nodes: int,
        suspicious_count: int,
        trojan_percentage: float,
        trojan_locations: list[TrojanLocation],
        gate_scores: dict[str, float],
        model_agreement: float,
    ) -> tuple[bool, str]:
        """Detect likely false positives using multiple structural signals.

        Real hardware trojans are a small fraction of the circuit. When the
        localization flags nearly everything, it usually means the model was
        confused by an unusual but benign topology rather than finding a
        genuine trojan.

        Returns:
            (should_downgrade, reason) — True + explanation if likely FP.
        """
        # ── Signal 1: Suspicion score variance ──
        # Real trojans produce a bimodal distribution (high scores for trojan
        # gates, low for the rest).  False positives produce uniformly similar
        # scores because the model cannot differentiate trojan from benign gates.
        scores = list(gate_scores.values())
        if len(scores) >= 2:
            mean_s = sum(scores) / len(scores)
            variance = sum((s - mean_s) ** 2 for s in scores) / len(scores)
        else:
            variance = 0.0

        # ── Signal 2: Graph size ──
        # Larger circuits are far less likely to be 100% trojan.
        size_factor = math.log2(max(total_nodes, 2))

        # ── Signal 3: Score concentration near threshold ──
        threshold = SUSPICION_THRESHOLD
        margin = 0.10  # scores within [threshold, threshold + margin] are "weak"
        weak_count = sum(
            1 for loc in trojan_locations
            if loc.suspicion_score < threshold + margin
        )
        weak_ratio = weak_count / max(suspicious_count, 1)

        # ── Combined decision ──
        # For small circuits (< 8 nodes), don't downgrade — trojan-only
        # modules can legitimately be entirely malicious.
        if total_nodes < 8:
            return False, ""

        # More than half the nodes flagged on a non-tiny circuit is almost
        # always a false positive — real trojans are a small fraction.
        if trojan_percentage >= 50.0 and total_nodes >= 20:
            variance_threshold = 0.005 * size_factor
            if variance < variance_threshold:
                return True, (
                    f"{trojan_percentage:.1f}% of {total_nodes} nodes flagged with low "
                    f"score variance ({variance:.4f} < {variance_threshold:.4f}) — "
                    f"model cannot differentiate trojan from benign gates."
                )

        # High flagged % + weak scores → noise, not signal
        if trojan_percentage >= 40.0 and weak_ratio >= 0.80 and total_nodes >= 15:
            return True, (
                f"{trojan_percentage:.1f}% of {total_nodes} nodes flagged, but "
                f"{weak_ratio:.0%} of suspicious scores are within {margin} of the "
                f"threshold — localization confidence too low."
            )

        return False, ""

    # ------------------------------------------------------------------
    # History recording
    # ------------------------------------------------------------------

    def _record_history(self, result: ClassificationResult, duration: float) -> None:
        self._history.record(STAGE, "verdict", result.verdict.value)
        self._history.record(STAGE, "confidence", result.confidence)
        self._history.record(STAGE, "trojan_probability", result.trojan_probability)
        self._history.record(STAGE, "model_version", result.model_version)
        self._history.record(STAGE, "architecture", result.architecture)
        self._history.record(STAGE, "inference_duration", duration)
        self._history.record(STAGE, "device", str(self._device))
        self._history.record(STAGE, "trojan_node_percentage", result.trojan_node_percentage)
        self._history.record(STAGE, "high_risk", result.high_risk)
        self._history.record(STAGE, "trojan_modules", result.trojan_modules)

        # Ensemble-specific history
        self._history.record(STAGE, "ensemble_used", True)
        self._history.record(STAGE, "ensemble_models_run", result.ensemble_models_run)
        self._history.record(STAGE, "per_model_results", result.per_model_results)
        self._history.record(STAGE, "model_agreement", result.model_agreement)
        if result.algorithmic_result is not None:
            ar = result.algorithmic_result
            self._history.record(STAGE, "algo_graph_score", ar.graph_algo_score)
            self._history.record(STAGE, "algo_zero_coi_count", len(ar.zero_coi_output_nodes))
            self._history.record(STAGE, "algo_isolated_count", len(ar.isolated_nodes))
            self._history.record(STAGE, "algo_high_cc1_count", len(ar.high_cc1_nodes))
            self._history.record(STAGE, "algo_high_co_count", len(ar.high_co_nodes))

        if result.verdict == TrojanVerdict.INFECTED or result.high_risk:
            top_locations = result.get_top_suspicious(20)
            self._history.record(
                STAGE,
                "top_suspicious_gates",
                [
                    {
                        "gate": loc.gate_name,
                        "score": loc.suspicion_score,
                        "module": loc.module_name,
                        "file": loc.source_file,
                        "line": loc.line_number,
                        "type": loc.gate_type,
                    }
                    for loc in top_locations
                ],
            )
            by_module = result.get_locations_by_module()
            self._history.record(
                STAGE,
                "trojan_locations_by_module",
                {
                    module: [
                        {
                            "gate": loc.gate_name,
                            "type": loc.gate_type,
                            "file": loc.source_file,
                            "line": loc.line_number,
                            "score": loc.suspicion_score,
                        }
                        for loc in locs
                    ]
                    for module, locs in by_module.items()
                },
            )

        self._history.info(
            STAGE,
            f"[ensemble] Final: {result.verdict.value} "
            f"(confidence={result.confidence:.4f}, "
            f"p(trojan)={result.trojan_probability:.4f}, "
            f"trojan_nodes={result.trojan_node_percentage:.2f}%, "
            f"models={result.ensemble_models_run}, "
            f"agreement={result.model_agreement:.2f})",
        )

        if result.high_risk:
            self._history.warning(
                STAGE,
                f"HIGH RISK: {result.trojan_node_percentage:.2f}% of nodes identified as trojan. "
                f"Affected modules: {', '.join(result.trojan_modules)}",
            )
