"""Shared error helpers for agent tool implementations."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.error_payloads import user_error_payload


def tool_error(exc: Exception, error_code: str, **context: Any) -> dict[str, Any]:
    return user_error_payload(exc, error_code=error_code, **context)
