"""Actionable error catalog for the BRAIN Alpha Ops web console (E3).

Converts the 11 spec-mandated user-facing error classes into structured
payloads that always carry cause / impact_scope / suggested_action /
recovery entry.

Each entry is bilingual (Chinese primary) and exposes a stable
``recovery_url`` that the frontend renders as a clickable recovery entry.
``classify_exception`` maps Python exceptions, HTTP status codes, and
known BRAIN error strings onto ``ErrorKind``::

    from brain_alpha_ops.error_catalog import classify_exception, build_actionable_error
    kind = classify_exception(exc)
    payload = build_actionable_error(kind, context={"retry_after": 60})

Classification delegates to ``errors.classify_error`` for the general
fallback path (status codes, text heuristics); catalog-specific ErrorKind
patterns (error_code substrings, exception types) are checked first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from brain_alpha_ops.errors import classify_error


class ErrorKind(str, Enum):
    """The 11 user-facing error classes defined in the spec."""

    login_expired = "login_expired"
    cache_unavailable = "cache_unavailable"
    official_rate_limited = "official_rate_limited"
    simulation_concurrency_exceeded = "simulation_concurrency_exceeded"
    dataset_missing = "dataset_missing"
    field_non_compliant = "field_non_compliant"
    expression_invalid = "expression_invalid"
    network_timeout = "network_timeout"
    task_cancelled = "task_cancelled"
    queue_blocked = "queue_blocked"
    local_service_unavailable = "local_service_unavailable"


@dataclass(frozen=True)
class ErrorCatalogEntry:
    """Static metadata for a single ``ErrorKind``."""

    kind: ErrorKind
    cause: str
    impact_scope: str
    suggested_action: str
    recovery_action_id: str
    i18n_key: str
    recovery_url: str
    severity: str = "error"  # "error" | "warning" | "info"


# Recovery URL mapping (kind → frontend route/handler id).
# Routes align with React CardViewId values (config / candidates /
# dashboard / official_backtests / official_operations).
RECOVERY_URLS: dict[ErrorKind, str] = {
    ErrorKind.login_expired: "/config",
    ErrorKind.cache_unavailable: "/operations/refresh",
    ErrorKind.official_rate_limited: "/backtests",
    ErrorKind.simulation_concurrency_exceeded: "/backtests",
    ErrorKind.dataset_missing: "/config",
    ErrorKind.field_non_compliant: "/config",
    ErrorKind.expression_invalid: "/candidates",
    ErrorKind.network_timeout: "/backtests",
    ErrorKind.task_cancelled: "/dashboard",
    ErrorKind.queue_blocked: "/backtests",
    ErrorKind.local_service_unavailable: "/dashboard",
}


def _entry(kind: ErrorKind, cause: str, impact: str, action: str,
           rec_id: str, i18n_key: str, severity: str) -> ErrorCatalogEntry:
    return ErrorCatalogEntry(
        kind=kind, cause=cause, impact_scope=impact,
        suggested_action=action, recovery_action_id=rec_id,
        i18n_key=i18n_key, recovery_url=RECOVERY_URLS[kind], severity=severity,
    )


# The 11 catalog entries (bilingual cause/action).
ERROR_CATALOG: dict[ErrorKind, ErrorCatalogEntry] = {
    ErrorKind.login_expired: _entry(
        ErrorKind.login_expired,
        "BRAIN 平台登录会话已失效或凭据过期（HTTP 401/403 或 AUTH_TOKEN_EXPIRED）。",
        "所有依赖官方 API 的操作：同步、回测、提交、能力集刷新都将失败。",
        "请在系统配置页重新填写凭据并点击「测试连接」；如使用托管凭据，请让维护者刷新。",
        "reconnect_session", "error.login_expired", "error",
    ),
    ErrorKind.cache_unavailable: _entry(
        ErrorKind.cache_unavailable,
        "本地 official_*.json 缓存缺失、损坏或不可读，且首次同步尚未完成。",
        "字段/算子/Dataset 校验、表达式预检、本地回测将退化为不可用。",
        "请在官方操作入口点击「刷新官方能力集」重建缓存；若仍失败，请让维护者检查本地数据目录权限。",
        "refresh_cache", "error.cache_unavailable", "warning",
    ),
    ErrorKind.official_rate_limited: _entry(
        ErrorKind.official_rate_limited,
        "BRAIN 官方接口返回 429 或 RATE_LIMITED，账号级请求频率超限。",
        "官方同步、回测提交、能力集刷新被暂停；候选池本地生产不受影响。",
        "系统会自动等待 retry_after 秒后重试。可在回测监控查看队列状态；频繁出现时请降低并发或让维护者调整请求间隔。",
        "review_official_slots", "error.official_rate_limited", "warning",
    ),
    ErrorKind.simulation_concurrency_exceeded: _entry(
        ErrorKind.simulation_concurrency_exceeded,
        "BRAIN 返回 CONCURRENT_SIMULATION_LIMIT_EXCEEDED，账号级回测并发槽位已满。",
        "新提交的官方回测被拒绝；已在运行的回测不受影响；候选池继续生产。",
        "请等待已有回测完成后再提交新回测；可在回测监控查看槽位占用情况。",
        "review_official_slots", "error.simulation_concurrency_exceeded", "warning",
    ),
    ErrorKind.dataset_missing: _entry(
        ErrorKind.dataset_missing,
        "指定的 dataset_id 不在官方能力集或本地缓存中（KeyError / DATASET_NOT_FOUND）。",
        "依赖该 Dataset 的字段映射、表达式校验、回测提交将失败。",
        "请在系统配置页从官方数据集列表重新选择 Dataset；必要时先刷新官方能力集。",
        "check_config", "error.dataset_missing", "error",
    ),
    ErrorKind.field_non_compliant: _entry(
        ErrorKind.field_non_compliant,
        "表达式或配置使用了 BRAIN 平台不允许的字段/参数（VALIDATION_FAILED / FIELD_NOT_SUPPORTED）。",
        "该候选无法通过官方验证；不影响其他候选或本地评分。",
        "请在系统配置页核对字段名与取值范围；可使用「检查表达式」验证后重新提交。",
        "check_config", "error.field_non_compliant", "error",
    ),
    ErrorKind.expression_invalid: _entry(
        ErrorKind.expression_invalid,
        "Alpha 表达式语法非法、括号不匹配、包含未知算子或为空。",
        "该候选无法进入回测；不影响其他候选或本地评分。",
        "请在候选管理中修正表达式：检查括号匹配、算子名称、字段拼写；可先使用「检查表达式」预检。",
        "fix_expression", "error.expression_invalid", "error",
    ),
    ErrorKind.network_timeout: _entry(
        ErrorKind.network_timeout,
        "与 BRAIN 官方接口的请求超时（HTTP 408/504、urllib timeout、IncompleteRead）。",
        "当前请求失败；BRAIN 平台可能仍在处理。其他操作不受影响。",
        "请稍后重试或缩小同步范围；若频繁超时，请检查网络与 VPN 状态。",
        "wait_and_retry", "error.network_timeout", "warning",
    ),
    ErrorKind.task_cancelled: _entry(
        ErrorKind.task_cancelled,
        "验证/同步/回测任务被用户主动取消或被 StallMonitor 中断。",
        "本次任务结果未确认完成；已保存的检查点不丢失。",
        "可在运行总览查看任务状态；如需继续，请重新启动流程或从检查点恢复。",
        "resume_or_restart", "error.task_cancelled", "info",
    ),
    ErrorKind.queue_blocked: _entry(
        ErrorKind.queue_blocked,
        "官方模拟队列长时间阻塞（槽位全占用且无回写、JOBS_FULL 或 queue_blocked）。",
        "新回测无法入队；候选池本地生产不受影响。",
        "请在回测监控查看队列与槽位状态；必要时取消挂起任务或等待官方回写。",
        "review_official_slots", "error.queue_blocked", "warning",
    ),
    ErrorKind.local_service_unavailable: _entry(
        ErrorKind.local_service_unavailable,
        "本地 Web 服务未启动或无法访问（ConnectionRefused / 503 / health check failed）。",
        "前端无法读取任何数据；所有面板将显示错误状态。",
        "请让维护者启动本地 Web 服务（通常为 `python -m brain_alpha_ops.web`），并确认端口未被占用。",
        "restart_flow", "error.local_service_unavailable", "error",
    ),
}


def build_actionable_error(
    kind: ErrorKind | str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured actionable error payload for the frontend.

    Returns a dict with stable keys: kind, cause, impact_scope,
    suggested_action, recovery_action_id, recovery_url, i18n_key,
    severity, context.
    """
    entry = _resolve_entry(kind)
    return {
        "kind": entry.kind.value,
        "cause": entry.cause,
        "impact_scope": entry.impact_scope,
        "suggested_action": entry.suggested_action,
        "recovery_action_id": entry.recovery_action_id,
        "recovery_url": entry.recovery_url,
        "i18n_key": entry.i18n_key,
        "severity": entry.severity,
        "context": dict(context) if context else {},
    }


