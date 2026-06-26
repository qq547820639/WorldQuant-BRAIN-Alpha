"""Multi-dimensional retrospective attribution (Workstream D3.1).

Aggregates scorecards by gate / metric / dataset / region / time so the
audit trail and the frontend can explain *why* candidates were ranked or
blocked across each dimension.

Kept in a sibling module so ``scoring/attribution.py`` stays under the
350-line limit while the single-card ``build_attribution_tree`` remains the
canonical per-candidate attribution.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

MULTI_DIM_ATTRIBUTION_SCHEMA = "multi_dim_attribution.v1"


@dataclass
class DimensionSummary:
    """Aggregate statistics for a single dimension value."""

    dimension: str
    value: str
    count: int = 0
    avg_score: float = 0.0
    pass_count: int = 0
    fail_count: int = 0
    top_failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "count": self.count,
            "avg_score": round(self.avg_score, 2),
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "top_failures": list(self.top_failures),
        }


def build_multi_dimensional_attribution(
    scorecards: Iterable[dict[str, Any]],
    *,
    candidates: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Aggregate scorecards across gate / metric / dataset / region / time.

    Args:
        scorecards: iterable of scorecard dicts (each from ``build_scorecard``).
        candidates: optional iterable of Candidate objects providing
            dataset / region / universe / timestamp context.

    Returns a dict keyed by dimension with per-value ``DimensionSummary`` lists.
    """
    cards = list(scorecards)
    cand_list = list(candidates) if candidates is not None else []
    cand_by_alpha: dict[str, Any] = {}
    for c in cand_list:
        aid = str(getattr(c, "alpha_id", "") or "")
        if aid:
            cand_by_alpha[aid] = c

    by_gate = _aggregate_by_gate(cards)
    by_metric = _aggregate_by_metric(cards)
    by_dataset = _aggregate_by_context(cards, cand_by_alpha, "dataset")
    by_region = _aggregate_by_context(cards, cand_by_alpha, "region")
    by_time = _aggregate_by_time(cards, cand_by_alpha)

    return {
        "schema_version": MULTI_DIM_ATTRIBUTION_SCHEMA,
        "dimensions": {
            "by_gate": [d.to_dict() for d in by_gate],
            "by_metric": [d.to_dict() for d in by_metric],
            "by_dataset": [d.to_dict() for d in by_dataset],
            "by_region": [d.to_dict() for d in by_region],
            "by_time": [d.to_dict() for d in by_time],
        },
        "total_scorecards": len(cards),
    }


def _aggregate_by_gate(cards: list[dict[str, Any]]) -> list[DimensionSummary]:
    """Aggregate pass/fail counts per hard-gate name across scorecards."""
    buckets: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    for card in cards:
        empirical = card.get("empirical") or {}
        for item in empirical.get("items") or []:
            name = str(item.get("name", "") or "unknown")
            bucket = buckets[name]
            bucket["count"] += 1
            bucket["scores"].append(float(item.get("points", 0) or 0))
            if item.get("passed"):
                bucket["pass"] += 1
            else:
                bucket["fail"] += 1
                if item.get("is_hard_gate"):
                    bucket["failures"].append(name)
    return _to_summaries("by_gate", buckets)


def _aggregate_by_metric(cards: list[dict[str, Any]]) -> list[DimensionSummary]:
    """Aggregate official metric values (sharpe/fitness/turnover/...) across cards."""
    buckets: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    for card in cards:
        empirical = card.get("empirical") or {}
        for item in empirical.get("items") or []:
            name = str(item.get("name", "") or "unknown")
            actual = item.get("actual")
            if actual is None:
                continue
            bucket = buckets[name]
            bucket["count"] += 1
            try:
                bucket["scores"].append(float(actual))
            except (TypeError, ValueError):
                pass
            if item.get("passed"):
                bucket["pass"] += 1
            else:
                bucket["fail"] += 1
    return _to_summaries("by_metric", buckets)


