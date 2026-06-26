"""OfficialScoringSystem orchestration layer.

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
from typing import Any, Dict, List, Optional

from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS
from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import (
    build_scorecard,
    evaluate_quality_gate,
)
from brain_alpha_ops.scoring.attribution import (
    build_attribution_tree,
    dim_explanation,
)
from brain_alpha_ops.scoring.gates import (
    GateConfig,
    GateResult,
)
from brain_alpha_ops.scoring.history import ScoreHistoryDB
from brain_alpha_ops.scoring.official_scoring._constants import SCORING_VERSION
from brain_alpha_ops.scoring.official_scoring._gates import _GatesMixin
from brain_alpha_ops.scoring.official_scoring._hints import _HintsMixin
from brain_alpha_ops.scoring.official_scoring._history import _HistoryMixin
from brain_alpha_ops.scoring.official_scoring._result import ScoringResult
from brain_alpha_ops.scoring.release_score_gate import (
    evaluate_release_score,
)
from brain_alpha_ops.scoring.scoring_comparison import simulate_brain_api_output

_PersistedScoreHistoryDB = ScoreHistoryDB

logger = logging.getLogger("brain_alpha_ops.scoring.official_scoring")


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
