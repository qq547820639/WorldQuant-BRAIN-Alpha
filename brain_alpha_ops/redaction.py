"""Shared helpers for redacting credentials from user-visible errors."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEYS = {
    "access_token",
    "address",
    "api_key",
    "authorization",
    "cookie",
    "csrf",
    "education",
    "email",
    "employer",
    "employment",
    "first_name",
    "firstname",
    "full_name",
    "fullname",
    "image",
    "last_name",
    "lastname",
    "password",
    "phone",
    "secret",
    "session",
    "set-cookie",
    "telephone",
    "token",
    "username",
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
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def redact_text(value: object, *, max_length: int | None = None) -> str:
    text = str(value or "")
    text = _EMAIL_RE.sub("***@***", text)
    text = _AUTH_RE.sub(lambda match: f"{match.group(1)} <redacted>", text)
    text = _KEY_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", text)
    text = _SECRET_FRAGMENT_RE.sub("<redacted>", text)
    if max_length is not None and len(text) > max_length:
        return text[:max_length]
    return text


def redact_data(
    data: Any,
    *,
    key_fragments: tuple[str, ...] | None = None,
    redacted_keys: set[str] | None = None,
) -> Any:
    fragments = tuple(_normalize_key(fragment) for fragment in (key_fragments or ()))
    if isinstance(data, dict):
        return {
            key: _redact_value_for_key(key, value, fragments=fragments, redacted_keys=redacted_keys)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_data(item, key_fragments=key_fragments, redacted_keys=redacted_keys) for item in data]
    if isinstance(data, tuple):
        return tuple(redact_data(item, key_fragments=key_fragments, redacted_keys=redacted_keys) for item in data)
    if isinstance(data, str):
        return redact_text(data)
    return data


def _redact_value_for_key(
    key: Any,
    value: Any,
    *,
    fragments: tuple[str, ...],
    redacted_keys: set[str] | None,
) -> Any:
    normalized = _normalize_key(str(key))
    if _is_sensitive_key(normalized, fragments):
        if redacted_keys is not None:
            redacted_keys.add(str(key))
        return "<redacted>"
    return redact_data(value, key_fragments=fragments, redacted_keys=redacted_keys)


def _is_sensitive_key(normalized_key: str, fragments: tuple[str, ...]) -> bool:
    if normalized_key in {_normalize_key(key) for key in SENSITIVE_KEYS}:
        return True
    parts = {part for part in normalized_key.split("_") if part}
    return any(
        fragment
        and (
            normalized_key == fragment
            or fragment in parts
            or normalized_key.startswith(f"{fragment}_")
            or normalized_key.endswith(f"_{fragment}")
        )
        for fragment in fragments
    )


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def redact_error_message(exc: Exception | object, *, max_length: int = 240) -> str:
    message = str(exc) or exc.__class__.__name__
    return redact_text(message, max_length=max_length)