def _resolve_entry(kind: ErrorKind | str) -> ErrorCatalogEntry:
    if isinstance(kind, ErrorKind):
        return ERROR_CATALOG[kind]
    if isinstance(kind, str):
        try:
            return ERROR_CATALOG[ErrorKind(kind)]
        except ValueError:
            normalized = kind.strip().lower()
            for member in ErrorKind:
                if member.value == normalized or member.name == normalized:
                    return ERROR_CATALOG[member]
    raise ValueError(f"unknown ErrorKind: {kind!r}")


# Exception → ErrorKind classification.
# Substring rules checked after status_code/exception-type matches.
_STRING_KIND_RULES: list[tuple[tuple[str, ...], ErrorKind]] = [
    (("concurrent_simulation_limit_exceeded", "concurrent simulation limit"),
     ErrorKind.simulation_concurrency_exceeded),
    (("rate_limited", "rate limit", "too many requests", "429"),
     ErrorKind.official_rate_limited),
    (("auth_token_expired", "session_expired", "session_invalid",
      "unauthorized", "forbidden", "incorrect authentication",
      "invalid_credentials", "auth_invalid"),
     ErrorKind.login_expired),
    (("cache_unavailable", "official_fields_empty", "official_operators_empty",
      "context_refresh_failed", "jsondecodeerror", "json decode"),
     ErrorKind.cache_unavailable),
    (("dataset_not_found", "dataset_not_in_official_context", "unknown dataset"),
     ErrorKind.dataset_missing),
    (("field_not_supported", "field_non_compliant", "validation_failed",
      "invalid value for"),
     ErrorKind.field_non_compliant),
    (("expression_empty", "expression_unbalanced_parens",
      "expression_unknown_operator", "expression_null_bytes",
      "expression_invalid", "syntax error", "unknown operator"),
     ErrorKind.expression_invalid),
    (("timed out", "timeout", "incompleteread", "incomplete read",
      "remote end closed", "connection reset", "connection aborted"),
     ErrorKind.network_timeout),
    (("task_cancelled", "raw backend cancellation", "job cancelled",
      "aborted", "aborterror"),
     ErrorKind.task_cancelled),
    (("queue_blocked", "jobs_full", "queue full", "max concurrent active jobs"),
     ErrorKind.queue_blocked),
    (("connection refused", "service unavailable", "local service",
      "web server not running", "health check failed"),
     ErrorKind.local_service_unavailable),
]


