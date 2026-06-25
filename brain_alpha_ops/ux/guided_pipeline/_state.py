"""Shared state for the guided_pipeline package.

Exposes ``_pkg()`` so submodules can read package-level attributes
(``_unified_classify``, ``run_pipeline_from_config``) that tests may
monkeypatch on the package itself.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)


def _pkg() -> Any:
    """Return the parent package module so submodules can access
    ``_unified_classify`` and ``run_pipeline_from_config`` that tests may
    monkeypatch on the package."""
    return sys.modules["brain_alpha_ops.ux.guided_pipeline"]


def classify_error(error: Exception) -> dict[str, str]:
    """Classify an error and return actionable guidance."""
    try:
        info = _pkg()._unified_classify(error)
        return {
            "type": info.error_code or type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": info.fix_hint or "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "yes" if info.retryable else ("maybe" if info.retryable is None else "no"),
        }
    except Exception:
        logger.warning("guided pipeline error classification fallback failed", exc_info=True)
        return {
            "type": type(error).__name__,
            "message": redact_error_message(error, max_length=200),
            "fix": "未知错误。请在页面事件记录中查看提示，或让维护者查看诊断信息。",
            "retry": "maybe",
        }
