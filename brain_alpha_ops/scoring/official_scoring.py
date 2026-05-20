"""科学评分系统 — BRAIN API 真实模拟、零偏差 Pass/Fail 门禁、多维评分归因。

OfficialScoringSystem — wraps the existing scoring pipeline with:
  1. True-to-API simulation output that matches BRAIN official API format
  2. Zero-deviation Pass/Fail configurable gating with threshold traceability
  3. Multi-dimensional attribution architecture (explainable, calibratable, evolvable)
  4. Score history tracking for convergence analysis

Usage:
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem
    oss = OfficialScoringSystem(ops_config)
    result = oss.evaluate(candidate)
    print(result.attribution_report())
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from brain_alpha_ops.config import OpsConfig, QualityThresholds, ScoringConfig
from brain_alpha_ops.jsonl import read_jsonl_records
from brain_alpha_ops.models import Candidate

from brain_alpha_ops.research.scoring import (
    build_scorecard,
    calculate_fitness,
    empirical_score,
    evaluate_quality_gate,
    prior_score,
    submission_checklist,
)
from brain_alpha_ops.scoring.attribution import (
    AttributionNode,
    build_attribution_tree,
    dim_explanation,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class GateResult:
    """Pass/Fail gate result with full traceability."""
    gate_name: str
    passed: bool
    check_items: List[Dict[str, Any]] = field(default_factory=list)
    failed_items: List[str] = field(default_factory=list)
    threshold_source: str = "BRAIN_Official"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "check_items": self.check_items,
            "failed_items": self.failed_items,
            "threshold_source": self.threshold_source,
            "notes": self.notes,
        }


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
            "attribution_tree": self.attribution_tree.to_dict() if self.attribution_tree else None,
            "top_failures": self.top_failures,
            "improvement_hints": self.improvement_hints,
            "simulated_api_output": self.simulated_api_output,
            "api_output_deviation": self.api_output_deviation,
            "deviation_details": self.deviation_details,
            "threshold_version": self.threshold_version,
            "scoring_schema": self.scoring_schema,
            "config_hash": self.config_hash,
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

    def __init__(self, ops_config: Optional[OpsConfig] = None, *, gate_config: "GateConfig | None" = None):
        self.ops_config = ops_config or OpsConfig()
        self.thresholds = self.ops_config.thresholds
        self.scoring = self.ops_config.scoring
        self.gate_config = gate_config
        if gate_config is not None:
            self.thresholds = gate_config.thresholds
        self._score_history: Dict[str, List[Dict[str, Any]]] = {}

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
        )

        # 2. Evaluate quality gate
        gate = evaluate_quality_gate(candidate, self.thresholds)

        # 3. Build hard/soft gate results
        hard_gates = self._build_hard_gates(candidate, scorecard)
        soft_gates = self._build_soft_gates(candidate, scorecard)
        if self.gate_config is not None and candidate.official_metrics:
            configured_gate = self.gate_config.evaluate(candidate.official_metrics)
            configured_gate.gate_name = "CONFIGURED_GATE"
            soft_gates.append(configured_gate)

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
            attribution_tree=attribution,
            top_failures=top_failures,
            improvement_hints=hints,
            simulated_api_output=api_sim,
            api_output_deviation=api_dev,
            deviation_details=dev_details,
            config_hash=self._config_hash(),
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
            if row.get("is_hard_gate") and row.get("points", 0) > 0
        ]
        hard_failed = [row for row in hard_gate_items if not row["passed"]]
        hard_passed = [row for row in hard_gate_items if row["passed"]]

        gate_items = []
        for row in hard_gate_items:
            gate_items.append({
                "name": row["name"],
                "passed": row["passed"],
                "actual": row["actual"],
                "target": row["target"],
                "direction": row["direction"],
                "source": "BRAIN_Official_Alpha_Check",
            })

        gates.append(GateResult(
            gate_name="BRAIN_HARD_GATES",
            passed=not bool(hard_failed),
            check_items=gate_items,
            failed_items=[f"{r['name']} (actual={r['actual']} {r['direction']} {r['target']})" for r in hard_failed],
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
            if not row.get("is_hard_gate") or row.get("points", 0) == 0
        ]

        if soft_items:
            soft_failed = [row for row in soft_items if not row["passed"]]
            gate_items = [
                {
                    "name": row["name"],
                    "passed": row["passed"],
                    "actual": row["actual"],
                    "target": row["target"],
                    "direction": row["direction"],
                    "source": row.get("source", "Advisor_Standard"),
                }
                for row in soft_items
            ]
            gates.append(GateResult(
                gate_name="QUALITY_TARGETS",
                passed=len(soft_failed) <= 2,  # Allow up to 2 warnings
                check_items=gate_items,
                failed_items=[f"{r['name']} (actual={r['actual']} {r['direction']} {r['target']})" for r in soft_failed],
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
        """Simulate what the BRAIN API would return for this alpha.

        Returns (simulated_output, deviation, deviation_details).
        deviation = 0.0 means perfect match with API format.
        """
        deviations = []

        # Construct a BRAIN-alpha-check-like response from the same empirical
        # items used by the gate. Official pass_fail, when present, remains the
        # source of truth; local reconstruction is compared against it.
        empirical = scorecard.get("empirical", {})
        metrics = candidate.official_metrics or {}
        local_hard_gate_passed = not bool(empirical.get("hard_gate_failed", False))
        official_pass = str(metrics.get("pass_fail") or "").upper()
        reconstructed_status = "PASS" if local_hard_gate_passed and metrics else "FAIL"
        api_status = official_pass if official_pass in {"PASS", "FAIL"} else reconstructed_status

        check_items = {}
        for row in empirical.get("items", []):
            if not row.get("is_hard_gate"):
                continue
            check_items[row["name"]] = {
                "value": row.get("actual"),
                "threshold": row.get("target"),
                "direction": row.get("direction"),
                "passed": bool(row.get("passed")),
                "source": row.get("source", "BRAIN_Official_Alpha_Check"),
            }

        simulated = {
            "alpha_id": candidate.official_alpha_id or candidate.alpha_id,
            "expression": candidate.expression,
            "status": api_status,
            "checks": check_items,
            "score": {
                "total": scorecard["total_score"],
                "prior": scorecard["prior"]["score"],
                "empirical": scorecard["empirical"]["score"],
                "checklist": scorecard["submission_checklist"]["score"],
            },
            "gate": {
                "hard_gate_passed": api_status == "PASS",
                "reconstructed_hard_gate_passed": local_hard_gate_passed,
                "soft_gate_warnings": [],
                "submission_ready": api_status == "PASS",
                "local_submission_ready": scorecard.get("decision_band") == "submit_candidate",
            },
            "meta": {
                "simulated": True,
                "scoring_schema": "scorecard-v2.3",
                "threshold_version": "CANONICAL_v2",
                "official_pass_fail_source": "candidate.official_metrics.pass_fail" if official_pass else "reconstructed_hard_gates",
                "thresholds_used": {
                    "min_sharpe": self.thresholds.min_sharpe,
                    "min_sharpe_delay0": self.thresholds.min_sharpe_delay0,
                    "min_fitness": self.thresholds.min_fitness,
                    "min_fitness_delay0": self.thresholds.min_fitness_delay0,
                    "min_turnover": self.thresholds.min_turnover,
                    "platform_max_turnover": self.thresholds.platform_max_turnover,
                    "max_self_correlation": self.thresholds.max_self_correlation,
                    "max_weight_concentration": self.thresholds.max_weight_concentration,
                    "sub_universe_sharpe_min_ratio": self.thresholds.sub_universe_sharpe_min_ratio,
                },
            },
        }

        # Compare with official metrics if available
        deviation = 0.0
        if candidate.official_metrics:
            if official_pass and official_pass != reconstructed_status:
                deviation = 1.0
                deviations.append(
                    f"pass_fail mismatch: official={official_pass}, reconstructed={reconstructed_status}"
                )

            # Check specific metric deviations
            for check_name in ["sharpe", "fitness"]:
                if check_name in candidate.official_metrics:
                    official_val = candidate.official_metrics[check_name]
                    sim_val = simulated["checks"].get(check_name, {}).get("value")
                    if abs((official_val or 0) - (sim_val or 0)) > 0.001:
                        deviations.append(
                            f"{check_name} mismatch: official={official_val}, simulated={sim_val}"
                        )
                        deviation = max(deviation, 0.5)

        return simulated, deviation, deviations

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
        self._score_history[alpha_id].append({
            "timestamp": result.evaluated_at,
            "total_score": result.total_score,
            "decision_band": result.decision_band,
            "passed_gate": result.passed_gate,
            "api_deviation": result.api_output_deviation,
        })

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
        import hashlib
        data = json.dumps({
            "thresholds": {
                k: getattr(self.thresholds, k)
                for k in ["min_sharpe", "min_fitness", "platform_max_turnover",
                          "max_self_correlation", "max_weight_concentration"]
            },
            "scoring": self.scoring.get_layer_weights(),
        }, sort_keys=True)
        return hashlib.md5(data.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════
# Configurable Gate Builder
# ═══════════════════════════════════════════════════════════════════════

class GateConfig:
    """Configurable Pass/Fail gate with zero-deviation thresholds."""

    def __init__(self, thresholds: QualityThresholds):
        self.thresholds = thresholds
        self._gates: List[Dict[str, Any]] = []

    @classmethod
    def from_thresholds(cls, thresholds: QualityThresholds) -> "GateConfig":
        return cls(thresholds)

    def add_hard_gate(self, name: str, check_fn, description: str = "") -> "GateConfig":
        self._gates.append({
            "name": name,
            "type": "HARD",
            "check": check_fn,
            "description": description,
            "source": "BRAIN_Official",
        })
        return self

    def add_soft_gate(self, name: str, check_fn, description: str = "") -> "GateConfig":
        self._gates.append({
            "name": name,
            "type": "SOFT",
            "check": check_fn,
            "description": description,
            "source": "Advisor_Standard",
        })
        return self

    def evaluate(self, metrics: dict) -> GateResult:
        passed_all = True
        items = []
        failed = []
        for gate in self._gates:
            passed = gate["check"](metrics, self.thresholds)
            items.append({
                "name": gate["name"],
                "type": gate["type"],
                "passed": passed,
                "source": gate["source"],
                "description": gate["description"],
            })
            if not passed:
                failed.append(gate["name"])
                if gate["type"] == "HARD":
                    passed_all = False

        return GateResult(
            gate_name="CustomGating",
            passed=passed_all,
            check_items=items,
            failed_items=failed,
            threshold_source="Configurable",
        )


# ═══════════════════════════════════════════════════════════════════════
# Score History Database (simple JSONL-based)
# ═══════════════════════════════════════════════════════════════════════

class ScoreHistoryDB:
    """Lightweight score history store for convergence analysis."""

    DEFAULT_HISTORY_LIMIT = 5000

    def __init__(self, path: str = "data/score_history.jsonl"):
        target = Path(path)
        self._path = target if target.suffix.lower() == ".jsonl" else target / "score_history.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, result: ScoringResult) -> None:
        record = {
            "timestamp": result.evaluated_at,
            "alpha_id": result.alpha_id,
            "total_score": result.total_score,
            "decision_band": result.decision_band,
            "passed_gate": result.passed_gate,
            "api_deviation": result.api_output_deviation,
            "prior": result.prior.get("score"),
            "empirical": result.empirical.get("score"),
            "checklist": result.checklist.get("score"),
            "config_hash": result.config_hash,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_all(self, *, limit: int | None = None) -> List[Dict[str, Any]]:
        return read_jsonl_records(self._path, limit=limit)

    def convergence_stats(self, *, limit: int = DEFAULT_HISTORY_LIMIT) -> Dict[str, Any]:
        """Compute convergence statistics from score history."""
        records = self.load_all(limit=limit)
        if len(records) < 3:
            return {"status": "insufficient_data", "count": len(records)}

        scores = [r["total_score"] for r in records]
        recent = scores[-10:] if len(scores) > 10 else scores

        return {
            "status": "ready",
            "total_evaluations": len(records),
            "history_limit": limit,
            "avg_score": round(sum(scores) / len(scores), 2),
            "recent_avg": round(sum(recent) / len(recent), 2),
            "std_dev": round(
                (sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores)) ** 0.5, 2
            ),
            "trend": "improving" if recent[-1] > scores[0] + 3 else "declining" if recent[-1] < scores[0] - 3 else "stable",
            "pass_rate": round(
                sum(1 for r in records if r["passed_gate"]) / len(records), 3
            ),
            "api_zero_deviation_rate": round(
                sum(1 for r in records if r["api_deviation"] == 0.0) / len(records), 3
            ),
        }
