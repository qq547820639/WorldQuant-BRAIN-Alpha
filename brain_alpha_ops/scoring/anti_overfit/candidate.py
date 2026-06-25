from __future__ import annotations

import math
from typing import Any

from .models import (
    ANTI_OVERFIT_SCHEMA_VERSION,
    _MIN_CANDIDATE_SERIES,
)


def _candidate_report(
    *,
    ok: bool,
    passed: bool,
    recommendation: str,
    score: float,
    sample_size: int,
    data_source: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "schema_version": ANTI_OVERFIT_SCHEMA_VERSION,
        "passed": bool(passed),
        "score": float(score),
        "recommendation": recommendation,
        "sample_size": int(sample_size),
        "data_source": data_source,
        "reason": reason,
    }


def _candidate_metrics(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    metrics = _candidate_value(candidate, "official_metrics")
    return metrics if isinstance(metrics, dict) else {}


def _candidate_value(candidate: dict[str, Any] | Any, key: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key)
    return getattr(candidate, key, None)


def _number_series(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def _attach_submission_report(candidate: dict[str, Any] | Any, key: str, report: dict[str, Any]) -> None:
    if isinstance(candidate, dict):
        submission = candidate.get("submission")
        if not isinstance(submission, dict):
            submission = {}
            candidate["submission"] = submission
        submission[key] = report
        return
    submission = getattr(candidate, "submission", None)
    if not isinstance(submission, dict):
        submission = {}
        setattr(candidate, "submission", submission)
    submission[key] = report
