"""Shared Web state and user-error contract helpers.

The Web console has several independently polled workflows.  This module keeps
their browser-facing status and recovery hints consistent without changing the
existing raw job/error fields that older callers already consume.
"""
from __future__ import annotations

from typing import Any, Mapping

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.tasks import (
    ACTIVE_STATUSES,
    DEFAULT_RECOVERY_ERROR,
    DEFAULT_WATCHDOG_ERROR,
    TERMINAL_STATUSES,
)

_CANCELLED_STATUSES = {"stopped", "cancelled", "canceled"}
_SUCCESS_STATUSES = {"completed"}
_WARNING_STATUSES = {"completed_with_warnings"}
_FAILED_STATUSES = {"failed"}
_MISSING_STATUSES = {"missing"}

_ERROR_DEFINITIONS: dict[str, dict[str, Any]] = {
    "session_expired": {
        "title": "本地会话已失效",
        "message": "本地会话已失效，需要重新连接后继续。",
        "impact": "当前操作无法确认你的 Web 会话，正在运行的监控或官方操作可能无法继续读取状态。",
        "suggested_action": "回到运行总览或系统配置，重新测试连接；本地缓存仍可用于非提交浏览。",
        "action_label": "重新连接",
        "next_action": "reconnect_session",
        "severity": "error",
        "recoverable": True,
        "retryable": False,
    },
    "cache_unavailable": {
        "title": "本地缓存不可用",
        "message": "本地缓存不可用，当前页面无法读取生产输入。",
        "impact": "候选生产、评分或门禁只能停在可恢复状态，不能把缺失缓存当作官方证据。",
        "suggested_action": "检查本地缓存文件是否存在；必要时在官方操作中手动刷新缓存。",
        "action_label": "检查缓存",
        "next_action": "refresh_cache",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "official_rate_limited": {
        "title": "官方接口限流",
        "message": "BRAIN 官方接口请求过于频繁，请稍后重试。",
        "impact": "官方同步、回测或检查会暂停；本地候选生产和评分可以继续。",
        "suggested_action": "等待限流冷却后重试，或降低官方操作并发。",
        "action_label": "稍后重试",
        "next_action": "wait_and_retry",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "web_rate_limited": {
        "title": "本地 Web 请求过于频繁",
        "message": "本地 Web 操作请求过于频繁，请稍后再试。",
        "impact": "当前页面会暂时拒绝新的本地请求，避免多个操作同时挤占状态通道。",
        "suggested_action": "等待几秒后重试；如果后台任务仍在运行，请先查看任务状态。",
        "action_label": "稍后重试",
        "next_action": "wait_and_retry",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "official_concurrency_limit": {
        "title": "官方回测并发已满",
        "message": "BRAIN 官方回测并发槽位已满，新的回测需要等待空槽。",
        "impact": "只有官方回测队列受影响；候选池生产、本地评分和质量门禁不应被锁死。",
        "suggested_action": "等待已有官方回测完成，或稍后重新运行官方验证队列。",
        "action_label": "查看回测槽位",
        "next_action": "review_official_slots",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "dataset_missing": {
        "title": "Dataset 不可用",
        "message": "当前 Dataset 在官方能力集或本地缓存中不可用。",
        "impact": "相关候选不能进入官方验证，避免使用未确认的数据集规则。",
        "suggested_action": "刷新官方能力集后，从系统配置的数据集列表重新选择。",
        "action_label": "刷新能力集",
        "next_action": "refresh_capabilities",
        "severity": "error",
        "recoverable": True,
        "retryable": False,
    },
    "invalid_expression": {
        "title": "表达式不合规",
        "message": "Alpha 表达式包含非法语法、未知字段或未知算子。",
        "impact": "该候选不能进入官方回测或提交预审。",
        "suggested_action": "查看候选的阻断原因，按官方字段/算子能力集修正表达式。",
        "action_label": "查看候选",
        "next_action": "fix_expression",
        "severity": "error",
        "recoverable": True,
        "retryable": False,
    },
    "network_timeout": {
        "title": "网络或请求超时",
        "message": "网络请求未在预期时间内返回。",
        "impact": "当前操作状态不明确，系统应停止或恢复监控后再继续。",
        "suggested_action": "检查网络后刷新状态；如果仍不明确，停止当前流程后重试。",
        "action_label": "刷新状态",
        "next_action": "refresh_status",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "task_cancelled": {
        "title": "流程已停止",
        "message": "当前流程已停止或取消。",
        "impact": "本轮任务不会继续写入新结果，已有本地证据仍会保留。",
        "suggested_action": "确认原因后重新启动对应流程。",
        "action_label": "重新启动",
        "next_action": "restart_flow",
        "severity": "info",
        "recoverable": True,
        "retryable": True,
    },
    "queue_blocked": {
        "title": "队列已有任务",
        "message": "已有相关任务正在运行，新的操作暂时不能入队。",
        "impact": "避免多个工作流同时修改候选池、评分或官方队列状态。",
        "suggested_action": "等待当前任务完成，或在任务监控中停止异常流程后重试。",
        "action_label": "查看任务",
        "next_action": "review_active_job",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "job_not_found": {
        "title": "找不到任务",
        "message": "找不到本次任务，可能已完成、被清理或服务已重启。",
        "impact": "当前监控不能继续依赖旧任务 ID。",
        "suggested_action": "刷新页面状态；如仍需要执行，请重新启动流程。",
        "action_label": "重新启动",
        "next_action": "restart_flow",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "completed_with_warnings": {
        "title": "流程带警告完成",
        "message": "流程已结束，但部分官方上下文、检查或候选结果需要复核。",
        "impact": "不要把带警告完成理解为提交就绪；需要先查看警告项。",
        "suggested_action": "打开对应结果面板，处理警告后再继续下一步。",
        "action_label": "查看警告",
        "next_action": "review_warnings",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "task_interrupted": {
        "title": "流程被中断",
        "message": "流程在完成前被停止、重启恢复或 watchdog 中断。",
        "impact": "当前结果不能视为完整闭环，需要恢复或重新运行。",
        "suggested_action": "查看任务记录，确认是否需要续跑或重新启动。",
        "action_label": "恢复流程",
        "next_action": "resume_or_restart",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "job_failed": {
        "title": "流程失败",
        "message": "流程未能完成。",
        "impact": "本轮结果不能推进到后续官方验证或提交预审。",
        "suggested_action": "查看错误详情和事件记录，修复后重试。",
        "action_label": "查看详情",
        "next_action": "inspect_error",
        "severity": "error",
        "recoverable": True,
        "retryable": True,
    },
    "unknown_state": {
        "title": "状态不明确",
        "message": "系统暂时无法确认当前流程状态。",
        "impact": "为了避免误判完成或继续写入，应该刷新状态或中断异常流程。",
        "suggested_action": "刷新状态；连续失败时停止当前任务后重试。",
        "action_label": "刷新状态",
        "next_action": "refresh_status",
        "severity": "warning",
        "recoverable": True,
        "retryable": True,
    },
    "general_error": {
        "title": "操作异常",
        "message": "操作未能完成。",
        "impact": "当前步骤不会继续推进。",
        "suggested_action": "重试当前操作；如果持续失败，请查看诊断记录。",
        "action_label": "重试",
        "next_action": "retry_operation",
        "severity": "error",
        "recoverable": True,
        "retryable": False,
    },
}

_STATUS_LABELS = {
    "active": "进行中",
    "success": "已完成",
    "warning": "带警告完成",
    "failed": "失败",
    "interrupted": "已中断",
    "missing": "监控受阻",
    "idle": "空闲",
    "unknown": "状态不明确",
}

def enrich_error_payload(payload: Mapping[str, Any], *, fallback_kind: str | None = None) -> dict[str, Any]:
    """Return an error payload with AF-018 user-action metadata attached."""

    enriched = dict(payload)
    raw_error = enriched.get("error") or enriched.get("redacted_message") or ""
    safe_error = redact_error_message(raw_error, max_length=500)
    if raw_error or "error" in enriched:
        enriched["error"] = safe_error
    kind = fallback_kind or classify_user_error_kind(enriched)
    user_error = build_user_error(kind, raw_error=safe_error, payload=enriched)
    enriched["user_error"] = user_error
    enriched["user_error_kind"] = user_error["kind"]
    enriched["user_message"] = user_error["message"]
    enriched["next_action"] = user_error["next_action"]
    enriched["recoverable"] = user_error["recoverable"]
    enriched["retryable"] = bool(enriched.get("retryable", user_error["retryable"]))
    return enriched

def enrich_job_response(payload: Mapping[str, Any], *, job_type: str | None = None) -> dict[str, Any]:
    """Attach stable status classification to a job/status response."""

    enriched = dict(payload)
    if job_type:
        enriched.setdefault("job_type", job_type)
    progress = enriched.get("progress") if isinstance(enriched.get("progress"), dict) else {}
    status = str(enriched.get("status") or progress.get("status") or "unknown")
    phase = str(enriched.get("phase") or progress.get("phase") or "")
    error = str(enriched.get("error") or progress.get("error") or progress.get("status_message") or "")

    state = classify_job_status(status=status, phase=phase, error=error, progress=progress)
    enriched.update(state)
    if state.get("user_error_kind"):
        user_error = build_user_error(str(state["user_error_kind"]), raw_error=error, payload=enriched)
        enriched["user_error"] = user_error
        enriched["user_error_kind"] = user_error["kind"]
        enriched["user_message"] = user_error["message"]
        enriched["next_action"] = user_error["next_action"]
        enriched["retryable"] = bool(enriched.get("retryable", user_error["retryable"]))
    elif enriched.get("ok") is False or enriched.get("error") or enriched.get("error_code"):
        enriched = enrich_error_payload(enriched)
    return enriched

def classify_job_status(
    *,
    status: str,
    phase: str = "",
    error: str = "",
    progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_status(status)
    text = f"{normalized} {phase} {error} {dict(progress or {})}".lower()

    if normalized in ACTIVE_STATUSES:
        return _state("active", terminal=False, recoverable=True, next_action="monitor_or_cancel")
    if normalized in _SUCCESS_STATUSES:
        return _state("success", terminal=True, recoverable=False, next_action="review_results")
    if normalized in _WARNING_STATUSES:
        return _state(
            "warning",
            terminal=True,
            recoverable=True,
            retryable=True,
            next_action="review_warnings",
            user_error_kind="completed_with_warnings",
        )
    if normalized in _CANCELLED_STATUSES:
        return _state(
            "interrupted",
            terminal=True,
            interrupted=True,
            recoverable=True,
            retryable=True,
            next_action="restart_flow",
            user_error_kind="task_cancelled",
        )
    if normalized in _FAILED_STATUSES:
        interrupted = _looks_interrupted(text)
        specific_error_kind = "task_interrupted" if interrupted else _specific_failed_job_kind(text)
        return _state(
            "interrupted" if interrupted else "failed",
            terminal=True,
            interrupted=interrupted,
            recoverable=True,
            retryable=True,
            next_action="resume_or_restart" if interrupted else "inspect_error",
            user_error_kind=specific_error_kind,
        )
    if normalized in _MISSING_STATUSES:
        return _state(
            "missing",
            terminal=True,
            interrupted=True,
            recoverable=True,
            retryable=True,
            next_action="restart_flow",
            user_error_kind="job_not_found",
        )
    if normalized in {"idle", ""}:
        return _state("idle", terminal=False, recoverable=False, next_action="")
    return _state(
        "unknown",
        terminal=False,
        recoverable=True,
        retryable=True,
        next_action="refresh_status",
        user_error_kind="unknown_state",
    )

def classify_user_error_kind(payload: Mapping[str, Any]) -> str:
    code = str(payload.get("error_code") or payload.get("status_code") or "")
    status_code = _int_value(payload.get("status_code"))
    error_text = str(payload.get("error") or payload.get("redacted_message") or payload.get("message") or "")
    text = f"{code} {error_text}".strip()
    upper = text.upper()
    lower = text.lower()

    if "SESSION_INVALID" in upper or "AUTH" in upper or status_code in {401, 403} or "invalid local session" in lower:
        return "session_expired"
    if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in upper or "CONCURRENT_SIMULATION_LIMIT" in upper:
        return "official_concurrency_limit"
    if "WEB_RATE_LIMIT" in upper or "LOCAL_RATE_LIMIT" in upper or "too many read requests" in lower or "too many write requests" in lower or "too many submit requests" in lower:
        return "web_rate_limited"
    if "RATE_LIMIT" in upper or "RATE LIMIT" in upper or "RATE_LIMITED" in upper or status_code == 429 or "too many requests" in lower:
        return "official_rate_limited"
    if "CACHE" in upper and any(token in lower for token in ("unavailable", "missing", "invalid", "failed", "not found")):
        return "cache_unavailable"
    if "CONTEXT" in upper and any(token in lower for token in ("unavailable", "missing cache", "cache unavailable")):
        return "cache_unavailable"
    if "DATASET" in upper and any(token in lower for token in ("missing", "not found", "unknown", "unavailable", "not in official")):
        return "dataset_missing"
    if "EXPRESSION" in upper or "UNKNOWN_OPERATOR" in upper or "syntax" in lower or "unknown operator" in lower:
        return "invalid_expression"
    if "TIMEOUT" in upper or status_code == 408 or "timed out" in lower or "timeout" in lower:
        return "network_timeout"
    if status_code in {500, 502, 503, 504} or any(token in lower for token in ("network", "connection reset", "connection aborted", "remote end closed", "urlopen error")):
        return "network_timeout"
    if any(token in upper for token in ("CANCELLED", "CANCELED", "STOPPED", "STOP_FAILED")) or "task cancelled" in lower:
        return "task_cancelled"
    if "CONFLICT" in upper or "JOBS_FULL" in upper or "QUEUE" in upper or "active " in lower or "already running" in lower:
        return "queue_blocked"
    if "JOB_NOT_FOUND" in upper or ("not found" in lower and "dataset" not in lower):
        return "job_not_found"
    return "general_error"

def build_user_error(kind: str, *, raw_error: str = "", payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    definition = _ERROR_DEFINITIONS.get(kind) or _ERROR_DEFINITIONS["general_error"]
    safe_error = redact_error_message(raw_error, max_length=500)
    message = str(definition["message"])
    if kind == "general_error" and safe_error:
        message = safe_error
    result = {
        "kind": kind if kind in _ERROR_DEFINITIONS else "general_error",
        "title": definition["title"],
        "message": message,
        "impact": definition["impact"],
        "suggested_action": definition["suggested_action"],
        "action_label": definition["action_label"],
        "next_action": definition["next_action"],
        "severity": definition["severity"],
        "recoverable": bool(definition["recoverable"]),
        "retryable": bool(definition["retryable"]),
    }
    retry_after = (payload or {}).get("retry_after")
    if retry_after not in (None, ""):
        result["retry_after"] = retry_after
    if safe_error and safe_error != message:
        result["detail"] = safe_error
    return result

def _state(
    status_kind: str,
    *,
    terminal: bool,
    interrupted: bool = False,
    recoverable: bool,
    retryable: bool = False,
    next_action: str,
    user_error_kind: str = "",
) -> dict[str, Any]:
    return {
        "status_kind": status_kind,
        "state_label": _STATUS_LABELS.get(status_kind, "状态不明确"),
        "terminal": terminal,
        "active": status_kind == "active",
        "interrupted": interrupted,
        "recoverable": recoverable,
        "retryable": retryable,
        "next_action": next_action,
        **({"user_error_kind": user_error_kind} if user_error_kind else {}),
    }

def _normalize_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "canceled":
        return "cancelled"
    return normalized

def _looks_interrupted(text: str) -> bool:
    markers = (
        "watchdog",
        "stopped",
        "cancelled",
        "canceled",
        "status_failed",
        "sse_exhausted",
        "stream_timeout",
        "ambiguous",
        "stalled",
        "restart",
        DEFAULT_RECOVERY_ERROR.lower(),
        DEFAULT_WATCHDOG_ERROR.lower(),
    )
    return any(marker in text for marker in markers)

def _specific_failed_job_kind(text: str) -> str:
    kind = classify_user_error_kind({"error": text})
    return "job_failed" if kind in {"general_error", "job_failed"} else kind

def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
