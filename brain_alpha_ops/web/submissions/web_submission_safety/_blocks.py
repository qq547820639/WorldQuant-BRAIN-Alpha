"""Shared building blocks for submission safety preflight services.

Extracted from the former ``web_submission_safety.py`` monolith
(deep-optimization-phase13). Holds the preflight block builder, the
callable type aliases, and the module logger. The logger name is
hardcoded to the original module path so log records continue to
attribute to ``brain_alpha_ops.web.submissions.web_submission_safety``
after the split.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger

LedgerFactory = Callable[[str], SubmissionLedger]
CloudAlphaSnapshot = Callable[..., dict[str, Any]]
CloudStatusFor = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]
ObservabilityBuilder = Callable[..., dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]
RepositoryFactory = Callable[[str], ResearchRepository]

logger = logging.getLogger("brain_alpha_ops.web.submissions.web_submission_safety")


def submit_preflight_block(
    error_code: str,
    error: str,
    *,
    category: str = "validation",
    action: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error_code": error_code, "error_category": category, "error": error}
    if action:
        payload["action"] = action
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


submission_preflight_block = submit_preflight_block
