"""Error-row extraction for research observability snapshots."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.errors import classify_error
from brain_alpha_ops.redaction import redact_text


def observability_error_rows(
    backtest_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
    check_rows: list[dict[str, Any]],
    job_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, items in (
        ("backtests", backtest_rows),
        ("lifecycle", lifecycle_rows),
        ("checks", check_rows),
        ("jobs", job_rows),
    ):
        for row in items:
            error = error_from_observability_row(row)
            if error:
                error_source = _text(row.get("source")) if source == "jobs" else source
                rows.append({"source": error_source or source, **error})
    return rows


def error_from_observability_row(row: dict[str, Any]) -> dict[str, Any] | None:
    contexts: list[dict[str, Any]] = []
    for key in ("error_context", "error"):
        value = row.get(key)
        if isinstance(value, dict):
            contexts.append(value)
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    value = progress.get("error_context")
    if isinstance(value, dict):
        contexts.append(value)
    for context in contexts:
        payload = {
            **context,
            "alpha_id": row.get("alpha_id") or context.get("alpha_id") or "",
            "timestamp": row.get("timestamp") or row.get("updated_at") or row.get("checked_at") or "",
        }
        payload["message"] = payload.get("error") or payload.get("message") or row.get("note") or ""
        return payload

    message = _text(row.get("error") or row.get("failure_reason"))
    status_text = " ".join(
        _text(row.get(key))
        for key in ("status", "stage", "action", "lifecycle_status", "note")
        if row.get(key) is not None
    )
    if not message and not _looks_failed_status(status_text):
        return None
    info = classify_error(RuntimeError(message or status_text or "recorded failure"), default_code=_default_error_code(row))
    payload = info.to_dict()
    payload.update({
        "alpha_id": row.get("alpha_id", ""),
        "timestamp": row.get("timestamp") or row.get("updated_at") or row.get("checked_at") or "",
        "message": payload.get("error", ""),
    })
    return payload


def _default_error_code(row: dict[str, Any]) -> str:
    text = f"{row.get('action', '')} {row.get('stage', '')} {row.get('status', '')}".upper()
    if "CHECK" in text:
        return "CHECK_ERROR"
    if "SUBMIT" in text:
        return "SUBMIT_ERROR"
    if "SIMULATION" in text or "BACKTEST" in text:
        return "BACKTEST_ERROR"
    return "RECORDED_ERROR"


def _looks_failed_status(text: str) -> bool:
    upper = text.upper()
    return any(token in upper for token in ("FAIL", "ERROR", "EXCEPTION", "BLOCKED", "TIMEOUT"))


def _text(value: Any) -> str:
    return str(value or "").strip()
