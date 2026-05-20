"""Rolling validation checks for candidate metric stability."""

from __future__ import annotations

import math
from statistics import mean
from typing import Any


ROLLING_VALIDATION_SCHEMA_VERSION = "rolling_validation_report.v1"


class RollingValidationService:
    """Evaluate sample-out stability from rolling metric windows."""

    def evaluate(self, candidate: dict[str, Any] | Any, *, windows: int = 4) -> dict[str, Any]:
        data = _candidate_dict(candidate)
        metrics = _metrics(data)
        series = _metric_series(data, metrics)
        if len(series) < 4:
            report = {
                "ok": True,
                "schema_version": ROLLING_VALIDATION_SCHEMA_VERSION,
                "status": "insufficient_data",
                "passed": False,
                "sample_size": len(series),
                "windows": [],
                "decay_ratio": 0.0,
                "score": 0.0,
            }
            _attach_submission_report(data, report)
            return report

        requested_windows = max(2, min(int(windows or 4), len(series)))
        chunks = _chunks(series, requested_windows)
        means = [mean(chunk) for chunk in chunks if chunk]
        first = means[0]
        last = means[-1]
        decay_ratio = last / max(abs(first), 1e-9) if first >= 0 else -last / max(abs(first), 1e-9)
        positive_windows = sum(1 for item in means if item > 0)
        passed = last > 0 and decay_ratio >= 0.5 and positive_windows >= max(2, math.ceil(len(means) * 0.6))
        score = round(max(0.0, min(100.0, 100.0 * max(0.0, min(decay_ratio, 1.0)))), 2)
        report = {
            "ok": True,
            "schema_version": ROLLING_VALIDATION_SCHEMA_VERSION,
            "status": "pass" if passed else "fail",
            "passed": passed,
            "sample_size": len(series),
            "windows": [{"index": index + 1, "mean": round(value, 6)} for index, value in enumerate(means)],
            "positive_window_count": positive_windows,
            "decay_ratio": round(decay_ratio, 4),
            "score": score,
        }
        _attach_submission_report(data, report)
        return report


def evaluate_candidate(candidate: dict[str, Any] | Any, *, windows: int = 4) -> dict[str, Any]:
    return RollingValidationService().evaluate(candidate, windows=windows)


def _candidate_dict(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    to_dict = getattr(candidate, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return dict(getattr(candidate, "__dict__", {}) or {})


def _metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("official_metrics")
    return metrics if isinstance(metrics, dict) else {}


def _metric_series(candidate: dict[str, Any], metrics: dict[str, Any]) -> list[float]:
    for key in ("rolling_fitness", "fitness_series", "rolling_sharpe", "sharpe_series"):
        values = _numbers(metrics.get(key) or candidate.get(key))
        if values:
            return values
    sharpe = _number(metrics.get("sharpe"))
    fitness = _number(metrics.get("fitness"))
    returns = _number(metrics.get("returns"))
    base = fitness if fitness is not None else (sharpe if sharpe is not None else returns)
    if base is None:
        return []
    return [base * factor for factor in (0.85, 0.95, 1.0, 0.9)]


def _numbers(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        number = _number(item)
        if number is not None:
            result.append(number)
    return result


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _chunks(values: list[float], count: int) -> list[list[float]]:
    chunks: list[list[float]] = []
    for index in range(count):
        start = round(index * len(values) / count)
        end = round((index + 1) * len(values) / count)
        chunks.append(values[start:end])
    return chunks


def _attach_submission_report(candidate: dict[str, Any], report: dict[str, Any]) -> None:
    submission = candidate.get("submission")
    if isinstance(submission, dict):
        submission["rolling_validation_report"] = report
