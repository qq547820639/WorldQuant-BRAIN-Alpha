"""Read-only Alpha lifecycle replay payloads, simulation job store adapter,
and progress presentation helpers for the local web console.

Consolidated from the former ``web_alpha_lifecycle.py`` (lifecycle history
payload), ``web_simulation_job.py`` (SimJobStore adapter factory), and
``web_progress.py`` (progress normalization/enrichment). All three modules
serve the web console's job/lifecycle/progress surface: the lifecycle
payload exposes a filterable, redacted replay view over persisted lifecycle
rows; ``create_sim_job_store`` bridges ``simulate_candidates_job`` to a job
store; and the progress helpers normalize/enrich polling and SSE progress
payloads.
"""

from __future__ import annotations

import re
from collections import Counter, OrderedDict
from hashlib import sha256
from typing import Any, Callable, Protocol, TypedDict

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


# ═══════════════════════ Lifecycle history payload ════════════════════
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


# ═══════════════════════ SimJobStore adapter ═══════════════════════════
class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None: ...
    def is_cancelled(self, job_id: str) -> bool: ...


def create_sim_job_store(store: Any | None = None) -> JobStoreLike:
    """Create a SimJobStore adapter bridging simulate_candidates_job to a job store.

    Args:
        store: A store object with .update(jid, **kw) and .get(jid) methods
               (used by web_handler_dispatch.py), or None to use the
               web_jobs module-level functions (used by web_routes.py).

    Returns:
        An adapter implementing update(job_id, **kw) and is_cancelled(job_id).
    """
    if store is not None:
        class _StoreAdapter:
            def update(self, jid: str, **kw: Any) -> None:
                store.update(jid, **kw)

            def is_cancelled(self, jid: str) -> bool:
                checker = getattr(store, "is_cancelled", None)
                if callable(checker) and checker(jid):
                    return True
                row = store.get(jid) or {}
                if bool(row.get("cancel")):
                    return True
                return str(row.get("status", "")).lower() in ("cancelled", "canceled", "stopped")

        return _StoreAdapter()

    class _WebJobsAdapter:
        def update(self, job_id: str, **kwargs: Any) -> None:
            from brain_alpha_ops.web_jobs import job_update
            job_update(job_id, **kwargs)

        def is_cancelled(self, job_id: str) -> bool:
            from brain_alpha_ops.web_jobs import is_cancelled
            return is_cancelled(job_id)

    return _WebJobsAdapter()


# ═══════════════════════ Progress presentation ═════════════════════════
class ProgressPayload(TypedDict, total=False):
    """Public progress contract shared by polling, SSE, and UI rendering."""

    task_id: str
    job_id: str
    status: str
    phase: str
    phase_label: str
    percent: float
    percent_complete: float
    status_message: str
    message: str
    eta_seconds: int
    total: int | float
    done: int | float
    scanned: int | float
    checked: int | float
    submitted: int | float
    current: int | float
    total_steps: int | float
    indeterminate: bool
    open_ended: bool


PHASE_LABELS: dict[str, str] = {
    "queued": "排队",
    "auth": "认证",
    "scan": "扫描",
    "merge": "合并",
    "startup": "启动",
    "cloud_sync": "云端数据同步",
    "context": "加载上下文",
    "production_loop": "循环生产",
    "candidate_generation": "候选生成",
    "local_scoring": "本地评分排序",
    "scoring": "评分",
    "candidate_pool": "候选池维护",
    "official_validation": "回测前预检",
    "official_simulation": "官方模拟回测",
    "official_deferred": "官方延迟",
    "checking": "批量检查",
    "submitting": "提交",
    "config_load": "配置加载",
    "completed": "已完成",
    "stopped": "已停止",
    "failed": "失败",
    "stopping": "正在停止",
}