def _aggregate_by_context(
    cards: list[dict[str, Any]],
    cand_by_alpha: dict[str, Any],
    field_name: str,
) -> list[DimensionSummary]:
    """Aggregate by a context field (dataset / region / universe)."""
    buckets: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    for card in cards:
        alpha_id = str(card.get("alpha_id", "") or "")
        candidate = cand_by_alpha.get(alpha_id)
        if candidate is None:
            continue
        value = _extract_context_value(candidate, field_name)
        if not value:
            continue
        bucket = buckets[value]
        bucket["count"] += 1
        bucket["scores"].append(float(card.get("total_score", 0) or 0))
        gate = _card_gate(card)
        if gate.get("submission_ready"):
            bucket["pass"] += 1
        else:
            bucket["fail"] += 1
            for reason in gate.get("failed_reasons") or []:
                bucket["failures"].append(str(reason))
    return _to_summaries(f"by_{field_name}", buckets)


def _aggregate_by_time(
    cards: list[dict[str, Any]],
    cand_by_alpha: dict[str, Any],
) -> list[DimensionSummary]:
    """Aggregate by date bucket (YYYY-MM) derived from candidate timestamps."""
    buckets: dict[str, dict[str, Any]] = defaultdict(_new_bucket)
    for card in cards:
        alpha_id = str(card.get("alpha_id", "") or "")
        candidate = cand_by_alpha.get(alpha_id)
        if candidate is None:
            continue
        month = _extract_month(candidate)
        if not month:
            continue
        bucket = buckets[month]
        bucket["count"] += 1
        bucket["scores"].append(float(card.get("total_score", 0) or 0))
        gate = _card_gate(card)
        if gate.get("submission_ready"):
            bucket["pass"] += 1
        else:
            bucket["fail"] += 1
    return _to_summaries("by_time", buckets)


def _new_bucket() -> dict[str, Any]:
    return {"count": 0, "scores": [], "pass": 0, "fail": 0, "failures": []}


def _to_summaries(
    dimension: str,
    buckets: dict[str, dict[str, Any]],
) -> list[DimensionSummary]:
    out: list[DimensionSummary] = []
    for value, data in sorted(buckets.items()):
        scores = data["scores"]
        avg = sum(scores) / len(scores) if scores else 0.0
        failures = data.get("failures") or []
        seen: set[str] = set()
        top_failures: list[str] = []
        for f in failures:
            if f and f not in seen:
                seen.add(f)
                top_failures.append(f)
            if len(top_failures) >= 5:
                break
        out.append(DimensionSummary(
            dimension=dimension, value=value, count=data["count"],
            avg_score=avg, pass_count=data["pass"], fail_count=data["fail"],
            top_failures=top_failures,
        ))
    return out


def _card_gate(card: dict[str, Any]) -> dict[str, Any]:
    gate = card.get("gate")
    return gate if isinstance(gate, dict) else {}


def _extract_context_value(candidate: Any, field_name: str) -> str:
    submission = getattr(candidate, "submission", None)
    if isinstance(submission, dict):
        settings = submission.get("settings") or submission.get("brain_settings")
        if isinstance(settings, dict):
            val = settings.get(field_name) or settings.get(f"{field_name}_id")
            if val:
                return str(val)
    validation = getattr(candidate, "validation", None)
    if isinstance(validation, dict):
        settings = validation.get("settings")
        if isinstance(settings, dict):
            val = settings.get(field_name)
            if val:
                return str(val)
    extra = getattr(candidate, "extra_fields", None)
    if isinstance(extra, dict):
        val = extra.get(field_name)
        if val:
            return str(val)
    return ""


def _extract_month(candidate: Any) -> str:
    for attr in ("created_at", "evaluated_at", "updated_at"):
        raw = getattr(candidate, attr, None)
        if not raw:
            continue
        text = str(raw)
        # ISO prefix YYYY-MM
        if len(text) >= 7 and text[4] == "-":
            return text[:7]
    return ""


__all__ = [
    "MULTI_DIM_ATTRIBUTION_SCHEMA",
    "DimensionSummary",
    "build_multi_dimensional_attribution",
]
