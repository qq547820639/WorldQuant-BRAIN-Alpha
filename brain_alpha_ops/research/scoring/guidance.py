"""Assistant-guidance score adjustment.

Contains ``assistant_guidance_score_adjustment`` — a conservative local-ranking
adjustment derived from historical assistant-guidance outcomes.
"""

from __future__ import annotations

from brain_alpha_ops.config import ScoringConfig
from brain_alpha_ops.models import Candidate

from ._helpers import (
    _bounded_score,
    _guidance_outcome_status,
    _int_num,
    _normalize_confidence,
    _num,
)


def assistant_guidance_score_adjustment(
    candidate: Candidate,
    *,
    scoring: ScoringConfig | None = None,
) -> dict:
    """Small local-ranking adjustment from historical assistant-guidance outcomes.

    This is intentionally conservative and only affects the local queueing score
    in ``build_scorecard``. Official metrics still dominate once available.
    """
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    digest = str(submission.get("assistant_guidance_digest") or "").strip()
    enabled = bool(getattr(scoring, "assistant_guidance_score_adjustment_enabled", True)) if scoring else True
    min_confidence = max(0.0, min(1.0, _num(getattr(scoring, "assistant_guidance_score_min_confidence", 0.6) if scoring else 0.6)))
    min_outcome_count = max(0, _int_num(getattr(scoring, "assistant_guidance_score_min_outcome_count", 1) if scoring else 1))
    bonus_cap = max(0.0, _num(getattr(scoring, "assistant_guidance_score_bonus_cap", 4.0) if scoring else 4.0))
    penalty_cap = max(0.0, _num(getattr(scoring, "assistant_guidance_score_penalty_cap", 5.0) if scoring else 5.0))
    config_snapshot = {
        "enabled": enabled,
        "min_confidence": min_confidence,
        "min_outcome_count": min_outcome_count,
        "bonus_cap": bonus_cap,
        "penalty_cap": penalty_cap,
    }
    if not enabled:
        return {
            "source": "disabled",
            "guidance_digest": digest,
            "outcome_status": "disabled",
            "outcome_count": 0,
            "success_rate": 0.0,
            "avg_score": 0.0,
            "confidence": 0.0,
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "assistant guidance score adjustment disabled by scoring config",
        }
    if not digest:
        return {
            "source": "none",
            "guidance_digest": "",
            "outcome_status": "none",
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "candidate has no assistant guidance metadata",
        }

    outcome = submission.get("assistant_guidance_outcome") if isinstance(submission.get("assistant_guidance_outcome"), dict) else {}
    count = _int_num(outcome.get("count", submission.get("assistant_guidance_outcome_count")))
    success_rate = _num(outcome.get("success_rate", submission.get("assistant_guidance_outcome_success_rate")))
    avg_score = _num(outcome.get("avg_score", submission.get("assistant_guidance_outcome_avg_score")))
    confidence = _normalize_confidence(submission.get("assistant_guidance_confidence"))
    status = str(submission.get("assistant_guidance_outcome_status") or "").strip().lower()
    if status not in {"strong", "neutral", "weak", "unknown"}:
        status = _guidance_outcome_status(count, success_rate, avg_score)

    if confidence < min_confidence:
        return {
            "source": "assistant_guidance_outcome",
            "guidance_digest": digest,
            "outcome_status": status or "unknown",
            "outcome_count": count,
            "success_rate": round(success_rate, 4),
            "avg_score": round(avg_score, 4),
            "confidence": confidence,
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "assistant guidance confidence is below scoring adjustment threshold",
        }
    if count < min_outcome_count:
        return {
            "source": "assistant_guidance_outcome",
            "guidance_digest": digest,
            "outcome_status": status or "unknown",
            "outcome_count": count,
            "success_rate": round(success_rate, 4),
            "avg_score": round(avg_score, 4),
            "confidence": confidence,
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "assistant guidance has too little historical outcome evidence for scoring adjustment",
        }

    adjustment = 0.0
    reason = "assistant guidance has no historical outcome evidence"
    if status == "strong":
        adjustment = 2.0
        if success_rate >= 0.75:
            adjustment += 1.0
        if avg_score >= 85:
            adjustment += 1.0
        reason = "historically strong assistant guidance gets a conservative local ranking bonus"
    elif status == "weak":
        adjustment = -3.0
        if count >= 2 and success_rate <= 0.0:
            adjustment -= 1.0
        if avg_score and avg_score < 40:
            adjustment -= 1.0
        reason = "historically weak assistant guidance gets a local ranking penalty"
    elif status == "neutral":
        adjustment = 0.75 if count else 0.0
        reason = "neutral assistant guidance history gets only a tiny local ranking nudge"

    if adjustment > 0:
        adjustment *= confidence
    adjustment = round(max(-penalty_cap, min(bonus_cap, adjustment)), 2)
    return {
        "source": "assistant_guidance_outcome",
        "guidance_digest": digest,
        "outcome_status": status or "unknown",
        "outcome_count": count,
        "success_rate": round(success_rate, 4),
        "avg_score": round(avg_score, 4),
        "confidence": confidence,
        "adjustment": adjustment,
        "configuration": config_snapshot,
        "reason": reason,
    }
