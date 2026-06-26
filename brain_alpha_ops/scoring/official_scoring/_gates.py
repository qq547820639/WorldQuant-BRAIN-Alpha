"""Gate construction mixin for OfficialScoringSystem."""
from __future__ import annotations

from typing import List

from brain_alpha_ops.scoring.gates import GateResult
from brain_alpha_ops.scoring.official_scoring._constants import (
    _SOFT_GATE_TOLERANCE,
    _format_gate_failure,
    _gate_item_value,
)


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
