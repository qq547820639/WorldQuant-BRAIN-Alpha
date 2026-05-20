"""Unified error classification knowledge base for BRAIN Alpha Ops.

Merges the dual classify_error() from errors.py and ux/guided_pipeline.py
into a single authoritative source. Both modules import from here.
"""

from __future__ import annotations

from dataclasses import dataclass

from brain_alpha_ops.errors import (
    AppError,
    AuthError,
    ConflictError,
    ContextRefreshError,
    MissingOfficialIdError,
    NotFoundError,
    OriginForbiddenError,
    SessionError,
    SubmitBlockedError,
    ValidationError,
    classify_error as _core_classify,
)


@dataclass(frozen=True)
class ErrorInfo:
    error_code: str
    error_category: str
    redacted_message: str
    error_type: str
    retryable: bool = False
    fix_hint: str = ""
    status_code: int | None = None
    retry_after: float | None = None

    def to_dict(self) -> dict:
        payload = {
            "error_code": self.error_code,
            "error_category": self.error_category,
            "error": self.redacted_message,
            "error_type": self.error_type,
            "retryable": self.retryable,
            "fix_hint": self.fix_hint,
        }
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.retry_after is not None:
            payload["retry_after"] = self.retry_after
        return payload


# ── UX / guided pipeline error code taxonomy ──

UX_ERROR_CODES: dict[str, dict] = {
    # Connectivity & API
    "API_TIMEOUT": {
        "category": "connectivity",
        "retryable": True,
        "fix_hint": "Check network. Increase ops.official_api.timeout_seconds or retry later.",
    },
    "API_RATE_LIMITED": {
        "category": "rate_limit",
        "retryable": True,
        "fix_hint": "Reduce max_official_*_per_cycle or increase official_retry_pause_seconds.",
    },
    "API_UNAUTHORIZED": {
        "category": "credentials",
        "retryable": False,
        "fix_hint": "Verify BRAIN_USERNAME / BRAIN_PASSWORD / BRAIN_TOKEN env vars. Check credentials resolve().",
    },
    # Redline / compliance
    "REDLINE_FAILED": {
        "category": "compliance",
        "retryable": False,
        "fix_hint": "Run 'brain-alpha-ops redline --block' to see violations. Fix config/generator/data sources.",
    },
    # Scoring
    "SCORE_LOW": {
        "category": "quality",
        "retryable": True,
        "fix_hint": "Review attribution report. Adjust generation parameters or add guidance bias.",
    },
    "GATE_BLOCKED": {
        "category": "quality",
        "retryable": True,
        "fix_hint": "Check hard_gates in scoring result. Tune expression, fields, or operators.",
    },
    # Generation
    "GENERATION_FAILED": {
        "category": "generation",
        "retryable": True,
        "fix_hint": "Check field/operator availability. Try different dataset or generation mode.",
    },
    "NO_CANDIDATES": {
        "category": "generation",
        "retryable": True,
        "fix_hint": "Relax min_local_quality_score. Increase max_candidates_per_cycle. Verify dataset has data.",
    },
    # Budget / quotas
    "BUDGET_EXHAUSTED": {
        "category": "budget",
        "retryable": False,
        "fix_hint": "Increase cycle budgets or wait for next period.",
    },
    # General
    "UNKNOWN": {
        "category": "unknown",
        "retryable": True,
        "fix_hint": "Check logs for full traceback.",
    },
}


def classify_ux_error(error: Exception | str) -> ErrorInfo:
    """Classify any exception into an ErrorInfo suitable for UX display.

    Delegates to errors.classify_error() for typed AppError instances,
    then enriches with UX-specific category and fix hints from UX_ERROR_CODES.
    """
    if not isinstance(error, Exception):
        error = RuntimeError(str(error))

    # Use the core typed classifier first
    core_info = _core_classify(error)

    # Enrich with UX taxonomy
    code = core_info.error_code or "UNKNOWN"
    ux_meta = UX_ERROR_CODES.get(code, UX_ERROR_CODES["UNKNOWN"])

    return ErrorInfo(
        error_code=code,
        error_category=ux_meta.get("category", core_info.category),
        retryable=ux_meta.get("retryable", core_info.retryable),
        fix_hint=ux_meta.get("fix_hint", ""),
        error_type=core_info.error_type,
        redacted_message=core_info.message,
        status_code=core_info.status_code,
        retry_after=core_info.retry_after,
    )


__all__ = [
    "UX_ERROR_CODES",
    "classify_ux_error",
    # Re-export from errors.py for single-import convenience
    "AppError",
    "AuthError",
    "ConflictError",
    "ContextRefreshError",
    "MissingOfficialIdError",
    "NotFoundError",
    "OriginForbiddenError",
    "SessionError",
    "SubmitBlockedError",
    "ValidationError",
    "ErrorInfo",
]
