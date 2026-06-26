"""Expression/feature bucket aggregation helpers for the expression index.

Re-exported via ``brain_alpha_ops.research.expression_index``.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.research.expression_index._helpers import (
    _append_unique,
    _compact_record,
    _score_for,
    _text,
)


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
