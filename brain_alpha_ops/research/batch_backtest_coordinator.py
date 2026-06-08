"""Batch coordination helpers for official backtest slots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.models import Candidate

from .pipeline_helpers import blocked_gate


BATCH_BACKTEST_PLAN_SCHEMA_VERSION = "batch_backtest_plan.v1"
HIGH_CLOUD_SIMILARITY_REJECTED = "HIGH_CLOUD_SIMILARITY_REJECTED"

CandidateRanker = Callable[[list[Candidate]], list[Candidate]]
CandidateRiskEvaluator = Callable[[Candidate], dict[str, Any]]


@dataclass(frozen=True)
class BacktestBatchPlan:
    selected: tuple[Candidate, ...]
    skipped: tuple[dict[str, Any], ...]
    capacity: int
    requested: int
    rate_limit: dict[str, Any] | None = None
    account_safety: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BATCH_BACKTEST_PLAN_SCHEMA_VERSION,
            "selected_count": len(self.selected),
            "skipped_count": len(self.skipped),
            "capacity": self.capacity,
            "requested": self.requested,
            "rate_limit": dict(self.rate_limit or {}),
            "account_safety": dict(self.account_safety or {}),
            "selected": [
                {
                    "alpha_id": candidate.alpha_id,
                    "score": float(candidate.scorecard.get("total_score", 0.0) or 0.0),
                    "expression": candidate.expression,
                }
                for candidate in self.selected
            ],
            "skipped": list(self.skipped),
        }


class BatchBacktestCoordinator:
    """Select and explain a batch of candidates for official backtest slots."""

    def __init__(
        self,
        *,
        ranker: CandidateRanker,
        min_score: float,
        batch_size: int,
        max_workers: int = 1,
        max_live_submissions_per_batch: int | None = None,
        risk_evaluator: CandidateRiskEvaluator | None = None,
        max_similarity_threshold: float | None = None,
    ) -> None:
        self.ranker = ranker
        self.min_score = float(min_score)
        self.batch_size = max(0, int(batch_size or 0))
        self.max_workers = max(1, int(max_workers or 1))
        self.max_live_submissions_per_batch = (
            max(0, int(max_live_submissions_per_batch))
            if max_live_submissions_per_batch is not None
            else self.batch_size
        )
        self.risk_evaluator = risk_evaluator
        self.max_similarity_threshold = (
            float(max_similarity_threshold)
            if max_similarity_threshold is not None
            else None
        )

    def plan(self, candidates: list[Candidate], *, capacity: int | None = None) -> BacktestBatchPlan:
        capacity_value = self.batch_size if capacity is None else max(0, int(capacity or 0))
        requested = min(self.batch_size, capacity_value, self.max_live_submissions_per_batch)
        skipped: list[dict[str, Any]] = []
        eligible: list[Candidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.expression.strip().lower()
            score = float(candidate.scorecard.get("total_score", 0.0) or 0.0)
            if key in seen:
                skipped.append(_skip(candidate, "duplicate_expression", score))
                continue
            seen.add(key)
            if score < self.min_score:
                skipped.append(_skip(candidate, "score_below_threshold", score))
                continue
            if candidate.simulation_id or candidate.official_metrics:
                skipped.append(_skip(candidate, "already_has_official_work", score))
                continue
            risk = self._risk(candidate)
            if _is_high_cloud_similarity(risk, self.max_similarity_threshold):
                details = _cloud_similarity_details(risk, self.max_similarity_threshold)
                _reject_high_cloud_similarity_candidate(candidate, details)
                skipped.append(_skip(
                    candidate,
                    "high_cloud_similarity",
                    score,
                    extra=details,
                ))
                continue
            eligible.append(candidate)
        selected = tuple(self.ranker(eligible)[:requested])
        return BacktestBatchPlan(
            selected=selected,
            skipped=tuple(skipped),
            capacity=capacity_value,
            requested=requested,
            rate_limit={
                "max_workers": min(self.max_workers, max(1, requested or 1)),
                "max_live_submissions_per_batch": self.max_live_submissions_per_batch,
                "bounded": True,
            },
            account_safety={
                "requires_explicit_live_confirmation": True,
                "duplicate_preflight_required": True,
                "cloud_similarity_preflight_required": bool(self.risk_evaluator),
                "similarity_threshold": self.max_similarity_threshold,
                "score_threshold": self.min_score,
            },
        )

    def _risk(self, candidate: Candidate) -> dict[str, Any]:
        if not self.risk_evaluator:
            return {}
        try:
            risk = self.risk_evaluator(candidate)
        except Exception as exc:
            from brain_alpha_ops.redaction import redact_error_message
            return {
                "level": "high",
                "max_similarity": None,
                "matched_alpha_id": "",
                "matched_status": "",
                "error": redact_error_message(exc),
            }
        return risk if isinstance(risk, dict) else {}


def _skip(candidate: Candidate, reason: str, score: float, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "alpha_id": candidate.alpha_id,
        "reason": reason,
        "score": round(score, 4),
        "expression": candidate.expression,
    }
    if extra:
        row.update(extra)
    return row


def _reject_high_cloud_similarity_candidate(candidate: Candidate, details: dict[str, Any]) -> None:
    candidate.lifecycle_status = "high_cloud_similarity_rejected"
    reasons = ["cloud_similarity_preflight_failed"]
    risk_level = str(details.get("risk_level") or "")
    if risk_level:
        reasons.append(f"risk_level={risk_level}")
    max_similarity = details.get("max_similarity")
    threshold = details.get("similarity_threshold")
    if max_similarity is not None and threshold is not None:
        reasons.append(f"max_similarity={max_similarity} >= threshold={threshold}")
    matched_alpha_id = str(details.get("matched_alpha_id") or "")
    if matched_alpha_id:
        reasons.append(f"matched_alpha_id={matched_alpha_id}")
    preflight = {
        "schema_version": "cloud_similarity_preflight.v1",
        "status": HIGH_CLOUD_SIMILARITY_REJECTED,
        **details,
    }
    candidate.gate = blocked_gate(HIGH_CLOUD_SIMILARITY_REJECTED, reasons)
    candidate.submission["cloud_similarity_preflight"] = preflight
    candidate.extra_fields["cloud_similarity_preflight"] = preflight


def _cloud_similarity_details(risk: dict[str, Any], threshold: float | None) -> dict[str, Any]:
    return {
        "risk_level": str(risk.get("level") or ""),
        "max_similarity": _float_or_none(risk.get("max_similarity")),
        "matched_alpha_id": str(risk.get("matched_alpha_id") or ""),
        "matched_status": str(risk.get("matched_status") or ""),
        "similarity_threshold": threshold,
    }


def _is_high_cloud_similarity(risk: dict[str, Any], threshold: float | None) -> bool:
    if not risk:
        return False
    level = str(risk.get("level") or "").lower()
    max_similarity = _float_or_none(risk.get("max_similarity"))
    if level == "high":
        return True
    return threshold is not None and max_similarity is not None and max_similarity >= threshold


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
