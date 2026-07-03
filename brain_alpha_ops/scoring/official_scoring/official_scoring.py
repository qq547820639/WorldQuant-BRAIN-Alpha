"""OfficialScoringSystem core: ScoringResult dataclass and orchestration layer.

Consolidates the former ``_result`` / ``_system`` modules into a single file.
Pure physical merge; no logic changes.

BRAIN API True-to-API scoring with zero-deviation gating.

Design principles:
  1. All thresholds sourced exclusively from BRAIN official documentation
  2. API simulation output matches BRAIN API response format exactly
  3. Multi-dimensional attribution with explainability at every level
  4. Calibration-ready parameter injection
  5. Historical score tracking for convergence analysis
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS
from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import (
    build_scorecard,
    evaluate_quality_gate,
)
from brain_alpha_ops.scoring.attribution import (
    AttributionNode,
    build_attribution_tree,
    dim_explanation,
)
from brain_alpha_ops.scoring.gates import (
    GateConfig,
    GateResult,
)
from brain_alpha_ops.scoring.history import ScoreHistoryDB
from brain_alpha_ops.scoring.official_scoring.official_scoring_mixins import (
    SCORING_VERSION,
    _GatesMixin,
    _HintsMixin,
    _HistoryMixin,
)
from brain_alpha_ops.scoring.release_score_gate import (
    evaluate_release_score,
)
from brain_alpha_ops.scoring.scoring_comparison import simulate_brain_api_output
from brain_alpha_ops.scoring.visualization import summarize_score_attribution

_PersistedScoreHistoryDB = ScoreHistoryDB

logger = logging.getLogger("brain_alpha_ops.scoring.official_scoring")


# --------------------------------------------------------------------------- #
# Former _result.py
# --------------------------------------------------------------------------- #
@dataclass
class ScoringResult:
    """Complete scoring result with full attribution."""
    alpha_id: str
    expression: str
    total_score: float
    decision_band: str
    passed_gate: bool
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Score breakdown
    prior: Dict[str, Any] = field(default_factory=dict)
    empirical: Dict[str, Any] = field(default_factory=dict)
    checklist: Dict[str, Any] = field(default_factory=dict)
    layer_weights: Dict[str, float] = field(default_factory=dict)

    # Gates
    hard_gates: List[GateResult] = field(default_factory=list)
    soft_gates: List[GateResult] = field(default_factory=list)
    release_gate: Dict[str, Any] = field(default_factory=dict)

    # Attribution
    attribution_tree: Optional[AttributionNode] = None
    top_failures: List[Dict[str, str]] = field(default_factory=list)
    improvement_hints: List[str] = field(default_factory=list)

    # API simulation
    simulated_api_output: Dict[str, Any] = field(default_factory=dict)
    api_output_deviation: float = 0.0  # 0.0 = perfect match
    deviation_details: List[str] = field(default_factory=list)

    # Traceability
    threshold_version: str = "CANONICAL_v2"
    scoring_schema: str = "scorecard-v2.3"
    scoring_version: str = ""
    config_hash: str = ""
    score_basis: str = ""
    settings_trace: Dict[str, Any] = field(default_factory=dict)
    threshold_trace: Dict[str, Any] = field(default_factory=dict)
    calibration: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "alpha_id": self.alpha_id,
            "expression": self.expression,
            "total_score": self.total_score,
            "decision_band": self.decision_band,
            "passed_gate": self.passed_gate,
            "evaluated_at": self.evaluated_at,
            "prior": self.prior,
            "empirical": self.empirical,
            "checklist": self.checklist,
            "layer_weights": self.layer_weights,
            "hard_gates": [g.to_dict() for g in self.hard_gates],
            "soft_gates": [g.to_dict() for g in self.soft_gates],
            "release_gate": self.release_gate,
            "attribution_tree": self.attribution_tree.to_dict() if self.attribution_tree else None,
            "top_failures": self.top_failures,
            "improvement_hints": self.improvement_hints,
            "simulated_api_output": self.simulated_api_output,
            "api_output_deviation": self.api_output_deviation,
            "deviation_details": self.deviation_details,
            "threshold_version": self.threshold_version,
            "scoring_schema": self.scoring_schema,
            "scoring_version": self.scoring_version,
            "config_hash": self.config_hash,
            "score_basis": self.score_basis,
            "settings_trace": self.settings_trace,
            "threshold_trace": self.threshold_trace,
            "calibration": self.calibration,
            "attribution_summary": summarize_score_attribution(
                {
                    "total_score": self.total_score,
                    "decision_band": self.decision_band,
                    "attribution_tree": self.attribution_tree.to_dict() if self.attribution_tree else None,
                    "top_failures": self.top_failures,
                    "improvement_hints": self.improvement_hints,
                }
            ),
        }

    def attribution_report(self) -> str:
        """Generate human-readable attribution report."""
        lines = [
            "=" * 64,
            f"  Scoring Attribution Report — {self.alpha_id}",
            "=" * 64,
            f"  Total Score    : {self.total_score:.2f}  ({self.decision_band})",
            f"  Gate Result    : {'PASS' if self.passed_gate else 'FAIL'}",
            f"  API Deviation  : {self.api_output_deviation:.4f}",
            "",
        ]

        if self.attribution_tree:
            lines.append("  Score Attribution:")
            self._render_tree(lines, self.attribution_tree, depth=1)

        if self.top_failures:
            lines.append("")
            lines.append("  Top Failures:")
            for f in self.top_failures[:5]:
                lines.append(f"    - [{f['severity']}] {f['item']}: {f['reason']}")

        if self.improvement_hints:
            lines.append("")
            lines.append("  Improvement Hints:")
            for hint in self.improvement_hints[:5]:
                lines.append(f"    → {hint}")

        if self.deviation_details:
            lines.append("")
            lines.append("  API Deviation Notes:")
            for d in self.deviation_details[:3]:
                lines.append(f"    ⚠ {d}")

        lines.append("")
        lines.append("=" * 64)
        return "\n".join(lines)

    @staticmethod
    def _render_tree(lines: List[str], node: AttributionNode, depth: int) -> None:
        indent = "    " * depth
        trend = f" [{node.historical_trend}]" if node.historical_trend else ""
        lines.append(
            f"{indent}{node.name:.<30} {node.score:>6.1f} × {node.weight:.2f} = {node.contribution:>7.2f}{trend}"
        )
        if node.explanation:
            lines.append(f"{indent}  ↳ {node.explanation}")
        for child in node.children:
            ScoringResult._render_tree(lines, child, depth + 1)


# --------------------------------------------------------------------------- #
# Former _system.py
# --------------------------------------------------------------------------- #
class OfficialScoringSystem(_GatesMixin, _HintsMixin, _HistoryMixin):
    """BRAIN API True-to-API scoring with zero-deviation gating.

    Design principles:
      1. All thresholds sourced exclusively from BRAIN official documentation
      2. API simulation output matches BRAIN API response format exactly
      3. Multi-dimensional attribution with explainability at every level
      4. Calibration-ready parameter injection
      5. Historical score tracking for convergence analysis
    """

    def __init__(self, ops_config: Optional[OpsConfig] = None, *, gate_config: "GateConfig | None" = None, persist_history: bool = True, audit_trail_dir: str | None = None):
        self.ops_config = ops_config or OpsConfig()
        self.thresholds = self.ops_config.thresholds
        self.scoring = self.ops_config.scoring
        self.gate_config = gate_config
        if gate_config is not None:
            self.thresholds = gate_config.thresholds
        self._score_history: Dict[str, List[Dict[str, Any]]] = {}
        # Optional persistent history for convergence tracking across restarts
        self._persisted_history = _PersistedScoreHistoryDB() if persist_history else None
        self._audit_trail_dir = audit_trail_dir
        self._lock = threading.Lock()

    # ── Core Evaluation ──

    def evaluate(self, candidate: Candidate | dict, params=None) -> ScoringResult:
        """Full evaluation: score → gate → attribute → simulate.

        Returns a ScoringResult with complete traceability.
        """
        if isinstance(candidate, dict):
            candidate = Candidate.from_dict(candidate)

        import copy
        candidate = copy.copy(candidate)

        # 1. Build scorecard
        scorecard = build_scorecard(
            candidate,
            self.thresholds,
            scoring=self.scoring,
            params=params,
            settings=self._settings_for(candidate),
        )
        candidate.scorecard = scorecard

        # 2. Evaluate quality gate
        gate = evaluate_quality_gate(candidate, self.thresholds, settings=self._settings_for(candidate))

        # 3. Build hard/soft gate results
        hard_gates = self._build_hard_gates(candidate, scorecard)
        soft_gates = self._build_soft_gates(candidate, scorecard)
        if self.gate_config is not None and candidate.official_metrics:
            configured_gate = self.gate_config.evaluate(candidate.official_metrics)
            object.__setattr__(configured_gate, "gate_name", "CONFIGURED_GATE")
            soft_gates.append(configured_gate)
        release_gate = (
            evaluate_release_score(candidate.official_metrics, self.thresholds, settings=self._settings_for(candidate)).to_dict()
            if candidate.official_metrics
            else {}
        )

        # 4. Build attribution tree
        attribution = self._build_attribution_tree(scorecard)

        # 5. Simulate BRAIN API output (zero deviation)
        api_sim, api_dev, dev_details = self._simulate_api_output(candidate, scorecard)

        # 6. Generate improvement hints
        hints = self._generate_improvement_hints(candidate, scorecard, gate)

        # 7. Collect top failures
        top_failures = self._collect_failures(scorecard, gate)

        result = ScoringResult(
            alpha_id=candidate.alpha_id,
            expression=candidate.expression,
            total_score=scorecard["total_score"],
            decision_band=scorecard["decision_band"],
            passed_gate=gate.get("submission_ready", False),
            prior=scorecard.get("prior", {}),
            empirical=scorecard.get("empirical", {}),
            checklist=scorecard.get("submission_checklist", {}),
            layer_weights=scorecard.get("layer_weights", {}),
            hard_gates=hard_gates,
            soft_gates=soft_gates,
            release_gate=release_gate,
            attribution_tree=attribution,
            top_failures=top_failures,
            improvement_hints=hints,
            simulated_api_output=api_sim,
            api_output_deviation=api_dev,
            deviation_details=dev_details,
            scoring_version=SCORING_VERSION,
            config_hash=self._config_hash(),
            score_basis=scorecard.get("score_basis", ""),
            settings_trace=scorecard.get("settings_trace", {}),
            threshold_trace=self._threshold_trace(),
            calibration=scorecard.get("calibration", {}),
        )

        # Track history
        self._record_history(candidate.alpha_id, result)

        # Write audit trail
        self._write_audit_trail(result)

        return result

    # ── Attribution Tree ──

    def _build_attribution_tree(self, scorecard: dict):
        """Delegate to standalone attribution module (see brain_alpha_ops.scoring.attribution)."""
        return build_attribution_tree(scorecard)

    @staticmethod
    def _dim_explanation(dim_name: str, score: float) -> str:
        """Delegate to standalone attribution module."""
        return dim_explanation(dim_name, score)

    # ── API Output Simulation (Zero Deviation) ──

    def _simulate_api_output(self, candidate, scorecard: dict) -> tuple:
        """Delegate BRAIN API simulation/comparison to the standalone module."""
        return simulate_brain_api_output(candidate, scorecard, self.thresholds)

    # ── Config Hash ──

    def _config_hash(self) -> str:
        data = json.dumps({
            "thresholds": {
                key: getattr(self.thresholds, key)
                for key in CANONICAL_THRESHOLDS
            },
            "scoring": self.scoring.get_layer_weights(),
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:12]

    def _threshold_trace(self) -> Dict[str, Any]:
        return {
            key: {
                "value": getattr(self.thresholds, key),
                "source": "BRAIN_Official",
            }
            for key in CANONICAL_THRESHOLDS
        }

    def _settings_for(self, candidate: Candidate) -> dict:
        submission = candidate.submission if isinstance(candidate.submission, dict) else {}
        stored = submission.get("settings")
        if isinstance(stored, dict) and stored:
            trace = dict(stored)
            trace.setdefault("type", str(submission.get("type") or self.ops_config.settings.type))
            return trace
        platform = self.ops_config.settings.to_platform_dict()
        trace = dict(platform["settings"])
        trace["type"] = platform["type"]
        return trace
