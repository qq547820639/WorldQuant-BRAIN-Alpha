"""OfficialScoringSystem internals: constants and gate/hints/history mixins.

Consolidates the former ``_constants`` / ``_gates`` / ``_hints`` /
``_history`` modules into a single file. Pure physical merge; no logic changes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from brain_alpha_ops.scoring.gates import GateResult


# --------------------------------------------------------------------------- #
# Former _constants.py
# --------------------------------------------------------------------------- #
SCORING_VERSION = "scoring-v2.4"

_MAX_SCORE_HISTORY_PER_ALPHA = 100
_MAX_SCORE_HISTORY_TOTAL_ENTRIES = 10_000

# Named thresholds extracted from hardcoded values
_SOFT_GATE_TOLERANCE = 2  # max allowed soft-gate failures (line ~404)
_TREND_DELTA_IMPROVING = 5  # score delta for "improving" trend
_TREND_DELTA_DECLINING = -5  # score delta for "declining" trend


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


# --------------------------------------------------------------------------- #
# Former _gates.py
# --------------------------------------------------------------------------- #
class _GatesMixin:
    """Gate construction methods extracted from OfficialScoringSystem."""

    def _build_hard_gates(self, candidate, scorecard: dict) -> List[GateResult]:
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

    def _build_soft_gates(self, candidate, scorecard: dict) -> List[GateResult]:
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
                passed=len(soft_failed) <= _SOFT_GATE_TOLERANCE,
                check_items=gate_items,
                failed_items=[_format_gate_failure(r) for r in soft_failed],
                threshold_source="Advisor_Standard",
                notes=["These are quality targets, not BRAIN hard gates"],
            ))

        # Gate: Submission Checklist
        checklist = scorecard.get("submission_checklist", {})
        checklist_items = checklist.get("items", [])
        if checklist_items:
            failed = [r for r in checklist_items if not r.get("passed", True)]
            gates.append(GateResult(
                gate_name="SUBMISSION_CHECKLIST",
                passed=not failed,
                check_items=[
                    {"name": r["name"], "passed": r.get("passed", True), "meaning": r.get("meaning", "")}
                    for r in checklist_items
                ],
                failed_items=[f"{r['name']}: {r.get('meaning', '')}" for r in failed],
                threshold_source="Pipeline_Policy",
            ))

        return gates


# --------------------------------------------------------------------------- #
# Former _hints.py
# --------------------------------------------------------------------------- #
class _HintsMixin:
    """Improvement hints and failure collection methods extracted from OfficialScoringSystem."""

    def _generate_improvement_hints(self, candidate, scorecard: dict, gate: dict) -> List[str]:
        """Generate actionable improvement suggestions based on failures."""
        hints = []

        empirical = scorecard.get("empirical", {})
        prior = scorecard.get("prior", {})

        # Empirical failures
        for item in empirical.get("items", []):
            if not item.get("passed", True):
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
            if not item.get("passed", True):
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

    def _collect_failures(self, scorecard: dict, gate: dict) -> List[Dict[str, str]]:
        """Collect and rank all failures for reporting."""
        failures = []

        empirical = scorecard.get("empirical", {})
        for item in empirical.get("items", []):
            if not item.get("passed", True):
                severity = "HARD" if item.get("is_hard_gate") else "SOFT"
                failures.append({
                    "item": item["name"],
                    "severity": severity,
                    "reason": f"actual={item['actual']} {item['direction']} {item['target']}",
                    "source": "empirical_score",
                })

        checklist = scorecard.get("submission_checklist", {})
        for item in checklist.get("items", []):
            if not item.get("passed", True):
                failures.append({
                    "item": item["name"],
                    "severity": "SOFT",
                    "reason": item.get("meaning", ""),
                    "source": "submission_checklist",
                })

        # Sort: HARD first
        failures.sort(key=lambda f: (0 if f["severity"] == "HARD" else 1, f["item"]))
        return failures


# --------------------------------------------------------------------------- #
# Former _history.py
# --------------------------------------------------------------------------- #
logger = logging.getLogger("brain_alpha_ops.scoring.official_scoring")


class _HistoryMixin:
    """History tracking methods extracted from OfficialScoringSystem."""

    def _record_history(self, alpha_id: str, result) -> None:
        with self._lock:
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
                logger.warning("failed to persist score history", exc_info=True)

    def _write_audit_trail(self, result) -> None:
        """Write scoring result to audit trail for traceability."""
        try:
            from brain_alpha_ops.audit_trail import write_scoring_audit
            write_scoring_audit(
                result,
                audit_dir=self._audit_trail_dir or "data/audit_trail",
                scoring_version=SCORING_VERSION,
            )
        except Exception:
            logger.warning("failed to write audit trail", exc_info=True)

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
        with self._lock:
            history = list(self._score_history.get(alpha_id, []))
        if len(history) < 2:
            return None
        first = history[0]["total_score"]
        last = history[-1]["total_score"]
        delta = last - first
        if delta > _TREND_DELTA_IMPROVING:
            return "improving"
        if delta < _TREND_DELTA_DECLINING:
            return "declining"
        return "stable"
