"""Safe-accessor helpers extracted from phase.py to satisfy the project's
350-line module budget. Kept private to the web.handlers package."""

from __future__ import annotations

from typing import Any


def _safe_bool(obj: Any, method_name: str) -> bool:
    try:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            return bool(fn())
    except (AttributeError, TypeError, ValueError):
        pass
    return False


def _format_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    formatter = getattr(value, "isoformat", None)
    if callable(formatter):
        return str(formatter())
    text = str(value).strip()
    return text or None


def _safe_int(obj: Any, method_name: str, *, default: int = 0) -> int:
    try:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            result = fn()
            return int(result) if result is not None else default
    except (AttributeError, TypeError, ValueError):
        pass
    return default