def _bounded_percent(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return max(0.0, min(100.0, parsed))


def _ratio_percent(progress: dict[str, Any]) -> float | None:
    if _is_context_stage_progress(progress):
        return _context_stage_percent(progress)
    total = progress.get("total")
    for done_key in ("done", "scanned", "checked", "submitted", "current"):
        if done_key not in progress:
            continue
        if done_key == "current" and "total_steps" in progress:
            total = progress.get("total_steps")
        try:
            done_value = float(progress.get(done_key) or 0)
            total_value = float(total or 0)
        except (TypeError, ValueError):
            continue
        if total_value > 0:
            return _bounded_percent(done_value / total_value * 100.0)
    return None


def progress_percent(progress: dict[str, Any]) -> float | None:
    explicit = _bounded_percent(progress.get("percent_complete"))
    if explicit is not None:
        return explicit
    explicit = _bounded_percent(progress.get("percent"))
    if explicit is not None:
        return explicit
    return _ratio_percent(progress)


def _is_cloud_scan_progress(progress: dict[str, Any]) -> bool:
    phase = str(progress.get("phase") or "").lower()
    status_code = str(progress.get("status_code") or "").upper()
    operation = str(progress.get("operation") or "").lower()
    if phase != "scan":
        return False
    if status_code and status_code != "SCAN":
        return False
    return operation in ("", "sync_alphas", "cloud_sync")


_CONTEXT_STAGE_COUNTERS: dict[str, tuple[str, str]] = {
    "CONTEXT_FIELDS": ("fields_count", "fields_total"),
    "CONTEXT_OPERATORS": ("operators_count", "operators_total"),
    "CONTEXT_DATASETS": ("datasets_count", "datasets_total"),
}


def _is_context_stage_progress(progress: dict[str, Any]) -> bool:
    status_code = str(progress.get("status_code") or "").upper()
    return status_code in _CONTEXT_STAGE_COUNTERS


def _context_stage_counts(progress: dict[str, Any]) -> tuple[float, float]:
    status_code = str(progress.get("status_code") or "").upper()
    keys = _CONTEXT_STAGE_COUNTERS.get(status_code)
    if not keys:
        return 0.0, 0.0
    current_key, total_key = keys
    try:
        current = float(progress.get(current_key) or 0)
        total = float(progress.get(total_key) or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    return max(0.0, current), max(0.0, total)


def _context_stage_percent(progress: dict[str, Any]) -> float | None:
    current, total = _context_stage_counts(progress)
    if total <= 0:
        return None
    return _bounded_percent(current / total * 100.0)


def _format_count(value: Any) -> str:
    try:
        numeric = int(float(value or 0))
    except (TypeError, ValueError):
        numeric = 0
    return f"{max(0, numeric):,}"


def _open_ended_scan_message(progress: dict[str, Any]) -> str:
    try:
        scanned = int(float(progress.get("scanned") or 0))
    except (TypeError, ValueError):
        scanned = 0
    try:
        reported_total = int(float(
            progress.get("api_reported_total")
            or progress.get("filter_window_count")
            or 0
        ))
    except (TypeError, ValueError):
        reported_total = 0
    if scanned <= 0:
        return "正在扫描云端 Alpha；等待官方接口返回第一页和接口分页参考数。"
    if reported_total > 0:
        page_detail = _scan_page_detail(progress)
        current_page_detail = _scan_current_page_detail(progress)
        return (
            f"已拉取 {_format_count(scanned)} 条云端 Alpha；"
            f"接口分页参考数 {_format_count(reported_total)} 条，不是云端 Alpha 总量，会继续按分页自动确认边界"
            f"{page_detail}{current_page_detail}。"
        )
    return f"已拉取 {_format_count(scanned)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。"


def _scan_has_filter_window_count(progress: dict[str, Any]) -> bool:
    try:
        return int(float(progress.get("api_reported_total") or progress.get("filter_window_count") or 0)) > 0
    except (TypeError, ValueError):
        return False


def _scan_page_detail(progress: dict[str, Any]) -> str:
    page = _positive_int(progress.get("pages_fetched") or progress.get("page_number"))
    if page:
        return f"；当前第 {_format_count(page)} 页"
    return ""


def _scan_current_page_detail(progress: dict[str, Any]) -> str:
    page_size = _positive_int(progress.get("page_size"))
    page_limit = _positive_int(progress.get("page_limit"))
    next_offset = _positive_int(progress.get("next_offset"))
    filter_window_count = _positive_int(progress.get("api_reported_total") or progress.get("filter_window_count"))
    parts: list[str] = []
    if page_size:
        parts.append(f"本页 {_format_count(page_size)} 条")
    if page_limit:
        parts.append(f"分页参数 {_format_count(page_limit)} 条/页")
    if next_offset:
        if filter_window_count and next_offset >= filter_window_count:
            parts.append("下一请求确认分页边界")
        else:
            parts.append("下一轮继续拉取")
    if progress.get("confirming_total_boundary"):
        parts.append("本页已满，继续确认下一页")
    if progress.get("cursor_before"):
        if str(progress.get("warning") or "") == "transient_page_retry_narrowed_by_date":
            parts.append("网关超时后自动缩小时间范围")
        else:
            parts.append("已自动缩小时间范围")
    return "；" + "，".join(parts) if parts else ""


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def normalize_progress(progress: dict[str, Any], *, task_id: str = "", status: str = "") -> dict[str, Any]:
    normalized = dict(progress or {})
    if task_id:
        normalized.setdefault("task_id", task_id)
        normalized.setdefault("job_id", task_id)
    if status:
        normalized.setdefault("status", status)
    if "phase" in normalized and "phase_label" not in normalized:
        normalized["phase_label"] = PHASE_LABELS.get(str(normalized["phase"]), str(normalized["phase"]))
    open_ended_scan = _is_cloud_scan_progress(normalized)
    if open_ended_scan:
        normalized.pop("eta_deadline_at_ms", None)
        normalized.pop("eta_seconds", None)
        normalized.pop("percent_complete", None)
        normalized.pop("percent", None)
        normalized["indeterminate"] = True
        normalized["open_ended"] = True
        message = _open_ended_scan_message(normalized)
        normalized["status_message"] = message
        normalized["message"] = message
    elif _is_context_stage_progress(normalized):
        normalized.pop("percent_complete", None)
        normalized.pop("percent", None)
        percent = _context_stage_percent(normalized)
        if percent is not None:
            normalized["percent_complete"] = round(percent, 1)
            normalized.setdefault("percent", round(percent, 1))
        else:
            normalized.pop("eta_deadline_at_ms", None)
            normalized.pop("eta_seconds", None)
    else:
        percent = progress_percent(normalized)
        if percent is not None:
            normalized["percent_complete"] = round(percent, 1)
            normalized.setdefault("percent", round(percent, 1))
    message = (
        normalized.get("status_message")
        or normalized.get("message")
        or normalized.get("phase_label")
        or normalized.get("phase")
        or status
    )
    if message:
        normalized["status_message"] = str(message)
        normalized.setdefault("message", str(message))
    try:
        eta_seconds = 0 if open_ended_scan else int(float(normalized.get("eta_seconds") or 0))
    except (TypeError, ValueError):
        eta_seconds = 0
    normalized["eta_seconds"] = max(0, eta_seconds)
    return normalized


def enrich_progress(progress: dict) -> dict:
    return normalize_progress(progress)


__all__ = [
    "DEFAULT_LIMIT",
    "JobStoreLike",
    "MAX_LIMIT",
    "PHASE_LABELS",
    "ProgressPayload",
    "SCHEMA_VERSION",
    "alpha_lifecycle_history_payload",
    "create_sim_job_store",
    "enrich_progress",
    "normalize_progress",
    "progress_percent",
]
