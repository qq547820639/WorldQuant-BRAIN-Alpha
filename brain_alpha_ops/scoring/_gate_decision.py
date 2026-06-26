"""Gate-decision service mapping gate outcomes to lifecycle transitions (D2.1).

``GateDecisionService.decide()`` inspects gate results (release-score gate,
configured hard gates) and the anti-overfit recommendation to decide:

  * continue optimization (→ ``needs_optimization``)
  * discard archive        (→ ``archived``)
  * enter official queue   (→ ``queued_for_simulation``)
  * human confirmation     (→ ``ready_for_review``)

The returned ``GateDecisionOutcome`` carries (action, reason, target_state)
plus the structured evidence so the audit trail and the frontend can replay
why the decision was made.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.candidate_lifecycle import LifecycleState
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring.gates import OFFICIAL_HARD_GATE_NAMES

logger = logging.getLogger(__name__)

# Actions exposed to the frontend / audit trail.
ACTION_QUEUE_SIMULATION = "enter_official_simulation_queue"
ACTION_CONTINUE_OPTIMIZATION = "continue_optimization"
ACTION_DISCARD_ARCHIVE = "discard_archive"
ACTION_HUMAN_CONFIRMATION = "enter_human_confirmation"

GATE_DECISION_SCHEMA_VERSION = "gate_decision.v1"

# Gate failures considered fixable via optimization (soft / recoverable).
_FIXABLE_GATE_HINTS: frozenset[str] = frozenset({
    "turnover_min", "turnover_quality", "drawdown_cap", "margin_bps",
    "is_oos_ratio", "fitness_crosscheck", "returns",
})


@dataclass
class GateDecisionOutcome:
    """Outcome of a gate decision (action, reason, target_state).

    Distinct from ``release_score_gate.GateDecision`` (which captures the
    raw release-gate pass/fail snapshot).  This dataclass captures the
    *production decision* derived from multiple gate signals.
    """

    action: str
    reason: str
    target_state: LifecycleState
    alpha_id: str = ""
    schema_version: str = GATE_DECISION_SCHEMA_VERSION
    gate_evidence: dict[str, Any] = field(default_factory=dict)
    triggered_rules: list[dict[str, Any]] = field(default_factory=list)
    next_action_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "target_state": self.target_state.value,
            "alpha_id": self.alpha_id,
            "schema_version": self.schema_version,
            "gate_evidence": self.gate_evidence,
            "triggered_rules": self.triggered_rules,
            "next_action_hint": self.next_action_hint,
        }


class GateDecisionService:
    """Map gate outcomes to production decisions and lifecycle transitions.

    Usage::

        service = GateDecisionService()
        outcome = service.decide(candidate, gate_results, anti_overfit_result)
        # outcome.action, outcome.reason, outcome.target_state
    """

    def decide(
        self,
        candidate: Candidate,
        gate_results: Any | None = None,
        anti_overfit_result: dict[str, Any] | None = None,
        *,
        release_gate: dict[str, Any] | None = None,
    ) -> GateDecisionOutcome:
        """Inspect gates and anti-overfit, return a production decision.

        Args:
            candidate: the candidate Alpha being assessed.
            gate_results: a ``GateResult`` (``scoring.gates``) or dict from
                ``evaluate_quality_gate`` / ``GateConfig.evaluate()``.
            anti_overfit_result: dict from ``AntiOverfitService.evaluate``;
                ``recommendation`` is one of pass/caution/block/insufficient_data.
            release_gate: optional dict from ``evaluate_release_score().to_dict()``.
        """
        alpha_id = str(getattr(candidate, "alpha_id", "") or "")
        gate_dict = _coerce_gate_dict(gate_results)
        release_dict = release_gate or _extract_release_gate(candidate)
        ao = anti_overfit_result or _extract_anti_overfit(candidate)

        hard_failed = _collect_hard_gate_failures(gate_dict, release_dict)
        ao_recommendation = str(ao.get("recommendation", "") or "").lower()
        ao_blocked = ao_recommendation == "block"
        ao_pass = ao_recommendation == "pass"
        has_metrics = bool(candidate.official_metrics)

        evidence = {
            "hard_gate_failed": hard_failed,
            "anti_overfit_recommendation": ao_recommendation,
            "anti_overfit_passed": bool(ao.get("passed", False)),
            "has_official_metrics": has_metrics,
            "release_status": str(release_dict.get("status", "") or ""),
            "gate_submission_ready": bool(
                gate_dict.get("submission_ready") or release_dict.get("pass_fail")
            ),
        }
        triggered = _build_triggered_rules(gate_dict, release_dict, ao)

        # 1. Ambiguous / missing data → human confirmation.
        if not has_metrics and not gate_dict and not release_dict:
            return self._outcome(
                alpha_id, ACTION_HUMAN_CONFIRMATION,
                "missing gate evidence and official metrics; needs human confirmation",
                LifecycleState.ready_for_review,
                evidence, triggered,
                "collect official simulation metrics then re-run gates",
            )
        if ao_recommendation == "insufficient_data":
            return self._outcome(
                alpha_id, ACTION_HUMAN_CONFIRMATION,
                "anti-overfit data insufficient; needs human confirmation",
                LifecycleState.ready_for_review,
                evidence, triggered,
                "provide more robustness samples or override after review",
            )

        # 2. Anti-overfit block → discard archive.
        if ao_blocked:
            return self._outcome(
                alpha_id, ACTION_DISCARD_ARCHIVE,
                f"anti-overfit block: {ao.get('reason', 'statistical robustness below threshold')}",
                LifecycleState.archived,
                evidence, triggered,
                "redesign expression or rebuild from a different family",
            )

        # 3. Hard gates fail unfixably → discard archive.
        unfixable = [g for g in hard_failed if g not in _FIXABLE_GATE_HINTS]
        if unfixable and has_metrics:
            return self._outcome(
                alpha_id, ACTION_DISCARD_ARCHIVE,
                f"hard gate failed unfixably: {', '.join(unfixable)}",
                LifecycleState.archived,
                evidence, triggered,
                "abandon variant; hard BRAIN checks cannot be optimized away",
            )

        # 4. Hard gates fail but fixable → continue optimization.
        fixable = [g for g in hard_failed if g in _FIXABLE_GATE_HINTS]
        if fixable:
            return self._outcome(
                alpha_id, ACTION_CONTINUE_OPTIMIZATION,
                f"hard gate failed but fixable: {', '.join(fixable)}",
                LifecycleState.needs_optimization,
                evidence, triggered,
                "adjust turnover / window / decay to recover the failing metric",
            )

        # 5. All hard gates pass + anti-overfit pass → official simulation queue.
        if not hard_failed and ao_pass:
            return self._outcome(
                alpha_id, ACTION_QUEUE_SIMULATION,
                "all hard gates pass and anti-overfit pass; ready for official simulation",
                LifecycleState.queued_for_simulation,
                evidence, triggered,
                "queue for official simulation; verify slot availability",
            )

        # 6. Soft warnings / caution → continue optimization.
        if ao_recommendation == "caution" or release_dict.get("status") == "WARN":
            return self._outcome(
                alpha_id, ACTION_CONTINUE_OPTIMIZATION,
                "soft warnings / anti-overfit caution; optimize before submission",
                LifecycleState.needs_optimization,
                evidence, triggered,
                "address soft warnings and re-evaluate before queueing",
            )

        # 7. Default fallback → human confirmation.
        return self._outcome(
            alpha_id, ACTION_HUMAN_CONFIRMATION,
            "gate outcome ambiguous; needs human confirmation",
            LifecycleState.ready_for_review,
            evidence, triggered,
            "review gate evidence and decide manually",
        )

    def _outcome(
        self,
        alpha_id: str,
        action: str,
        reason: str,
        target_state: LifecycleState,
        evidence: dict[str, Any],
        triggered: list[dict[str, Any]],
        next_hint: str,
    ) -> GateDecisionOutcome:
        return GateDecisionOutcome(
            action=action,
            reason=reason,
            target_state=target_state,
            alpha_id=alpha_id,
            gate_evidence=evidence,
            triggered_rules=triggered,
            next_action_hint=next_hint,
        )


# --- Helpers ----------------------------------------------------------------


def _coerce_gate_dict(gate_results: Any) -> dict[str, Any]:
    if gate_results is None:
        return {}
    if isinstance(gate_results, dict):
        return gate_results
    if hasattr(gate_results, "to_dict"):
        try:
            d = gate_results.to_dict()
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _extract_release_gate(candidate: Candidate) -> dict[str, Any]:
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    release = submission.get("official_release_gate") or submission.get("release_gate")
    return release if isinstance(release, dict) else {}


def _extract_anti_overfit(candidate: Candidate) -> dict[str, Any]:
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    ao = submission.get("anti_overfit_report")
    return ao if isinstance(ao, dict) else {}


def _collect_hard_gate_failures(
    gate_dict: dict[str, Any],
    release_dict: dict[str, Any],
) -> list[str]:
    """Collect names of failed hard gates from both gate sources."""
    failed: list[str] = []

    # From configured GateResult / evaluate_quality_gate
    for item in gate_dict.get("check_items") or []:
        if isinstance(item, dict) and not item.get("passed", True):
            name = str(item.get("name", ""))
            if name in OFFICIAL_HARD_GATE_NAMES or item.get("type") == "HARD":
                failed.append(name)
    for reason in gate_dict.get("failed_items") or gate_dict.get("failed_reasons") or []:
        name = str(reason).split(":")[0].strip()
        if name in OFFICIAL_HARD_GATE_NAMES:
            failed.append(name)

    # From release-score gate attributions
    for attr in release_dict.get("attributions") or []:
        if isinstance(attr, dict) and not attr.get("passed", True):
            if str(attr.get("severity", "")).upper() == "ERROR":
                failed.append(str(attr.get("name", "")))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for name in failed:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _build_triggered_rules(
    gate_dict: dict[str, Any],
    release_dict: dict[str, Any],
    ao: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a triggered-rules list for the audit trail."""
    rules: list[dict[str, Any]] = []
    for item in gate_dict.get("triggered_rules") or []:
        if isinstance(item, dict):
            rules.append({"source": "configured_gate", **item})
    for attr in release_dict.get("attributions") or []:
        if isinstance(attr, dict) and not attr.get("passed", True):
            rules.append({
                "source": "release_score_gate",
                "rule": str(attr.get("name", "")),
                "severity": str(attr.get("severity", "")),
                "reason": str(attr.get("reason", "")),
                "actual": attr.get("actual"),
                "expected": attr.get("expected"),
            })
    if ao and not ao.get("passed", False):
        rules.append({
            "source": "anti_overfit",
            "rule": str(ao.get("recommendation", "")),
            "reason": str(ao.get("reason", "statistical_robustness_below_threshold")),
            "score": ao.get("score"),
        })
    return rules


__all__ = [
    "ACTION_CONTINUE_OPTIMIZATION",
    "ACTION_DISCARD_ARCHIVE",
    "ACTION_HUMAN_CONFIRMATION",
    "ACTION_QUEUE_SIMULATION",
    "GATE_DECISION_SCHEMA_VERSION",
    "GateDecisionOutcome",
    "GateDecisionService",
]
