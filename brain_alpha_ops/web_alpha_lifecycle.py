"""Read-only Alpha lifecycle replay payloads for the Web console."""

from __future__ import annotations

from collections import Counter, OrderedDict
from hashlib import sha256
import re
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_data, redact_text
from brain_alpha_ops.web_runtime_state import status_category


SCHEMA_VERSION = "alpha_lifecycle_history.v1"
DEFAULT_LIMIT = 250
MAX_LIMIT = 2000

ReadStorageJsonl = Callable[..., list[dict[str, Any]]]

_SENSITIVE_NOTE_LABEL_RE = re.compile(
    r"(?i)\b(?:access[-_]?token|api[-_]?key|auth[-_]?token|authorization|cookie|csrf(?:[-_]?token)?|"
    r"email|passwd|password|secret|session(?:[-_](?:id|token))?|token|username)"
    r"\s*[:=]\s*(?:<redacted>|\"[^\"]*\"|'[^']*'|[^,\s;}\]]+)"
)


def alpha_lifecycle_history_payload(
    *,
    read_storage_jsonl: ReadStorageJsonl,
    alpha_id: str = "",
    query: str = "",
    stage: str = "",
    status: str = "",
    status_category_filter: str = "",
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Return a filterable, redacted replay view over persisted lifecycle rows.

    This is intentionally local-only: it reads the existing append-only lifecycle
    ledger and never calls BRAIN APIs or submission helpers.
    """
    safe_limit = _safe_limit(limit)
    filters = {
        "alpha_id": _clean_filter(alpha_id),
        "query": _clean_filter(query),
        "stage": _clean_filter(stage).lower(),
        "status": _clean_filter(status).upper(),
        "status_category": _clean_filter(status_category_filter).lower(),
        "limit": safe_limit,
    }
    rows = [
        _normalize_lifecycle_row(row)
        for row in read_storage_jsonl("lifecycle.jsonl", limit=None)
        if isinstance(row, dict)
    ]
    matching_records = [row for row in rows if _matches_filters(row, filters)]
    records = matching_records[-safe_limit:]
    complete = len(records) == len(matching_records)
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "source": "lifecycle_jsonl",
        "official_api_called": False,
        "submit_allowed": False,
        "filters": filters,
        "records": records,
        "items": records,
        "count": len(records),
        "returned_count": len(records),
        "total_count": len(matching_records),
        "total": len(matching_records),
        "complete": complete,
        "truncated": not complete,
        "display_limit": safe_limit,
        "summary": _summary(records),
        "alpha_traces": _alpha_traces(records),
    }


def _normalize_lifecycle_row(row: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_data(row)
    if not isinstance(redacted, dict):
        redacted = {}
    status_text = _text(redacted.get("status") or redacted.get("lifecycle_status"))
    stage = _text(redacted.get("stage") or redacted.get("action"))
    alpha_id = _text(redacted.get("alpha_id"))
    official_alpha_id = _text(redacted.get("official_alpha_id"))
    simulation_id = _text(redacted.get("simulation_id"))
    expression = _text(redacted.get("expression"), max_length=320)
    safe = {
        "schema_version": _text(redacted.get("schema_version") or "lifecycle_record.v1"),
        "timestamp": _text(redacted.get("timestamp")),
        "run_id": _text(redacted.get("run_id")),
        "alpha_id": alpha_id,
        "official_alpha_id": official_alpha_id,
        "simulation_id": simulation_id,
        "stage": stage,
        "status": status_text,
        "status_category": status_category({**redacted, "stage": stage, "status": status_text}),
        "expression": expression,
        "expression_digest": _digest(expression),
        "note": _public_note(redacted.get("note") or redacted.get("message") or redacted.get("reason"), max_length=240),
        "correlation_id": _text(redacted.get("correlation_id")),
        "source": "lifecycle_jsonl",
    }
    for key in ("decision_action", "decision_band", "lifecycle_status", "family", "dataset_id"):
        value = _text(redacted.get(key), max_length=120)
        if value:
            safe[key] = value
    score = _number(redacted.get("score") or redacted.get("total_score"))
    if score is not None:
        safe["score"] = score
    return safe


def _matches_filters(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    alpha_filter = str(filters.get("alpha_id") or "")
    if alpha_filter and alpha_filter not in _row_identity_values(row):
        return False
    stage_filter = str(filters.get("stage") or "")
    if stage_filter and stage_filter not in str(row.get("stage") or "").lower():
        return False
    status_filter = str(filters.get("status") or "")
    if status_filter and status_filter not in str(row.get("status") or "").upper():
        return False
    category_filter = str(filters.get("status_category") or "")
    if category_filter and category_filter != str(row.get("status_category") or "").lower():
        return False
    query = str(filters.get("query") or "").lower()
    if query and query not in _search_blob(row):
        return False
    return True


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage = Counter(str(row.get("stage") or "unknown") or "unknown" for row in records)
    by_category = Counter(str(row.get("status_category") or "other") or "other" for row in records)
    alpha_ids = {_trace_key(row) for row in records if _trace_key(row) != "unknown"}
    latest = max((str(row.get("timestamp") or "") for row in records), default="")
    return {
        "record_count": len(records),
        "alpha_count": len(alpha_ids),
        "latest_event_at": latest,
        "by_stage": dict(sorted(by_stage.items())),
        "by_status_category": dict(sorted(by_category.items())),
        "blocked_count": by_category.get("blocked", 0),
        "failed_count": by_category.get("failed", 0),
        "passed_count": by_category.get("passed", 0),
        "submitted_count": by_category.get("submitted", 0),
        "replay_ready": bool(records),
    }


def _alpha_traces(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in records:
        key = _trace_key(row)
        grouped.setdefault(key, []).append(row)
    traces = []
    for key, rows in grouped.items():
        latest = rows[-1]
        categories = [str(row.get("status_category") or "other") for row in rows]
        traces.append({
            "trace_key": key,
            "alpha_id": _text(latest.get("alpha_id")),
            "official_alpha_id": _text(latest.get("official_alpha_id")),
            "simulation_id": _text(latest.get("simulation_id")),
            "expression_digest": _text(latest.get("expression_digest")),
            "latest_stage": _text(latest.get("stage")),
            "latest_status": _text(latest.get("status")),
            "status_category": _text(latest.get("status_category") or "other"),
            "event_count": len(rows),
            "first_event_at": _text(rows[0].get("timestamp")),
            "latest_event_at": _text(latest.get("timestamp")),
            "stages": _unique_text(row.get("stage") for row in rows),
            "blocked": "blocked" in categories,
            "failed": "failed" in categories,
            "passed": "passed" in categories,
            "submitted": "submitted" in categories,
            "last_note": _text(latest.get("note"), max_length=180),
            "next_action": _next_action(categories, latest),
        })
    return sorted(traces, key=lambda item: str(item.get("latest_event_at") or ""), reverse=True)


def _row_identity_values(row: dict[str, Any]) -> list[str]:
    return [
        _text(row.get("alpha_id")),
        _text(row.get("official_alpha_id")),
        _text(row.get("simulation_id")),
    ]


def _trace_key(row: dict[str, Any]) -> str:
    for value in _row_identity_values(row):
        if value:
            return value
    digest = _text(row.get("expression_digest"))
    return digest or "unknown"


def _search_blob(row: dict[str, Any]) -> str:
    return " ".join(str(value or "") for value in row.values()).lower()


def _next_action(categories: list[str], latest: dict[str, Any]) -> str:
    latest_category = _text(latest.get("status_category") or "").lower()
    if latest_category == "submitted":
        return "monitor_official_result"
    if latest_category == "blocked":
        return "review_blockers"
    if latest_category == "failed":
        return "optimize_or_archive"
    if latest_category == "passed" and not _text(latest.get("official_alpha_id")):
        return "collect_official_identity"
    return "continue_validation"


def _safe_limit(value: Any) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = DEFAULT_LIMIT
    return min(MAX_LIMIT, max(1, parsed))


def _clean_filter(value: Any) -> str:
    text = redact_text(value, max_length=200).strip()
    return _SENSITIVE_NOTE_LABEL_RE.sub("sensitive detail redacted", text).strip()


def _text(value: Any, *, max_length: int = 240) -> str:
    return redact_text(value, max_length=max_length).strip()


def _public_note(value: Any, *, max_length: int = 240) -> str:
    text = _text(value, max_length=max_length)
    return _SENSITIVE_NOTE_LABEL_RE.sub("sensitive detail redacted", text)


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _digest(value: str) -> str:
    if not value:
        return ""
    return "expr_" + sha256(value.encode("utf-8")).hexdigest()[:12]


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value, max_length=120)
        if text and text not in result:
            result.append(text)
    return result
