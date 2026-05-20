"""Shared helpers for redacting credentials from user-visible errors."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "csrf",
    "password",
    "secret",
    "session",
    "set-cookie",
    "token",
}

_KEY_VALUE_RE = re.compile(
    r"(?i)\b(access_token|authorization|cookie|csrf|password|secret|session|set-cookie|token)\b"
    r"(\s*[:=]\s*)"
    r"([^,\s;]+)"
)
_AUTH_RE = re.compile(r"(?i)\b(Basic|Bearer)\s+[A-Za-z0-9._~+/=-]+")
_SECRET_FRAGMENT_RE = re.compile(
    r"(?i)\b[A-Za-z0-9._~+/=-]*"
    r"(?:access[-_]?token|authorization|cookie|csrf|password|secret|session|token)"
    r"[-_][A-Za-z0-9._~+/=-]*\d[A-Za-z0-9._~+/=-]*\b"
)


def redact_text(value: object, *, max_length: int | None = None) -> str:
    text = str(value or "")
    text = _AUTH_RE.sub(lambda match: f"{match.group(1)} <redacted>", text)
    text = _KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = _SECRET_FRAGMENT_RE.sub("<redacted>", text)
    if max_length is not None and len(text) > max_length:
        return text[:max_length]
    return text


def redact_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            key: "<redacted>" if str(key).lower() in SENSITIVE_KEYS else redact_data(value)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_data(item) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_data(item) for item in data)
    if isinstance(data, str):
        return redact_text(data)
    return data


def redact_error_message(exc: Exception | object, *, max_length: int = 240) -> str:
    message = str(exc) or exc.__class__.__name__
    return redact_text(message, max_length=max_length)
