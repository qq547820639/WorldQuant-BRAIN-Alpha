"""Low-level scalar/record helpers for the expression history index.

Re-exported via ``brain_alpha_ops.research.expression_index``.
"""
from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
