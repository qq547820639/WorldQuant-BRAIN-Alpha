"""Expression history index built from append-only research JSONL files."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.expression_ast import expression_profile_summary, expression_similarity


DEFAULT_SOURCES = {
    "candidates.jsonl": "candidate",
    "lifecycle.jsonl": "lifecycle",
    "checks.jsonl": "check",
    "backtests.jsonl": "backtest",
    "submissions.jsonl": "submission",
    "cloud_alphas.jsonl": "cloud_alpha",
}


class ExpressionHistoryIndex:
    def __init__(self, storage_dir: str | Path = "data"):
        self.storage_dir = Path(storage_dir)

    def summary(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_cloud: bool = True,
        source_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if source_rows is None:
            sqlite_summary = self._sqlite_summary(top_n=top_n)
            if sqlite_summary.get("ok"):
                return _compat_summary_schema(sqlite_summary)
        rows = self.records(limit=limit, include_cloud=include_cloud, source_rows=source_rows)
        buckets: dict[str, dict[str, Any]] = {}
        field_buckets: dict[str, dict[str, Any]] = defaultdict(_feature_bucket)
        operator_buckets: dict[str, dict[str, Any]] = defaultdict(_feature_bucket)
        window_buckets: dict[int, dict[str, Any]] = defaultdict(_feature_bucket)
        source_counts: Counter[str] = Counter()

        for row in rows:
            fingerprint = str(row.get("expression_fingerprint") or "")
            if not fingerprint:
                continue
            source = str(row.get("source") or "")
            source_counts[source] += 1
            bucket = buckets.setdefault(fingerprint, _expression_bucket(row))
            _update_expression_bucket(bucket, row)
            profile = row.get("expression_profile") if isinstance(row.get("expression_profile"), dict) else {}
            for field in _as_text_list(profile.get("fields")):
                _update_feature_bucket(field_buckets[field], fingerprint, source)
            for operator in _as_text_list(profile.get("operators")):
                _update_feature_bucket(operator_buckets[operator], fingerprint, source)
            for window in _as_int_list(profile.get("windows")):
                _update_feature_bucket(window_buckets[window], fingerprint, source)

        duplicate_rows = [
            _finalize_expression_bucket(bucket)
            for bucket in buckets.values()
            if int(bucket.get("count") or 0) > 1
        ]
        duplicate_rows.sort(key=lambda item: (item["count"], item["source_count"], item["max_score"]), reverse=True)

        frequent_rows = [_finalize_expression_bucket(bucket) for bucket in buckets.values()]
        frequent_rows.sort(key=lambda item: (item["count"], item["max_score"], item["latest_timestamp"]), reverse=True)

        return {
            "ok": True,
            "schema_version": "expression-index.v1",
            "source": "local_jsonl_expression_index",
            "storage_dir": str(self.storage_dir),
            "total_expression_records": len(rows),
            "unique_expression_count": len(buckets),
            "duplicate_expression_count": len(duplicate_rows),
            "source_counts": dict(source_counts.most_common()),
            "duplicates": duplicate_rows[:top_n],
            "frequent_expressions": frequent_rows[:top_n],
            "fields": _rank_feature_buckets(field_buckets, top_n),
            "operators": _rank_feature_buckets(operator_buckets, top_n),
            "windows": _rank_window_buckets(window_buckets, top_n),
        }

    def lookup(
        self,
        expression: str,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_cloud: bool = True,
        min_similarity: float = 0.75,
        source_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if source_rows is None:
            sqlite_lookup = self._sqlite_lookup(expression, top_n=top_n, min_similarity=min_similarity)
            if sqlite_lookup.get("ok"):
                return _compat_lookup_schema(sqlite_lookup)
        target = expression_profile_summary(expression)
        target_fingerprint = str(target.get("expression_fingerprint") or "")
        rows = self.records(limit=limit, include_cloud=include_cloud, source_rows=source_rows)
        exact = [
            _compact_record(row)
            for row in rows
            if str(row.get("expression_fingerprint") or "") == target_fingerprint
        ]
        similar: list[dict[str, Any]] = []
        if not exact:
            for row in rows:
                score = expression_similarity(
                    str(target.get("expression_canonical") or expression),
                    str(row.get("expression_canonical") or row.get("expression") or ""),
                )
                if score >= min_similarity:
                    similar.append({**_compact_record(row), "similarity": score})
            similar.sort(key=lambda item: item.get("similarity", 0.0), reverse=True)
        return {
            "ok": True,
            "schema_version": "expression-index.lookup.v1",
            "expression": expression,
            **target,
            "exact_match": bool(exact),
            "exact_count": len(exact),
            "exact_records": exact[:top_n],
            "similar_count": len(similar),
            "similar_records": similar[:top_n],
            "min_similarity": min_similarity,
        }

    def _sqlite_summary(self, *, top_n: int) -> dict[str, Any]:
        db_path = self.storage_dir / "expression_index.sqlite"
        if not db_path.is_file():
            return {}
        try:
            from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex

            return ExpressionSqliteIndex(self.storage_dir).summary(top_n=top_n)
        except Exception:
            return {}

    def _sqlite_lookup(self, expression: str, *, top_n: int, min_similarity: float) -> dict[str, Any]:
        db_path = self.storage_dir / "expression_index.sqlite"
        if not db_path.is_file():
            return {}
        try:
            from brain_alpha_ops.research.expression_sqlite_index import ExpressionSqliteIndex

            return ExpressionSqliteIndex(self.storage_dir).lookup(
                expression,
                top_n=top_n,
                min_similarity=min_similarity,
            )
        except Exception:
            return {}

    def records(
        self,
        *,
        limit: int = 5000,
        include_cloud: bool = True,
        source_rows: dict[str, list[dict[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sources = dict(DEFAULT_SOURCES)
        if not include_cloud:
            sources.pop("cloud_alphas.jsonl", None)
        for filename, source in sources.items():
            records = _source_records_for(filename, source_rows, self.storage_dir, limit=limit)
            for index, record in enumerate(records):
                expression = _expression_from_record(record)
                if not expression:
                    continue
                summary = _summary_from_record(record, expression)
                rows.append({
                    "source": source,
                    "source_file": filename,
                    "record_index": index,
                    "alpha_id": _text(record.get("alpha_id") or record.get("id") or _nested(record, "candidate", "alpha_id")),
                    "official_alpha_id": _text(record.get("official_alpha_id") or _nested(record, "candidate", "official_alpha_id")),
                    "simulation_id": _text(record.get("simulation_id") or _nested(record, "candidate", "simulation_id")),
                    "stage": _text(record.get("stage")),
                    "status": _status_for(record),
                    "family": _text(record.get("family") or _nested(record, "candidate", "family")),
                    "score": _score_for(record),
                    "timestamp": _text(record.get("timestamp") or record.get("created_at") or record.get("synced_at")),
                    "expression": expression,
                    **summary,
                })
        return rows[-max(1, int(limit or 1)):]


def _load_jsonl(path: Path, *, limit: int) -> list[dict[str, Any]]:
    return read_jsonl_tail(path, limit=limit)


def _compat_summary_schema(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "schema_version": "expression-index.v1",
        "source": "sqlite_expression_index",
        "cache_schema_version": payload.get("schema_version", ""),
    }


def _compat_lookup_schema(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "schema_version": "expression-index.lookup.v1",
        "source": "sqlite_expression_index",
        "cache_schema_version": payload.get("schema_version", ""),
    }


def _source_records_for(
    filename: str,
    source_rows: dict[str, list[dict[str, Any]]] | None,
    storage_dir: Path,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if isinstance(source_rows, dict) and filename in source_rows:
        rows = source_rows.get(filename) or []
        safe_limit = max(1, int(limit or 1))
        return [row for row in rows[-safe_limit:] if isinstance(row, dict)]
    return _load_jsonl(storage_dir / filename, limit=limit)


def _expression_from_record(record: dict[str, Any]) -> str:
    expression = record.get("expression")
    if isinstance(expression, dict):
        code = expression.get("code") or expression.get("regular")
        if code:
            return _text(code)
    if expression:
        return _text(expression)

    candidate = record.get("candidate")
    if isinstance(candidate, dict):
        nested = _expression_from_record(candidate)
        if nested:
            return nested

    regular = record.get("regular")
    if isinstance(regular, dict) and regular.get("code"):
        return _text(regular.get("code"))

    raw = record.get("raw")
    if isinstance(raw, dict):
        raw_regular = raw.get("regular")
        if isinstance(raw_regular, dict) and raw_regular.get("code"):
            return _text(raw_regular.get("code"))

    return _text(record.get("expression_canonical"))


def _summary_from_record(record: dict[str, Any], expression: str) -> dict[str, Any]:
    fingerprint = _text(record.get("expression_fingerprint"))
    canonical = _text(record.get("expression_canonical"))
    profile = record.get("expression_profile") if isinstance(record.get("expression_profile"), dict) else {}
    if fingerprint and canonical and profile:
        return {
            "expression_canonical": canonical,
            "expression_fingerprint": fingerprint,
            "expression_profile": profile,
        }
    return expression_profile_summary(expression)


def _expression_bucket(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "expression_fingerprint": row.get("expression_fingerprint", ""),
        "expression_canonical": row.get("expression_canonical", ""),
        "expression_profile": row.get("expression_profile", {}),
        "count": 0,
        "sources": Counter(),
        "statuses": Counter(),
        "families": Counter(),
        "alpha_ids": [],
        "official_alpha_ids": [],
        "examples": [],
        "max_score": 0.0,
        "latest_timestamp": "",
    }


def _update_expression_bucket(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["count"] += 1
    bucket["sources"][_text(row.get("source"))] += 1
    if row.get("status"):
        bucket["statuses"][_text(row.get("status"))] += 1
    if row.get("family"):
        bucket["families"][_text(row.get("family"))] += 1
    _append_unique(bucket["alpha_ids"], row.get("alpha_id"))
    _append_unique(bucket["official_alpha_ids"], row.get("official_alpha_id"))
    if len(bucket["examples"]) < 3:
        bucket["examples"].append(_compact_record(row))
    bucket["max_score"] = max(float(bucket.get("max_score") or 0.0), _score_for(row))
    timestamp = _text(row.get("timestamp"))
    if timestamp >= _text(bucket.get("latest_timestamp")):
        bucket["latest_timestamp"] = timestamp


def _finalize_expression_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "expression_fingerprint": bucket.get("expression_fingerprint", ""),
        "expression_canonical": bucket.get("expression_canonical", ""),
        "count": int(bucket.get("count") or 0),
        "source_count": len(bucket.get("sources") or {}),
        "sources": dict((bucket.get("sources") or Counter()).most_common()),
        "statuses": dict((bucket.get("statuses") or Counter()).most_common()),
        "families": dict((bucket.get("families") or Counter()).most_common()),
        "alpha_ids": list(bucket.get("alpha_ids") or [])[:10],
        "official_alpha_ids": list(bucket.get("official_alpha_ids") or [])[:10],
        "max_score": round(float(bucket.get("max_score") or 0.0), 3),
        "latest_timestamp": _text(bucket.get("latest_timestamp")),
        "expression_profile": bucket.get("expression_profile", {}),
        "examples": list(bucket.get("examples") or []),
    }


def _feature_bucket() -> dict[str, Any]:
    return {"count": 0, "fingerprints": set(), "sources": Counter()}


def _update_feature_bucket(bucket: dict[str, Any], fingerprint: str, source: str) -> None:
    bucket["count"] += 1
    bucket["fingerprints"].add(fingerprint)
    bucket["sources"][source] += 1


def _rank_feature_buckets(buckets: dict[str, dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    rows = [
        {
            "name": name,
            "count": int(bucket.get("count") or 0),
            "unique_expression_count": len(bucket.get("fingerprints") or set()),
            "sources": dict((bucket.get("sources") or Counter()).most_common()),
        }
        for name, bucket in buckets.items()
    ]
    rows.sort(key=lambda item: (-item["unique_expression_count"], -item["count"], item["name"]))
    return rows[:top_n]


def _rank_window_buckets(buckets: dict[int, dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    rows = [
        {
            "window": window,
            "count": int(bucket.get("count") or 0),
            "unique_expression_count": len(bucket.get("fingerprints") or set()),
            "sources": dict((bucket.get("sources") or Counter()).most_common()),
        }
        for window, bucket in buckets.items()
    ]
    rows.sort(key=lambda item: (item["unique_expression_count"], item["count"], item["window"]), reverse=True)
    return rows[:top_n]


def _compact_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": row.get("source", ""),
        "alpha_id": row.get("alpha_id", ""),
        "official_alpha_id": row.get("official_alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "stage": row.get("stage", ""),
        "status": row.get("status", ""),
        "family": row.get("family", ""),
        "score": row.get("score", 0.0),
        "timestamp": row.get("timestamp", ""),
        "expression": row.get("expression", ""),
        "expression_canonical": row.get("expression_canonical", ""),
        "expression_fingerprint": row.get("expression_fingerprint", ""),
    }


def _status_for(record: dict[str, Any]) -> str:
    metrics = record.get("official_metrics") if isinstance(record.get("official_metrics"), dict) else {}
    nested_metrics = _nested(record, "candidate", "official_metrics")
    if not isinstance(nested_metrics, dict):
        nested_metrics = {}
    return _text(
        record.get("lifecycle_status")
        or record.get("status")
        or metrics.get("pass_fail")
        or nested_metrics.get("pass_fail")
    )


def _score_for(record: dict[str, Any]) -> float:
    scorecard = record.get("scorecard") if isinstance(record.get("scorecard"), dict) else {}
    nested_scorecard = _nested(record, "candidate", "scorecard")
    if isinstance(nested_scorecard, dict) and not scorecard:
        scorecard = nested_scorecard
    return _num(scorecard.get("total_score", record.get("score", 0.0)))


def _nested(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return ""
        value = value.get(key)
    return value


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _as_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    rows: list[int] = []
    for item in value:
        try:
            rows.append(int(float(item)))
        except (TypeError, ValueError):
            continue
    return rows


def _append_unique(rows: list[str], value: Any) -> None:
    text = _text(value)
    if text and text not in rows:
        rows.append(text)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