# ── ErrorInfo.category → ErrorKind mapping ────────────────────────────────
# Used when classify_exception falls through to the unified classify_error()
# and the resulting ErrorInfo.category must be mapped back to an ErrorKind.
_CATEGORY_TO_KIND: dict[str, ErrorKind] = {
    "auth": ErrorKind.login_expired,
    "rate_limit": ErrorKind.official_rate_limited,
    "network": ErrorKind.network_timeout,
    "not_found": ErrorKind.dataset_missing,
    "validation": ErrorKind.field_non_compliant,
    "conflict": ErrorKind.simulation_concurrency_exceeded,
    "storage": ErrorKind.cache_unavailable,
}


class _StatuscodeException(Exception):
    """Lightweight exception carrying only an HTTP status code."""

    def __init__(self, sc: int) -> None:
        self.status_code = sc
        super().__init__("")


def _classify_fallback(
    exc: BaseException | int | str,
    message: str = "",
) -> ErrorKind:
    """Delegate to the unified ``classify_error`` and map category → ErrorKind.

    Catalog-specific status-code mappings (503 → local_service_unavailable)
    take priority over the generic classify_error category mapping.
    """
    # Check catalog-specific status-code mapping first (differs from
    # classify_error's generic "network" bucket for 503).
    if isinstance(exc, int):
        sc: int | None = exc
    elif isinstance(exc, str):
        sc = None
    else:
        raw = getattr(exc, "status_code", None)
        try:
            sc = int(raw) if raw is not None else None
        except (TypeError, ValueError):
            sc = None
    if sc is not None:
        kind = _kind_from_status(sc)
        if kind is not None:
            return kind

    if isinstance(exc, int):
        info = classify_error(_StatuscodeException(exc))
    elif isinstance(exc, str):
        info = classify_error(Exception(exc))
    else:
        info = classify_error(exc)
    kind = _CATEGORY_TO_KIND.get(info.category)
    if kind is not None:
        return kind
    return ErrorKind.network_timeout


