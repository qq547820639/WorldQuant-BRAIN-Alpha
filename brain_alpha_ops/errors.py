"""Typed error hierarchy for Brain Alpha Ops.

Phase D2: Replaces generic Exception('message') with typed, machine-readable
error classes that map directly to the error_code enum in the API contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from brain_alpha_ops.redaction import redact_error_message


class AppError(Exception):
    """Base class for all application errors."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "ok": False,
            "error": self.message,
            "error_code": self.code,
        }


class ValidationError(AppError):
    """Invalid input parameters."""

    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", 400)


class AuthError(AppError):
    """BRAIN API authentication failed."""

    def __init__(self, message: str = "BRAIN API authentication failed"):
        super().__init__(message, "AUTH_FAILED", 400)


class SubmitBlockedError(AppError):
    """Alpha submission blocked by safety gate."""

    def __init__(self, message: str):
        super().__init__(message, "SUBMIT_BLOCKED", 400)


class MissingOfficialIdError(AppError):
    """Alpha has no official_alpha_id — run simulation first."""

    def __init__(self, message: str = "Missing official Alpha ID"):
        super().__init__(message, "MISSING_OFFICIAL_ID", 400)


class ConflictError(AppError):
    """Resource conflict (e.g., another job running)."""

    def __init__(self, message: str, code: str = "CONFLICT_RUNNING"):
        super().__init__(message, code, 409)


class NotFoundError(AppError):
    """Resource not found."""

    def __init__(self, message: str = "Not found"):
        super().__init__(message, "NOT_FOUND", 404)


class SessionError(AppError):
    """Invalid or expired session."""

    def __init__(self, message: str = "Invalid local session"):
        super().__init__(message, "SESSION_INVALID", 403)


class OriginForbiddenError(AppError):
    """Request from non-local origin."""

    def __init__(self):
        super().__init__("Forbidden local request origin", "ORIGIN_FORBIDDEN", 403)


class ContextRefreshError(AppError):
    """Failed to refresh fields/operators context and no cache available."""

    def __init__(self, message: str = "Context refresh failed"):
        super().__init__(message, "CONTEXT_REFRESH_FAILED", 500)


@dataclass(frozen=True)
class ErrorInfo:
    error_code: str
    category: str
    message: str
    error_type: str
    retryable: bool = False
    status_code: int | None = None
    retry_after: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error_code": self.error_code,
            "error_category": self.category,
            "error": self.message,
            "error_type": self.error_type,
            "retryable": self.retryable,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        return payload


def classify_error(exc: Exception | object, *, default_code: str = "UNHANDLED_ERROR") -> ErrorInfo:
    message = redact_error_message(exc, max_length=500)
    error_type = exc.__class__.__name__
    app_code = str(getattr(exc, "code", "") or "")
    status_code = getattr(exc, "status_code", None)
    retry_after = getattr(exc, "retry_after", None)
    text = message.lower()
    explicit_category = _category_for_code(default_code)

    if app_code:
        return ErrorInfo(
            error_code=app_code,
            category=_category_for_code(app_code),
            message=message,
            error_type=error_type,
            retryable=_retryable_for_code(app_code),
            status_code=_safe_status(status_code),
            retry_after=_safe_float(retry_after),
        )

    if explicit_category != "internal":
        return ErrorInfo(default_code, explicit_category, message, error_type, _retryable_for_code(default_code), _safe_status(status_code), _safe_float(retry_after))
    if _safe_status(status_code) == 429 or "rate limit" in text or "too many requests" in text:
        return ErrorInfo(default_code, "rate_limit", message, error_type, True, _safe_status(status_code), _safe_float(retry_after))
    if _safe_status(status_code) in {401, 403} or "auth" in text or "credential" in text or "unauthorized" in text or "forbidden" in text:
        return ErrorInfo(default_code, "auth", message, error_type, False, _safe_status(status_code), _safe_float(retry_after))
    if _safe_status(status_code) == 404 or "not found" in text or "unknown simulation id" in text:
        return ErrorInfo(default_code, "not_found", message, error_type, False, _safe_status(status_code), _safe_float(retry_after))
    if _safe_status(status_code) == 400 or "validation" in text or "invalid" in text or "missing" in text:
        return ErrorInfo(default_code, "validation", message, error_type, False, _safe_status(status_code), _safe_float(retry_after))
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return ErrorInfo(default_code, "validation", message, error_type, False, _safe_status(status_code), _safe_float(retry_after))
    if _safe_status(status_code) in {408, 500, 502, 503, 504}:
        return ErrorInfo(default_code, "network", message, error_type, True, _safe_status(status_code), _safe_float(retry_after))
    if any(token in text for token in ("timed out", "timeout", "connection", "network", "temporarily unavailable")):
        return ErrorInfo(default_code, "network", message, error_type, True, _safe_status(status_code), _safe_float(retry_after))
    if isinstance(exc, OSError):
        return ErrorInfo(default_code, "storage", message, error_type, False, _safe_status(status_code), _safe_float(retry_after))
    return ErrorInfo(default_code, "internal", message, error_type, False, _safe_status(status_code), _safe_float(retry_after))


def _category_for_code(code: str) -> str:
    code = code.upper()
    if "AUTH" in code or "SESSION" in code or "ORIGIN" in code:
        return "auth"
    if "VALIDATION" in code or "MISSING" in code or "PARSE" in code or "JSON" in code:
        return "validation"
    if "NOT_FOUND" in code:
        return "not_found"
    if "CONFLICT" in code:
        return "conflict"
    return "internal"


def _retryable_for_code(code: str) -> bool:
    code = code.upper()
    return any(token in code for token in ("RATE_LIMIT", "TIMEOUT", "RETRY", "TEMPORARY"))


def _safe_status(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
