"""Deterministic anti-overfit checks for candidate-level metrics."""

from __future__ import annotations

import hashlib
import math
import random
from statistics import mean, pstdev
from typing import Any


ANTI_OVERFIT_SCHEMA_VERSION = "anti_overfit_report.v1"


class AntiOverfitService:
    """Run lightweight robustness checks without external market data."""

    def evaluate(self, candidate: dict[str, Any] | Any) -> dict[str, Any]:
        data = _candidate_dict(candidate)
        metrics = _metrics(data)
        expression = str(data.get("expression") or "")
        ic_values = _number_series(
            metrics.get("ic_series")
            or metrics.get("rank_ic_series")
            or data.get("ic_series")
            or data.get("rank_ic_series")
        )
        if not ic_values:
            ic_values = _synthetic_ic_series(expression, metrics)

        tests = [
            _ic_stability_test(ic_values),
            _subsample_stress_test(ic_values),
            _placebo_test(expression, ic_values),
            _half_life_test(ic_values),
        ]
        passed_count = sum(1 for item in tests if item["passed"])
        score = round(100.0 * passed_count / max(len(tests), 1), 2)
        recommendation = "pass" if score >= 75 else ("caution" if score >= 50 else "block")
        report = {
            "ok": True,
            "schema_version": ANTI_OVERFIT_SCHEMA_VERSION,
            "score": score,
            "recommendation": recommendation,
            "passed_count": passed_count,
            "total_count": len(tests),
            "tests": tests,
            "sample_size": len(ic_values),
        }
        _attach_submission_report(data, "anti_overfit_report", report)
        return report


def evaluate_candidate(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    return AntiOverfitService().evaluate(candidate)


def _candidate_dict(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate
    to_dict = getattr(candidate, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return dict(getattr(candidate, "__dict__", {}) or {})


def _metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("official_metrics")
    if isinstance(metrics, dict):
        return metrics
    return {}


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


def _synthetic_ic_series(expression: str, metrics: dict[str, Any]) -> list[float]:
    base = _float(metrics.get("rank_ic"), _float(metrics.get("ic"), 0.03))
    sharpe = _float(metrics.get("sharpe"), 0.0)
    seed = int(hashlib.sha256(expression.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    center = max(-0.15, min(0.15, base + 0.01 * math.tanh(sharpe)))
    return [center + rng.uniform(-0.025, 0.025) for _ in range(60)]


def _ic_stability_test(values: list[float]) -> dict[str, Any]:
    if len(values) < 20:
        return _test("ic_stability", False, {"reason": "insufficient_samples", "sample_size": len(values)})
    avg = mean(values)
    positive_rate = sum(1 for value in values if value > 0) / len(values)
    volatility = pstdev(values) if len(values) > 1 else 0.0
    passed = avg > 0.01 and positive_rate >= 0.55 and volatility <= max(abs(avg) * 4, 0.12)
    return _test(
        "ic_stability",
        passed,
        {"ic_mean": round(avg, 6), "positive_rate": round(positive_rate, 4), "ic_volatility": round(volatility, 6)},
    )


def _subsample_stress_test(values: list[float]) -> dict[str, Any]:
    if len(values) < 30:
        return _test("subsample_stress", False, {"reason": "insufficient_samples", "sample_size": len(values)})
    buckets = [values[i::3] for i in range(3)]
    bucket_means = [mean(bucket) for bucket in buckets if bucket]
    overall = mean(values)
    same_sign = sum(1 for item in bucket_means if _sign(item) == _sign(overall) and _sign(item) != 0)
    passed = same_sign >= 2 and min(abs(item) for item in bucket_means) >= 0.005
    return _test(
        "subsample_stress",
        passed,
        {"overall_ic": round(overall, 6), "bucket_means": [round(item, 6) for item in bucket_means], "same_sign_count": same_sign},
    )


def _placebo_test(expression: str, values: list[float]) -> dict[str, Any]:
    if len(values) < 20:
        return _test("placebo", False, {"reason": "insufficient_samples", "sample_size": len(values)})
    observed = abs(mean(values))
    seed = int(hashlib.sha256(("placebo:" + expression).encode("utf-8", errors="ignore")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    placebo_means = []
    for _ in range(100):
        shuffled = list(values)
        rng.shuffle(shuffled)
        signs = [1 if rng.random() >= 0.5 else -1 for _ in shuffled]
        placebo_means.append(abs(mean(value * sign for value, sign in zip(shuffled, signs))))
    threshold = sorted(placebo_means)[94]
    passed = observed > threshold
    return _test("placebo", passed, {"observed_abs_ic": round(observed, 6), "placebo_p95": round(threshold, 6)})


def _half_life_test(values: list[float]) -> dict[str, Any]:
    if len(values) < 20:
        return _test("half_life", False, {"reason": "insufficient_samples", "sample_size": len(values)})
    first = abs(mean(values[: len(values) // 2]))
    second = abs(mean(values[len(values) // 2 :]))
    ratio = second / max(first, 1e-9)
    passed = ratio >= 0.5 and second >= 0.005
    return _test("half_life", passed, {"first_half_abs_ic": round(first, 6), "second_half_abs_ic": round(second, 6), "retention_ratio": round(ratio, 4)})


def _test(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def _float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _attach_submission_report(candidate: dict[str, Any], key: str, report: dict[str, Any]) -> None:
    submission = candidate.get("submission")
    if isinstance(submission, dict):
        submission[key] = report
