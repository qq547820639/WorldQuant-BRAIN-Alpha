"""Shared logger, type aliases, and helper functions."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger("brain_alpha_ops.web.misc.web_assistant_snapshots")

LoadConfig = Callable[[], RunConfig]
WebError = Callable[[Exception, str], dict[str, Any]]
BoundedFloat = Callable[[Any, float, float], float]
PayloadTruthy = Callable[[Any], bool]
ReadStorageJsonl = Callable[..., list[dict[str, Any]]]
StoragePath = Callable[[str], Path]
SafeErrorMessage = Callable[[Exception], str]
RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
Snapshot = Callable[..., dict[str, Any]]


def _default_web_error(exc: Exception, error_code: str) -> dict[str, Any]:
    from brain_alpha_ops.redaction import redact_error_message
    return {"ok": False, "error_code": error_code, "error": redact_error_message(exc)}


def _bounded_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _payload_truthy(value: Any) -> bool:
    return value not in (False, "false", "False", "0", 0, None)
