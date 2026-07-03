"""LLM-ready context packs — helper utilities.

Storage access (``_latest_result_from_storage``, ``_cloud_snapshot_from_storage``,
``_read_jsonl``), row brief builders (``_candidate_brief``, ``_backtest_brief``,
``_cloud_alpha_brief``, etc.), join/format helpers, and primitive value
converters.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research._market_data_helpers import _float_value, _int_value


def _latest_result_from_storage(storage_dir: str) -> dict[str, Any]:
    latest_path = Path(storage_dir) / "run_history" / "latest.json"
    if not latest_path.is_file():
        return {"ok": True, "source": "empty", "status": "idle", "result": None, "progress": {}}
    try:
        data = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        from brain_alpha_ops.redaction import redact_error_message
        return {"ok": False, "source": "run_history", "error": redact_error_message(exc), "result": None, "progress": {}}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "ok": True,
        "source": "run_history",
        "job_id": str(data.get("run_id") or latest_path.stem),
        "status": data.get("status") or "completed",
        "result": {
            "summary": summary,
            "candidates": summary.get("candidates") or data.get("candidates") or [],
        },
        "progress": {"phase": data.get("status") or "completed", "data": summary},
    }

def _cloud_snapshot_from_storage(storage_dir: str, *, top_n: int) -> dict[str, Any]:
    rows = _read_jsonl(Path(storage_dir) / "cloud_alphas.jsonl", limit=None)
    latest_by_id: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for row in rows:
        alpha_id = str(row.get("id") or row.get("alpha_id") or "")
        if alpha_id:
            latest_by_id[alpha_id] = row
        else:
            anonymous.append(row)
    deduped = list(latest_by_id.values()) + anonymous
    summary = {
        "source": "storage" if deduped else "empty",
        "count": len(deduped),
        "submitted_count": sum(1 for row in deduped if str(row.get("status", "")).upper() in {"SUBMITTED", "ACTIVE", "PRODUCTION", "CONDUCTED"}),
        "passed_unsubmitted_count": sum(1 for row in deduped if _cloud_pass_fail(row) == "PASS" and str(row.get("status", "")).upper() not in {"SUBMITTED", "ACTIVE", "PRODUCTION", "CONDUCTED"}),
        "failed_unsubmitted_count": sum(1 for row in deduped if _cloud_pass_fail(row) == "FAIL"),
        "is_stale": False,
    }
    return {"alphas": deduped[:top_n], "summary": summary}

def _read_jsonl(path: Path, *, limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        from brain_alpha_ops.jsonl import read_jsonl_records

        return read_jsonl_records(path, limit=None, max_rows=None)
    return read_jsonl_tail(path, limit=limit)

def _candidate_brief(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _first_dict(row.get("official_metrics"), row.get("metrics"))
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return {
        "alpha_id": row.get("alpha_id") or row.get("id") or "",
        "official_alpha_id": row.get("official_alpha_id") or "",
        "family": row.get("family") or "",
        "hypothesis": row.get("hypothesis") or "",
        "expression": _expression_from_row(row),
        "fields": list(row.get("data_fields") or []),
        "operators": list(row.get("operators") or []),
        "score": scorecard.get("total_score", row.get("smart_rank_score", row.get("score", 0))),
        "lifecycle_status": row.get("lifecycle_status") or gate.get("status") or row.get("status") or "",
        "metrics": {
            key: metrics.get(key)
            for key in ("sharpe", "fitness", "turnover", "returns", "drawdown", "correlation", "pass_fail")
            if key in metrics
        },
    }

def _backtest_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": row.get("slot", ""),
        "alpha_id": row.get("alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "status": row.get("status", ""),
        "message": row.get("message", ""),
        "next_poll_seconds": row.get("next_poll_seconds"),
    }

def _backtest_record_brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": row.get("action", ""),
        "slot": row.get("slot", ""),
        "alpha_id": row.get("alpha_id", ""),
        "simulation_id": row.get("simulation_id", ""),
        "status": row.get("status", ""),
        "lifecycle_status": row.get("lifecycle_status", ""),
        "score": row.get("score", 0.0),
        "poll_count": row.get("poll_count", 0),
        "expression_fingerprint": row.get("expression_fingerprint", ""),
        "note": row.get("note", ""),
    }

def _cloud_alpha_brief(row: dict[str, Any]) -> dict[str, Any]:
    metrics = _first_dict(row.get("metrics"), row.get("is"))
    return {
        "alpha_id": row.get("id") or row.get("alpha_id") or "",
        "status": row.get("status", ""),
        "expression": _expression_from_row(row),
        "pass_fail": metrics.get("pass_fail") or row.get("pass_fail") or "",
        "sharpe": metrics.get("sharpe", row.get("sharpe")),
        "fitness": metrics.get("fitness", row.get("fitness")),
        "turnover": metrics.get("turnover", row.get("turnover")),
    }

def _expression_from_row(row: dict[str, Any]) -> str:
    expression = row.get("expression")
    if isinstance(expression, dict):
        return str(expression.get("code") or "")
    if expression:
        return str(expression)
    regular = row.get("regular") if isinstance(row.get("regular"), dict) else {}
    return str(regular.get("code") or "")

def _cloud_pass_fail(row: dict[str, Any]) -> str:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return str(metrics.get("pass_fail") or row.get("pass_fail") or "").upper()

def _join_candidate_briefs(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    parts = []
    for row in rows[:5]:
        parts.append(f"{row.get('alpha_id') or '-'} score={row.get('score', '-')} {row.get('family') or ''}".strip())
    return "; ".join(parts)

def _join_field_combinations(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    return "; ".join("+".join(row.get("fields") or []) for row in rows[:5])

def _join_failures(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    return "; ".join(f"{row.get('reason', '-') } x{row.get('count', 0)}" for row in rows[:5])

def _join_stat_bucket(row: dict[str, Any]) -> str:
    count = _int_value(row.get("count"))
    if not count:
        return "-"
    return (
        f"count={count} success={_float_value(row.get('success_rate'))} "
        f"avg_score={_float_value(row.get('avg_score'))}"
    )

def _join_guidance_outcomes(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    parts = []
    for row in rows[:5]:
        parts.append(
            f"{row.get('guidance_digest') or '-'} count={row.get('count', 0)} "
            f"success={row.get('success_rate', 0)} avg_score={row.get('avg_score', 0)}"
        )
    return "; ".join(parts)

def _join_duplicate_expressions(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "-"
    parts = []
    for row in rows[:3]:
        expression = str(row.get("expression_canonical") or "")[:80]
        parts.append(f"{row.get('count', 0)}x {expression or row.get('expression_fingerprint', '-')}")
    return "; ".join(parts)

def _join_text_items(rows: list[Any]) -> str:
    items = [str(item).strip() for item in rows[:5] if str(item).strip()]
    return "; ".join(items) if items else "-"

def _unique_text_items(rows: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in rows:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique

def _guidance_outcomes(summary: dict[str, Any], *, top_n: int) -> list[dict[str, Any]]:
    rows = summary.get("assistant_guidance_outcomes") if isinstance(summary, dict) else []
    if not isinstance(rows, list):
        return []
    outcomes: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        digest = str(row.get("guidance_digest") or "").strip()
        if not digest:
            continue
        pass_fail = row.get("pass_fail") if isinstance(row.get("pass_fail"), dict) else {}
        outcomes.append({
            "guidance_digest": digest,
            "count": _int_value(row.get("count")),
            "success_count": _int_value(row.get("success_count")),
            "success_rate": _float_value(row.get("success_rate")),
            "avg_score": _float_value(row.get("avg_score")),
            "avg_sharpe": _float_value(row.get("avg_sharpe")),
            "avg_fitness": _float_value(row.get("avg_fitness")),
            "pass_fail": dict(pass_fail),
        })
    return outcomes[:top_n]

def _strong_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        if _int_value(row.get("count")) <= 0:
            continue
        if _float_value(row.get("success_rate")) >= 0.5 or _float_value(row.get("avg_score")) >= 70:
            return row
    return {}

def _weak_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        count = _int_value(row.get("count"))
        if count <= 0:
            continue
        success_rate = _float_value(row.get("success_rate"))
        avg_score = _float_value(row.get("avg_score"))
        if (count >= 2 and success_rate <= 0.25) or (success_rate == 0.0 and avg_score <= 50):
            return row
    return {}

def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}

def _first_list(*values: Any) -> list[dict[str, Any]]:
    for value in values:
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []

def _dataclass_dict(value: Any) -> dict[str, Any]:
    from dataclasses import asdict, is_dataclass
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {}
