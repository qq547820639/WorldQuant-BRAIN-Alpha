"""Submission-aware policy over deterministic robustness reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brain_alpha_ops.models import Candidate


ROBUSTNESS_POLICY_SCHEMA_VERSION = "robustness_policy.v1"


@dataclass(frozen=True)
class RobustnessDecision:
    action: str
    score_multiplier: float
    blocked: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ROBUSTNESS_POLICY_SCHEMA_VERSION,
            "action": self.action,
            "score_multiplier": self.score_multiplier,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


class RobustnessPolicy:
    """Convert anti-overfit and rolling validation reports into gate effects."""

    def __init__(
        self,
        *,
        block_on_anti_overfit: bool = True,
        block_on_rolling_failure: bool = False,
        caution_multiplier: float = 0.9,
        block_multiplier: float = 0.0,
    ) -> None:
        self.block_on_anti_overfit = bool(block_on_anti_overfit)
        self.block_on_rolling_failure = bool(block_on_rolling_failure)
        self.caution_multiplier = max(0.0, min(1.0, float(caution_multiplier)))
        self.block_multiplier = max(0.0, min(1.0, float(block_multiplier)))

    def decide(self, anti_overfit_report: dict[str, Any], rolling_validation_report: dict[str, Any]) -> RobustnessDecision:
        reasons: list[str] = []
        warnings: list[str] = []
        action = "allow"
        multiplier = 1.0

        anti_recommendation = str(anti_overfit_report.get("recommendation") or "").strip().lower()
        if anti_recommendation == "block":
            message = "anti-overfit recommendation is block"
            if self.block_on_anti_overfit:
                reasons.append(message)
                action = "block"
                multiplier = self.block_multiplier
            else:
                warnings.append(message)
                action = "downgrade"
                multiplier = min(multiplier, self.caution_multiplier)
        elif anti_recommendation == "caution":
            warnings.append("anti-overfit recommendation is caution")
            action = "downgrade"
            multiplier = min(multiplier, self.caution_multiplier)

        rolling_status = str(rolling_validation_report.get("status") or "").strip().lower()
        rolling_passed = rolling_validation_report.get("passed")
        if rolling_status == "insufficient_data":
            warnings.append("rolling validation has insufficient data")
            if action == "allow":
                action = "downgrade"
            multiplier = min(multiplier, self.caution_multiplier)
        elif rolling_passed is False:
            message = "rolling validation failed"
            if self.block_on_rolling_failure:
                reasons.append(message)
                action = "block"
                multiplier = self.block_multiplier
            else:
                warnings.append(message)
                if action != "block":
                    action = "downgrade"
                    multiplier = min(multiplier, self.caution_multiplier)

        blocked = bool(reasons)
        if blocked:
            action = "block"
        return RobustnessDecision(
            action=action,
            score_multiplier=round(multiplier, 4),
            blocked=blocked,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
        )

    def apply(
        self,
        candidate: Candidate,
        anti_overfit_report: dict[str, Any],
        rolling_validation_report: dict[str, Any],
    ) -> dict[str, Any]:
        decision = self.decide(anti_overfit_report, rolling_validation_report)
        payload = decision.to_dict()
        candidate.submission["robustness_policy"] = payload
        scorecard = candidate.scorecard if isinstance(candidate.scorecard, dict) else {}
        if scorecard and decision.score_multiplier < 1.0:
            original = _float(scorecard.get("total_score"), 0.0)
            scorecard["robustness_original_total_score"] = original
            scorecard["robustness_score_multiplier"] = decision.score_multiplier
            scorecard["total_score"] = round(original * decision.score_multiplier, 2)
            scorecard["robustness_policy"] = payload
            candidate.scorecard = scorecard
        gate = candidate.gate if isinstance(candidate.gate, dict) else {}
        if decision.warnings:
            gate.setdefault("warnings", [])
            gate["warnings"].extend(f"ROBUSTNESS:{item}" for item in decision.warnings)
        if decision.blocked:
            gate.setdefault("failed_reasons", [])
            gate["failed_reasons"].extend(f"ROBUSTNESS:{item}" for item in decision.reasons)
            gate["submission_ready"] = False
            gate["status"] = "ROBUSTNESS_BLOCKED"
            gate["hard_gate_blocked"] = True
        gate["robustness_policy"] = payload
        candidate.gate = gate
        return payload


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