def classify_exception(exc: BaseException | int | str) -> ErrorKind:
    """Map a Python exception / HTTP status / known string to an ``ErrorKind``.

    Resolution order:
      1. ``error_code`` attribute — catalog-specific substring rules.
      2. Exception type (JSONDecodeError→cache_unavailable; KeyError→
         dataset_missing; ConnectionError→local_service_unavailable;
         TimeoutError→network_timeout; asyncio.CancelledError→
         task_cancelled).
      3. ``error_code`` + message substring rules (catalog-specific).
      4. Fallback: delegates to ``errors.classify_error()`` and maps the
         resulting ``ErrorInfo.category`` to an ``ErrorKind``.

    The unified ``classify_error`` is the single classification engine;
    catalog-specific patterns (step 1-3) refine the mapping to the 11
    user-facing ``ErrorKind`` values.
    """
    if isinstance(exc, int):
        return _classify_fallback(exc)
    if isinstance(exc, str):
        return _kind_from_string(exc) or _classify_fallback(exc)
    if exc is None:
        return ErrorKind.network_timeout

    # 1. error_code → catalog-specific substring match.
    err_code = str(getattr(exc, "error_code", "") or "").lower()
    if err_code:
        kind = _kind_from_string(err_code)
        if kind is not None:
            return kind

    # 2. Exception-type-based (catalog-specific mapping).
    kind = _kind_from_type(exc)
    if kind is not None:
        return kind

    # 3. Message substring match (catalog-specific rules).
    message = str(exc).lower()
    kind = _kind_from_string(message)
    if kind is not None:
        return kind

    # 4. Fallback: delegate to the unified classify_error → map category.
    return _classify_fallback(exc, message)


def _kind_from_status(sc: int) -> ErrorKind | None:
    """Map an HTTP status code to a catalog-specific ErrorKind."""
    if sc in (401, 403):
        return ErrorKind.login_expired
    if sc == 429:
        return ErrorKind.official_rate_limited
    if sc in (408, 504):
        return ErrorKind.network_timeout
    if sc == 503:
        return ErrorKind.local_service_unavailable
    return None


def _kind_from_type(exc: BaseException) -> ErrorKind | None:
    if isinstance(exc, json.JSONDecodeError):
        return ErrorKind.cache_unavailable  # official_*.json decode failure
    if isinstance(exc, KeyError):
        return ErrorKind.dataset_missing
    if isinstance(exc, ConnectionError):
        return ErrorKind.local_service_unavailable
    if isinstance(exc, TimeoutError):
        return ErrorKind.network_timeout
    cancelled_cls = _get_asyncio_cancelled_error()
    if cancelled_cls is not None and isinstance(exc, cancelled_cls):
        return ErrorKind.task_cancelled
    return None


def _kind_from_string(text: str) -> ErrorKind | None:
    if not text:
        return None
    lowered = text.lower()
    for needles, kind in _STRING_KIND_RULES:
        for needle in needles:
            if needle in lowered:
                return kind
    return None


_asyncio_cancelled_cache: Any = False


def _get_asyncio_cancelled_error() -> type | None:
    """Return ``asyncio.CancelledError`` lazily, or None if unavailable."""
    global _asyncio_cancelled_cache
    if _asyncio_cancelled_cache is not False:
        return _asyncio_cancelled_cache
    import asyncio  # local import keeps module load stdlib-cheap

    _asyncio_cancelled_cache = asyncio.CancelledError
    return _asyncio_cancelled_cache


__all__ = [
    "ErrorKind", "ErrorCatalogEntry", "ERROR_CATALOG", "RECOVERY_URLS",
    "build_actionable_error", "classify_exception",
]
