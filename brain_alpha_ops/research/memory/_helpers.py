"""Helper functions for the ``ResearchMemory`` module.

Extracted from the original ``memory.py`` monolith. These private helpers
compute aggregate statistics over candidate/lifecycle/check records and
support the higher-level ``ResearchMemory.summary`` /
``ResearchMemory.generation_guidance`` APIs.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable


def _stat_bucket() -> dict[str, Any]:
    return {
        "count": 0,
        "success_count": 0,
        "score_sum": 0.0,
        "sharpe_sum": 0.0,
        "fitness_sum": 0.0,
        "pass_fail": Counter(),
    }

def _update_bucket(bucket: dict[str, Any], score: float, metrics: dict[str, Any], passed: bool) -> None:
    bucket["count"] += 1
    bucket["success_count"] += 1 if passed else 0
    bucket["score_sum"] += score
    bucket["sharpe_sum"] += _num(metrics.get("sharpe"))
    bucket["fitness_sum"] += _num(metrics.get("fitness"))
    if metrics.get("pass_fail"):
        bucket["pass_fail"][str(metrics.get("pass_fail"))] += 1

def _rank_buckets(buckets: dict[str, dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    rows = []
    for name, bucket in buckets.items():
        count = max(1, int(bucket["count"]))
        rows.append({
            "name": name,
            "count": bucket["count"],
            "success_count": bucket["success_count"],
            "success_rate": round(bucket["success_count"] / count, 3),
            "avg_score": round(bucket["score_sum"] / count, 3),
            "avg_sharpe": round(bucket["sharpe_sum"] / count, 3),
            "avg_fitness": round(bucket["fitness_sum"] / count, 3),
            "pass_fail": dict(bucket["pass_fail"].most_common()),
        })
    rows.sort(key=lambda item: (item["success_rate"], item["avg_score"], item["count"]), reverse=True)
    return rows[:top_n]

def _rank_guidance_buckets(buckets: dict[str, dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    rows = _rank_buckets(buckets, top_n)
    for row in rows:
        row["guidance_digest"] = row.pop("name", "")
    return rows

def _finalize_stat_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    count = int(bucket.get("count") or 0)
    success_count = int(bucket.get("success_count") or 0)
    score_total = float(bucket.get("score_sum") or 0.0)
    sharpe_total = float(bucket.get("sharpe_sum") or 0.0)
    fitness_total = float(bucket.get("fitness_sum") or 0.0)
    return {
        "count": count,
        "success_count": success_count,
        "success_rate": round(success_count / count, 4) if count else 0.0,
        "avg_score": round(score_total / count, 4) if count else 0.0,
        "avg_sharpe": round(sharpe_total / count, 4) if count else 0.0,
        "avg_fitness": round(fitness_total / count, 4) if count else 0.0,
    }

def _recommendations(
    field_stats: dict[str, dict[str, Any]],
    operator_stats: dict[str, dict[str, Any]],
    failure_patterns: Counter[str],
) -> list[str]:
    recommendations: list[str] = []
    top_fields = _rank_buckets(field_stats, 3)
    top_ops = _rank_buckets(operator_stats, 3)
    if top_fields:
        recommendations.append("Prefer fields with stronger observed outcomes: " + ", ".join(row["name"] for row in top_fields))
    if top_ops:
        recommendations.append("Prefer operators with stronger observed outcomes: " + ", ".join(row["name"] for row in top_ops))
    if failure_patterns:
        reason, _count = failure_patterns.most_common(1)[0]
        recommendations.append(f"Prioritize fixes for the most common failure pattern: {reason}")
    return recommendations

def _top_windows(records: list[dict[str, Any]], features: list[dict[str, Any]], top_n: int) -> list[int]:
    counter: Counter[int] = Counter()
    for row in records:
        for window in _as_list(row.get("window_values")):
            parsed = _parse_window(window)
            if parsed:
                counter[parsed] += 1
        expression = str(row.get("expression") or "")
        for window in re.findall(r"\b(\d{1,3})\b", expression):
            parsed = _parse_window(window)
            if parsed:
                counter[parsed] += 1
    for row in features:
        for window in _as_list(row.get("window_values")):
            parsed = _parse_window(window)
            if parsed:
                counter[parsed] += 1
    return [window for window, _count in counter.most_common(top_n)]

def _top_field_combinations(
    records: list[dict[str, Any]],
    feature_by_id: dict[str, dict[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], dict[str, float]] = {}
    counts: Counter[tuple[str, ...]] = Counter()
    for row in records:
        alpha_id = str(row.get("alpha_id", "") or "")
        fields = _as_list(row.get("data_fields")) or _as_list((feature_by_id.get(alpha_id) or {}).get("field_set"))
        combo = tuple(sorted(str(field) for field in fields if str(field).strip()))
        if not combo:
            continue
        counts[combo] += 1
        bucket = buckets.setdefault(combo, {"sharpe_sum": 0.0})
        bucket["sharpe_sum"] += _num((row.get("official_metrics") or {}).get("sharpe", (feature_by_id.get(alpha_id) or {}).get("sharpe")))

    rows: list[dict[str, Any]] = []
    for combo, count in counts.most_common(top_n):
        bucket = buckets.get(combo) or {"sharpe_sum": 0.0}
        rows.append({
            "fields": list(combo),
            "count": count,
            "avg_sharpe": round(bucket["sharpe_sum"] / max(1, count), 3),
        })
    return rows

def _parse_window(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if 2 <= parsed <= 252:
        return parsed
    return None

def _metrics_for(candidate: dict[str, Any], feature: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(candidate.get("official_metrics") or {})
    for key in ("sharpe", "fitness", "turnover", "returns", "drawdown", "correlation", "margin", "pass_fail", "failure_reason"):
        if key not in metrics and key in feature:
            metrics[key] = feature[key]
    return metrics

def _score_for(row: dict[str, Any]) -> float:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    return _num(scorecard.get("total_score", row.get("score", 0.0)))

def _is_success(row: dict[str, Any], metrics: dict[str, Any]) -> bool:
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    status = str(row.get("lifecycle_status") or gate.get("status") or "").lower()
    pass_fail = str(metrics.get("pass_fail") or "").upper()
    return bool(gate.get("submission_ready")) or status in {"submission_ready", "submitted"} or pass_fail == "PASS"

def _failure_reasons(row: dict[str, Any]) -> Iterable[str]:
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    validation = row.get("validation") if isinstance(row.get("validation"), dict) else {}
    metrics = row.get("official_metrics") if isinstance(row.get("official_metrics"), dict) else {}

    for value in _as_list(gate.get("failed_reasons")):
        yield _clean_reason(value)
    for value in _as_list(validation.get("errors")):
        yield _clean_reason(value)
    for value in _as_list(row.get("failed_checks")):
        if isinstance(value, dict):
            yield _clean_reason(value.get("name") or value.get("message") or value)
        else:
            yield _clean_reason(value)
    for key in ("failure_reason", "error", "note"):
        value = row.get(key) or metrics.get(key)
        if value:
            yield _clean_reason(value)

def _candidate_guidance_digest(row: dict[str, Any]) -> str:
    submission = row.get("submission") if isinstance(row.get("submission"), dict) else {}
    for key in ("assistant_guidance_digest", "guidance_digest"):
        digest = str(submission.get(key) or row.get(key) or "").strip()
        if digest:
            return digest
    for tag in _as_list(row.get("source_tags")):
        text = str(tag)
        if text.startswith("assistant_guidance_"):
            return text.removeprefix("assistant_guidance_")
    return ""

def _guidance_outcome_status(row: dict[str, Any]) -> str:
    if not row:
        return "unknown"
    if _is_weak_guidance_outcome(row):
        return "weak"
    count = int(_num(row.get("count")))
    if count <= 0:
        return "unknown"
    if _num(row.get("success_rate")) >= 0.5 or _num(row.get("avg_score")) >= 70:
        return "strong"
    return "neutral"

def _is_weak_guidance_outcome(row: dict[str, Any]) -> bool:
    count = int(_num(row.get("count")))
    if count < 2:
        return False
    success_rate = _num(row.get("success_rate"))
    avg_score = _num(row.get("avg_score"))
    return success_rate <= 0.25 or avg_score <= 50

def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]

def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)

def _has_generator_bias(guidance: dict[str, Any]) -> bool:
    return bool(
        guidance.get("top_fields")
        or guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
    )

def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)

def _clean_reason(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:180] if text else "unknown"

def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
