"""Research memory built from append-only alpha records.

The memory layer summarizes what the system has already tried: which fields and
operators worked, which hypotheses failed, and how alpha variants relate to
their parents.  It reads existing JSONL stores and does not change the primary
pipeline write path.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any, Iterable

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest


class ResearchMemory:
    def __init__(self, storage_dir: str | Path = "data"):
        self.storage_dir = Path(storage_dir)

    def summary(self, *, limit: int = 5000, top_n: int = 10) -> dict[str, Any]:
        records = self._load_candidate_records(limit=limit)
        lifecycle = self._load_jsonl("lifecycle.jsonl", limit=limit)
        checks = self._load_jsonl("checks.jsonl", limit=limit)
        features = self._load_jsonl("alpha_features.jsonl", limit=limit)

        candidates_by_id = {str(row.get("alpha_id", "")): row for row in records if row.get("alpha_id")}
        feature_by_id = {str(row.get("alpha_id", "")): row for row in features if row.get("alpha_id")}
        preferred_windows = _top_windows(records, features, top_n)
        field_combinations = _top_field_combinations(records, feature_by_id, top_n)

        field_stats: dict[str, dict[str, Any]] = defaultdict(_stat_bucket)
        operator_stats: dict[str, dict[str, Any]] = defaultdict(_stat_bucket)
        family_stats: dict[str, dict[str, Any]] = defaultdict(_stat_bucket)
        hypothesis_stats: dict[str, dict[str, Any]] = defaultdict(_stat_bucket)
        status_counts: Counter[str] = Counter()
        failure_patterns: Counter[str] = Counter()
        lineage: dict[str, dict[str, Any]] = {}
        assistant_guided_stats = _stat_bucket()
        assistant_guidance_stats: dict[str, dict[str, Any]] = defaultdict(_stat_bucket)

        for row in records:
            alpha_id = str(row.get("alpha_id", "") or "")
            metrics = _metrics_for(row, feature_by_id.get(alpha_id, {}))
            score = _score_for(row)
            passed = _is_success(row, metrics)
            status = str(row.get("lifecycle_status") or (row.get("gate") or {}).get("status") or "unknown")
            status_counts[status] += 1

            _update_bucket(family_stats[str(row.get("family") or "unknown")], score, metrics, passed)
            _update_bucket(hypothesis_stats[str(row.get("hypothesis") or "unknown")], score, metrics, passed)
            if "assistant_guided" in _as_list(row.get("source_tags")):
                _update_bucket(assistant_guided_stats, score, metrics, passed)
                guidance_digest = _candidate_guidance_digest(row)
                if guidance_digest:
                    bucket = assistant_guidance_stats[guidance_digest]
                    bucket["guidance_digest"] = guidance_digest
                    _update_bucket(bucket, score, metrics, passed)

            for field in _as_list(row.get("data_fields")) or _as_list((feature_by_id.get(alpha_id) or {}).get("field_set")):
                _update_bucket(field_stats[str(field)], score, metrics, passed)
            for operator in _as_list(row.get("operators")) or _as_list((feature_by_id.get(alpha_id) or {}).get("operator_set")):
                _update_bucket(operator_stats[str(operator)], score, metrics, passed)

            for reason in _failure_reasons(row):
                failure_patterns[reason] += 1

            parent_id = str(row.get("parent_id") or "")
            if parent_id:
                parent = lineage.setdefault(
                    parent_id,
                    {"parent_id": parent_id, "children": [], "mutation_types": Counter(), "best_child_score": 0.0},
                )
                parent["children"].append(alpha_id)
                parent["mutation_types"][str(row.get("mutation_type") or "unknown")] += 1
                parent["best_child_score"] = max(parent["best_child_score"], score)

        for row in lifecycle:
            for reason in _failure_reasons(row):
                failure_patterns[reason] += 1
        for row in checks:
            for reason in _failure_reasons(row):
                failure_patterns[reason] += 1

        lineage_rows = []
        for row in lineage.values():
            lineage_rows.append({
                "parent_id": row["parent_id"],
                "child_count": len(row["children"]),
                "children": row["children"][:top_n],
                "mutation_types": dict(row["mutation_types"].most_common()),
                "best_child_score": round(row["best_child_score"], 3),
            })
        lineage_rows.sort(key=lambda item: (item["child_count"], item["best_child_score"]), reverse=True)

        return {
            "ok": True,
            "source": "local_jsonl_research_memory",
            "storage_dir": str(self.storage_dir),
            "total_candidates": len(records),
            "total_lifecycle_records": len(lifecycle),
            "total_check_records": len(checks),
            "total_feature_records": len(features),
            "status_counts": dict(status_counts.most_common()),
            "families": _rank_buckets(family_stats, top_n),
            "hypotheses": _rank_buckets(hypothesis_stats, top_n),
            "fields": _rank_buckets(field_stats, top_n),
            "operators": _rank_buckets(operator_stats, top_n),
            "preferred_windows": preferred_windows,
            "field_combinations": field_combinations,
            "assistant_guided": _finalize_stat_bucket(assistant_guided_stats),
            "assistant_guidance_outcomes": _rank_guidance_buckets(assistant_guidance_stats, top_n),
            "expression_index": ExpressionHistoryIndex(self.storage_dir).summary(
                limit=limit,
                top_n=top_n,
                source_rows={
                    "candidates.jsonl": records,
                    "lifecycle.jsonl": lifecycle,
                    "checks.jsonl": checks,
                },
            ),
            "failure_patterns": [
                {"reason": reason, "count": count}
                for reason, count in failure_patterns.most_common(top_n)
            ],
            "lineage": lineage_rows[:top_n],
            "recommendations": _recommendations(field_stats, operator_stats, failure_patterns),
        }

    def generation_guidance(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        min_success_rate: float = 0.0,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return memory-derived patterns compatible with generator guidance."""
        summary = summary if isinstance(summary, dict) else self.summary(limit=limit, top_n=top_n)

        fields = [
            row["name"] for row in summary.get("fields", [])
            if row.get("name") and float(row.get("success_rate") or 0.0) >= min_success_rate
        ][:top_n]
        operators = [
            row["name"] for row in summary.get("operators", [])
            if row.get("name") and float(row.get("success_rate") or 0.0) >= min_success_rate
        ][:top_n]
        families = [
            row["name"] for row in summary.get("families", [])
            if row.get("name") and row.get("name") != "unknown"
        ][:top_n]
        hypotheses = [
            row["name"] for row in summary.get("hypotheses", [])
            if row.get("name") and row.get("name") != "unknown"
        ][:top_n]
        windows = list(summary.get("preferred_windows") or [])[:top_n]
        field_combinations = list(summary.get("field_combinations") or [])[:top_n]

        sample_size = int(summary.get("total_candidates") or 0)
        return {
            "ok": True,
            "source": "local_jsonl_research_memory",
            "sample_size": sample_size,
            "total_records": sample_size,
            "top_fields": fields,
            "field_combinations": field_combinations,
            "top_operators": operators,
            "preferred_windows": windows,
            "top_categories": families,
            "top_hypotheses": hypotheses,
            "failure_patterns": summary.get("failure_patterns", [])[:top_n],
            "recommendations": summary.get("recommendations", []),
            "summary": (
                f"Research memory guidance from {sample_size} candidates. "
                f"Top fields: {', '.join(fields[:5]) or 'none'}. "
                f"Top operators: {', '.join(operators[:5]) or 'none'}. "
                f"Preferred windows: {windows or []}."
            ),
        }

    def latest_assistant_guidance(
        self,
        *,
        limit: int = 100,
        min_confidence: float = 0.0,
    ) -> dict[str, Any]:
        """Return the newest persisted assistant guidance that is usable."""
        rows = self._load_jsonl("assistant_guidance.jsonl", limit=limit)
        threshold = _clamp(_num(min_confidence), 0.0, 1.0)
        outcome_top_n = max(100, int(limit or 100))
        memory_summary = self.summary(limit=5000, top_n=outcome_top_n)
        outcomes_by_guidance = {
            str(row.get("guidance_digest") or ""): row
            for row in memory_summary.get("assistant_guidance_outcomes", [])
            if row.get("guidance_digest")
        }
        weak_rejection: dict[str, Any] = {}
        for row in reversed(rows):
            guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else row
            if not isinstance(guidance, dict):
                continue
            if guidance.get("ok") is False or not _truthy(guidance.get("usable", True)):
                continue
            confidence = _num(guidance.get("confidence", 1.0))
            if confidence < threshold:
                continue
            if not _has_generator_bias(guidance):
                continue
            guidance = ensure_assistant_guidance_digest(guidance)
            digest = str(row.get("guidance_digest") or guidance.get("guidance_digest") or "")
            guidance["guidance_digest"] = digest or guidance.get("guidance_digest")
            historical_outcome = outcomes_by_guidance.get(str(guidance.get("guidance_digest") or ""), {})
            historical_outcome_status = _guidance_outcome_status(historical_outcome)
            if historical_outcome_status == "weak":
                weak_rejection = {
                    "guidance_digest": guidance.get("guidance_digest", ""),
                    "historical_outcome": historical_outcome,
                    "historical_outcome_status": historical_outcome_status,
                }
                continue
            return {
                **guidance,
                "guidance_digest": guidance.get("guidance_digest"),
                "persisted_at": row.get("timestamp") or row.get("persisted_at") or "",
                "persistence_source": row.get("source") or "assistant_guidance_jsonl",
                "min_confidence": max(threshold, _num(guidance.get("min_confidence", 0.0))),
                "historical_outcome": historical_outcome,
                "historical_outcome_status": historical_outcome_status,
            }
        return {
            "ok": True,
            "schema_version": "assistant_generation_guidance.v1",
            "source": "assistant_guidance_jsonl",
            "usable": False,
            "reason": "weak_historical_guidance_outcome" if weak_rejection else "no_persisted_usable_guidance",
            "confidence": 0.0,
            "min_confidence": threshold,
            "sample_size": 0,
            "top_fields": [],
            "top_operators": [],
            "preferred_windows": [],
            "field_combinations": [],
            **weak_rejection,
        }

    def write_summary(self, path: str | Path | None = None, *, limit: int = 5000, top_n: int = 10) -> Path:
        target = Path(path) if path else self.storage_dir / "research_memory_summary.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.summary(limit=limit, top_n=top_n)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        return target

    def _load_candidate_records(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self._load_jsonl("candidates.jsonl", limit=limit)
        if rows:
            return rows
        latest = self.storage_dir / "run_history" / "latest.json"
        if not latest.is_file():
            return []
        try:
            payload = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [row for row in payload.get("candidates", []) if isinstance(row, dict)][-limit:]

    def _load_jsonl(self, filename: str, *, limit: int) -> list[dict[str, Any]]:
        return read_jsonl_tail(self.storage_dir / filename, limit=limit)


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
