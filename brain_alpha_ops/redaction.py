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
    "passwd",
    "password",
    "phone",
    "secret",
    "session",
    "set-cookie",
    "telephone",
    "token",
    "username",
}


def _key_regex_fragment(key: str) -> str:
    normalized = key.strip().lower().replace("-", "_")
    parts = [re.escape(part) for part in normalized.split("_") if part]
    return r"[-_]?".join(parts)


_SENSITIVE_KEY_RE = "|".join(
    sorted(
        {_key_regex_fragment(key) for key in SENSITIVE_KEYS},
        key=len,
        reverse=True,
    )
)
_KEY_VALUE_RE = re.compile(
    rf"(?i)([\"']?)\b({_SENSITIVE_KEY_RE})\b([\"']?)"
    r"(\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^,\s;}}]+)"
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
    text = _KEY_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}{match.group(4)}<redacted>",
        text,
    )
    text = _SECRET_FRAGMENT_RE.sub("<redacted>", text)
    if max_length is not None and len(text) > max_length:
        return text[:max_length]
    return text


def redact_data(
    data: Any,
    *,
    key_fragments: tuple[str, ...] | None = None,
    redacted_keys: set[str] | None = None,
    max_depth: int = 64,
) -> Any:
    fragments = tuple(_normalize_key(fragment) for fragment in (key_fragments or ()))
    return _redact_data(
        data,
        fragments=fragments,
        redacted_keys=redacted_keys,
        max_depth=max(1, int(max_depth or 1)),
        seen=set(),
        depth=0,
    )


def _redact_data(
    data: Any,
    *,
    fragments: tuple[str, ...],
    redacted_keys: set[str] | None,
    max_depth: int,
    seen: set[int],
    depth: int,
) -> Any:
    if depth >= max_depth and isinstance(data, (dict, list, tuple)):
        return "<redacted-depth-limit>"
    if isinstance(data, dict):
        data_id = id(data)
        if data_id in seen:
            return "<redacted-recursive-reference>"
        seen.add(data_id)
        try:
            return {
                key: _redact_value_for_key(
                    key,
                    value,
                    fragments=fragments,
                    redacted_keys=redacted_keys,
                    max_depth=max_depth,
                    seen=seen,
                    depth=depth + 1,
                )
                for key, value in data.items()
            }
        finally:
            seen.remove(data_id)
    if isinstance(data, list):
        data_id = id(data)
        if data_id in seen:
            return "<redacted-recursive-reference>"
        seen.add(data_id)
        try:
            return [
                _redact_data(
                    item,
                    fragments=fragments,
                    redacted_keys=redacted_keys,
                    max_depth=max_depth,
                    seen=seen,
                    depth=depth + 1,
                )
                for item in data
            ]
        finally:
            seen.remove(data_id)
    if isinstance(data, tuple):
        data_id = id(data)
        if data_id in seen:
            return "<redacted-recursive-reference>"
        seen.add(data_id)
        try:
            return tuple(
                _redact_data(
                    item,
                    fragments=fragments,
                    redacted_keys=redacted_keys,
                    max_depth=max_depth,
                    seen=seen,
                    depth=depth + 1,
                )
                for item in data
            )
        finally:
            seen.remove(data_id)
    if isinstance(data, str):
        return redact_text(data)
    return data


def _redact_value_for_key(
    key: Any,
    value: Any,
    *,
    fragments: tuple[str, ...],
    redacted_keys: set[str] | None,
    max_depth: int,
    seen: set[int],
    depth: int,
) -> Any:
    normalized = _normalize_key(str(key))
    if _is_sensitive_key(normalized, fragments):
        if redacted_keys is not None:
            redacted_keys.add(str(key))
        return "<redacted>"
    return _redact_data(
        value,
        fragments=fragments,
        redacted_keys=redacted_keys,
        max_depth=max_depth,
        seen=seen,
        depth=depth,
    )


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
