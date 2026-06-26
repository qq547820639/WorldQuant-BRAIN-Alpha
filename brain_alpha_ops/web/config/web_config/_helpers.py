"""Helper functions for payload parsing and bounding."""
from __future__ import annotations

import math
from typing import Any


def payload_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def payload_bool(payload: dict, key: str, default: object = False) -> bool:
    return payload_truthy(payload.get(key, default))


def payload_web_environment(payload: dict) -> str | None:
    if "environment" not in payload:
        return None
    environment = str(payload.get("environment") or "production").strip().lower()
    if environment != "production":
        raise ValueError("web console only supports production environment")
    return "production"


def payload_string_list(payload: dict, key: str, default: list[str] | None = None) -> list[str]:
    raw = payload.get(key, default or [])
    if isinstance(raw, str):
        values: list[Any] = raw.replace("\r", "\n").replace(",", "\n").splitlines()
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = list(default or [])
    return [str(item).strip() for item in values if str(item).strip()]


def bounded_query_int(value: object, lower: int, upper: int) -> int:
    if value is None:
        return lower
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def bounded_query_float(value: object, lower: float, upper: float) -> float:
    if value is None:
        return lower
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def payload_int(
    payload: dict,
    key: str,
    default: int,
    *,
    lower: int | None = None,
    upper: int | None = None,
    label: str | None = None,
) -> int:
    display = label or key
    raw = payload.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{display} must be an integer")
    try:
        parsed = int(raw)
    except (OverflowError, TypeError, ValueError):
        raise ValueError(f"{display} must be an integer") from None
    if isinstance(raw, float) and (not math.isfinite(raw) or not raw.is_integer()):
        raise ValueError(f"{display} must be an integer")
    if lower is not None and parsed < lower:
        raise ValueError(f"{display} must be >= {lower}")
    if upper is not None and parsed > upper:
        return upper
    return parsed


def payload_float(
    payload: dict,
    key: str,
    default: float,
    *,
    lower: float | None = None,
    upper: float | None = None,
    label: str | None = None,
) -> float:
    display = label or key
    raw = payload.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{display} must be a number")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{display} must be a number") from None
    if not math.isfinite(parsed):
        raise ValueError(f"{display} must be finite")
    if lower is not None and parsed < lower:
        raise ValueError(f"{display} must be >= {lower}")
    if upper is not None and parsed > upper:
        return upper
    return parsed
