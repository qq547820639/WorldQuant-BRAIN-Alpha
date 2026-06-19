"""科学评分系统 — BRAIN API 真实模拟、零偏差 Pass/Fail 门禁、多维评分归因。

OfficialScoringSystem — wraps the existing scoring pipeline with:
  1. True-to-API simulation output that matches BRAIN official API format
  2. Zero-deviation Pass/Fail configurable gating with threshold traceability
  3. Multi-dimensional attribution architecture (explainable, calibratable, evolvable)
  4. Score history tracking for convergence analysis

── Module responsibility boundary (A-05, documented 2026-06-18) ──

  ``brain_alpha_ops.research.scoring``  (pure functions)
    • ``build_scorecard()``, ``prior_score()``, ``empirical_score()``,
      ``submission_checklist()``, ``evaluate_quality_gate()``,
      ``decision_band()``, ``calculate_fitness()``, ``item()``, ``check()``
    • Stateless by design — takes Candidate + thresholds, returns dict.
    • No BRAIN API calls, no persistence, no history tracking.

  ``brain_alpha_ops.scoring.official_scoring``  (orchestration layer)
    • ``OfficialScoringSystem.evaluate()`` — 7-step pipeline:
      scorecard → gate → hard/soft gate results → release gate →
      attribution tree → API simulation → improvement hints → history
    • Owns ``ScoringResult`` dataclass — the canonical output structure.
    • Delegates pure computations to ``research.scoring``.
    • Adds persistence, API output simulation, gate aggregation, and
      confidence estimation on top of the pure scoring functions.

  Rule: New scoring logic should be added as a pure function in
  ``research.scoring``; orchestration/aggregation goes in this module.
  Do NOT add BRAIN API calls or state to ``research.scoring``.
  Do NOT add pure scoring computations directly to ``OfficialScoringSystem``.

Usage:
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem
    oss = OfficialScoringSystem(ops_config)
    result = oss.evaluate(candidate)
    print(result.attribution_report())
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
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
    OFFICIAL_HARD_GATE_NAMES,
    GateConfig,
    GateResult,
)
from brain_alpha_ops.scoring.history import ScoreHistoryDB

_PersistedScoreHistoryDB = ScoreHistoryDB
from brain_alpha_ops.scoring.release_score_gate import (
    evaluate_release_score,
)
from brain_alpha_ops.scoring.scoring_comparison import simulate_brain_api_output
from brain_alpha_ops.scoring.visualization import summarize_score_attribution

logger = logging.getLogger(__name__)

_MAX_SCORE_HISTORY_PER_ALPHA = 100
_MAX_SCORE_HISTORY_TOTAL_ENTRIES = 10_000

def _gate_item_value(row: dict, key: str, default: str = "-") -> str:
    value = row.get(key, default)
    return str(value if value not in (None, "") else default)

def _format_gate_failure(row: dict) -> str:
    return (
        f"{_gate_item_value(row, 'name')} "
        f"(actual={row.get('actual', '-')} "
        f"{_gate_item_value(row, 'direction')} "
        f"{row.get('target', '-')})"
    )

# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════
# Official Scoring System
# ═══════════════════════════════════════════════════════════════════════

class OfficialScoringSystem:
    """BRAIN API True-to-API scoring with zero-deviation gating.

    Design principles:
      1. All thresholds sourced exclusively from BRAIN official documentation
      2. API simulation output matches BRAIN API response format exactly
      3. Multi-dimensional attribution with explainability at every level
      4. Calibration-ready parameter injection
      5. Historical score tracking for convergence analysis
    """

    def __init__(self, ops_config: Optional[OpsConfig] = None, *, gate_config: "GateConfig | None" = None, persist_history: bool = True):
        self.ops_config = ops_config or OpsConfig()
        self.thresholds = self.ops_config.thresholds
        self.scoring = self.ops_config.scoring
        self.gate_config = gate_config
        if gate_config is not None:
            self.thresholds = gate_config.thresholds
        self._score_history: Dict[str, List[Dict[str, Any]]] = {}
        # Optional persistent history for convergence tracking across restarts
        self._persisted_history = _PersistedScoreHistoryDB() if persist_history else None

    # ── Core Evaluation ──

    def evaluate(self, candidate: Candidate | dict, params=None) -> ScoringResult:
        """Full evaluation: score → gate → attribute → simulate.

        Returns a ScoringResult with complete traceability.
        """
        if isinstance(candidate, dict):
            candidate = Candidate.from_dict(candidate)

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
            config_hash=self._config_hash(),
            score_basis=scorecard.get("score_basis", ""),
            settings_trace=scorecard.get("settings_trace", {}),
            threshold_trace=self._threshold_trace(),
            calibration=scorecard.get("calibration", {}),
        )

        # Track history
        self._record_history(candidate.alpha_id, result)

        return result

    # ── Gate Construction ──

    def _build_hard_gates(
        self, candidate: Candidate, scorecard: dict
    ) -> List[GateResult]:
        """Build hard gate results from BRAIN official Alpha Check specifications."""
        gates = []

        # Gate: BRAIN Official Hard Gates
        empirical = scorecard.get("empirical", {})
        hard_gate_items = [
            row for row in empirical.get("items", [])
            if row.get("is_hard_gate")
        ]
        hard_failed = [row for row in hard_gate_items if not bool(row.get("passed", False))]

        gate_items = []
        for row in hard_gate_items:
            gate_items.append({
                "name": _gate_item_value(row, "name"),
                "passed": bool(row.get("passed", False)),
                "actual": row.get("actual"),
                "target": row.get("target"),
                "direction": _gate_item_value(row, "direction"),
                "source": "BRAIN_Official_Alpha_Check",
            })

        gates.append(GateResult(
            gate_name="BRAIN_HARD_GATES",
            passed=not bool(hard_failed),
            check_items=gate_items,
            failed_items=[_format_gate_failure(r) for r in hard_failed],
            threshold_source="BRAIN_Official",
            notes=[f"Delay-aware thresholds: min_sharpe={self.thresholds.min_sharpe}, min_fitness={self.thresholds.min_fitness}"],
        ))

        return gates

    def _build_soft_gates(
        self, candidate: Candidate, scorecard: dict
    ) -> List[GateResult]:
        """Build soft gate results for quality targets and advisor standards."""
        gates = []

        empirical = scorecard.get("empirical", {})
        soft_items = [
            row for row in empirical.get("items", [])
            if not row.get("is_hard_gate")
        ]

        if soft_items:
            soft_failed = [row for row in soft_items if not bool(row.get("passed", False))]
            gate_items = [
                {
                    "name": _gate_item_value(row, "name"),
                    "passed": bool(row.get("passed", False)),
                    "actual": row.get("actual"),
                    "target": row.get("target"),
                    "direction": _gate_item_value(row, "direction"),
                    "source": row.get("source", "Advisor_Standard"),
                }
                for row in soft_items
            ]
            gates.append(GateResult(
                gate_name="QUALITY_TARGETS",
                passed=len(soft_failed) <= 2,  # Allow up to 2 warnings
                check_items=gate_items,
                failed_items=[_format_gate_failure(r) for r in soft_failed],
                threshold_source="Advisor_Standard",
                notes=["These are quality targets, not BRAIN hard gates"],
            ))

        # Gate: Submission Checklist
        checklist = scorecard.get("submission_checklist", {})
        checklist_items = checklist.get("items", [])
        if checklist_items:
            failed = [r for r in checklist_items if not r["passed"]]
            gates.append(GateResult(
                gate_name="SUBMISSION_CHECKLIST",
                passed=not failed,
                check_items=[
                    {"name": r["name"], "passed": r["passed"], "meaning": r.get("meaning", "")}
                    for r in checklist_items
                ],
                failed_items=[f"{r['name']}: {r.get('meaning', '')}" for r in failed],
                threshold_source="Pipeline_Policy",
            ))

        return gates

    # ── Attribution Tree ──

    def _build_attribution_tree(self, scorecard: dict) -> AttributionNode:
        """Delegate to standalone attribution module (see brain_alpha_ops.scoring.attribution)."""
        return build_attribution_tree(scorecard)

    @staticmethod
    def _dim_explanation(dim_name: str, score: float) -> str:
        """Delegate to standalone attribution module."""
        return dim_explanation(dim_name, score)

    # ── API Output Simulation (Zero Deviation) ──

    def _simulate_api_output(
        self, candidate: Candidate, scorecard: dict
    ) -> tuple:
        """Delegate BRAIN API simulation/comparison to the standalone module."""
        return simulate_brain_api_output(candidate, scorecard, self.thresholds)

    # ── Improvement Hints ──

    def _generate_improvement_hints(
        self, candidate: Candidate, scorecard: dict, gate: dict
    ) -> List[str]:
        """Generate actionable improvement suggestions based on failures."""
        hints = []

        empirical = scorecard.get("empirical", {})
        prior = scorecard.get("prior", {})

        # Empirical failures
        for item in empirical.get("items", []):
            if not item["passed"]:
                name = item["name"]
                if name == "sharpe":
                    hints.append(
                        f"Sharpe ({item['actual']}) below BRAIN threshold ({item['target']}). "
                        "Consider: shorter decay, different universe, or adding risk controls."
                    )
                elif name == "fitness":
                    hints.append(
                        f"Fitness ({item['actual']}) below threshold ({item['target']}). "
                        "Consider: reduce turnover to improve returns/turnover ratio."
                    )
                elif name == "turnover_platform":
                    hints.append(
                        f"Turnover ({item['actual']}) exceeds BRAIN max ({item['target']}). "
                        "Consider: use longer windows (ts_mean, ts_decay_linear) or slower signals."
                    )
                elif name == "turnover_quality":
                    hints.append(
                        f"Turnover ({item['actual']}) exceeds advisor quality target ({item['target']}). "
                        "Consider: add decay, use ts_decay_linear, or increase window length."
                    )
                elif name == "self_correlation":
                    hints.append(
                        f"Self-correlation ({item['actual']}) too high ({item['target']}). "
                        "Consider: change feature combination, use different operators, or check cloud overlap."
                    )
                elif name == "weight_concentration":
                    hints.append(
                        f"Weight concentration ({item['actual']}) too high ({item['target']}). "
                        "Consider: use group_neutralize with subindustry, or more diversified signals."
                    )

        # Checklist failures
        checklist = scorecard.get("submission_checklist", {})
        for item in checklist.get("items", []):
            if not item["passed"]:
                if item["name"] == "official_metrics_present":
                    hints.append("Missing official simulation results — run BRAIN API simulation first.")
                elif item["name"] == "official_pass":
                    hints.append("BRAIN official check did not pass — address hard gate failures.")
                elif item["name"] == "economic_logic":
                    hints.append("Hypothesis text too short (< 40 chars). Write a concrete economic thesis.")
                elif item["name"] == "diversity":
                    hints.append("Plain momentum template detected — add liquidity filter (adv20, vwap).")

        # Prior-based hints
        if prior.get("score", 100) < 60:
            hints.append("Low prior score. Improve: add more fields, use risk controls, diversify operators.")

        return hints[:8]  # Limit to top 8

    # ── Failure Collection ──

    def _collect_failures(
        self, scorecard: dict, gate: dict
    ) -> List[Dict[str, str]]:
        """Collect and rank all failures for reporting."""
        failures = []

        empirical = scorecard.get("empirical", {})
        for item in empirical.get("items", []):
            if not item["passed"]:
                severity = "HARD" if item.get("is_hard_gate") else "SOFT"
                failures.append({
                    "item": item["name"],
                    "severity": severity,
                    "reason": f"actual={item['actual']} {item['direction']} {item['target']}",
                    "source": "empirical_score",
                })

        checklist = scorecard.get("submission_checklist", {})
        for item in checklist.get("items", []):
            if not item["passed"]:
                failures.append({
                    "item": item["name"],
                    "severity": "SOFT",
                    "reason": item.get("meaning", ""),
                    "source": "submission_checklist",
                })

        # Sort: HARD first
        failures.sort(key=lambda f: (0 if f["severity"] == "HARD" else 1, f["item"]))
        return failures

    # ── History Tracking ──

    def _record_history(self, alpha_id: str, result: ScoringResult) -> None:
        if alpha_id not in self._score_history:
            self._score_history[alpha_id] = []
        history = self._score_history[alpha_id]
        history.append({
            "timestamp": result.evaluated_at,
            "total_score": result.total_score,
            "decision_band": result.decision_band,
            "passed_gate": result.passed_gate,
            "api_deviation": result.api_output_deviation,
        })
        if len(history) > _MAX_SCORE_HISTORY_PER_ALPHA:
            del history[:-_MAX_SCORE_HISTORY_PER_ALPHA]
        self._trim_score_history()
        # Persist to disk for convergence tracking across restarts
        if self._persisted_history is not None:
            try:
                self._persisted_history.append(result)
            except Exception:
                logger.debug("failed to persist score history", exc_info=True)

    def _trim_score_history(self) -> None:
        total_entries = sum(len(history) for history in self._score_history.values())
        while total_entries > _MAX_SCORE_HISTORY_TOTAL_ENTRIES:
            oldest_alpha: str | None = None
            oldest_timestamp = ""
            for alpha_id, history in self._score_history.items():
                if not history:
                    oldest_alpha = alpha_id
                    oldest_timestamp = ""
                    break
                timestamp = str(history[0].get("timestamp", ""))
                if oldest_alpha is None or timestamp < oldest_timestamp:
                    oldest_alpha = alpha_id
                    oldest_timestamp = timestamp
            if oldest_alpha is None:
                break
            history = self._score_history.get(oldest_alpha, [])
            if history:
                history.pop(0)
                total_entries -= 1
            if not history:
                self._score_history.pop(oldest_alpha, None)

    def get_score_trend(self, alpha_id: str) -> Optional[str]:
        """Get score trend over evaluations: improving/stable/declining."""
        history = self._score_history.get(alpha_id, [])
        if len(history) < 2:
            return None
        first = history[0]["total_score"]
        last = history[-1]["total_score"]
        delta = last - first
        if delta > 5:
            return "improving"
        if delta < -5:
            return "declining"
        return "stable"

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
