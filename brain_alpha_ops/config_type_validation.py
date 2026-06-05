"""Type helpers for loading dataclass-backed config objects."""

from __future__ import annotations

import logging
from typing import Any, Union, get_args, get_origin, get_type_hints


logger = logging.getLogger(__name__)
_TYPE_HINTS_CACHE: dict[type, dict[str, Any]] = {}
_TYPE_HINTS_DIAGNOSTICS: dict[type, dict[str, Any]] = {}
_UNION_ORIGINS: set[Any] = {Union}
try:
    from types import UnionType as _UnionType
except ImportError:
    pass
else:
    _UNION_ORIGINS.add(_UnionType)


def field_type_hint(cls: type, field_name: str) -> Any:
    hints = _TYPE_HINTS_CACHE.get(cls)
    if hints is None:
        try:
            hints = get_type_hints(cls)
        except Exception as exc:
            message = str(exc)
            logger.warning(
                "failed to resolve type hints for %s; using empty fallback",
                getattr(cls, "__name__", cls),
                exc_info=True,
            )
            _TYPE_HINTS_DIAGNOSTICS[cls] = {
                "class": getattr(cls, "__name__", str(cls)),
                "error": message,
                "fallback": "Any",
            }
            hints = {}
        else:
            _TYPE_HINTS_DIAGNOSTICS.pop(cls, None)
        _TYPE_HINTS_CACHE[cls] = hints
    return hints.get(field_name, Any)


def type_hint_resolution_diagnostics(cls: type | None = None) -> list[dict[str, Any]]:
    """Return cached type-hint resolution fallbacks for monitoring/tests."""
    if cls is not None:
        diagnostic = _TYPE_HINTS_DIAGNOSTICS.get(cls)
        return [dict(diagnostic)] if diagnostic else []
    return [dict(item) for item in _TYPE_HINTS_DIAGNOSTICS.values()]


def clear_type_hint_resolution_caches() -> None:
    _TYPE_HINTS_CACHE.clear()
    _TYPE_HINTS_DIAGNOSTICS.clear()


def value_matches_type_hint(value: Any, expected: Any) -> bool:
    if expected is Any:
        return True
    if expected is None or expected is type(None):
        return value is None
    origin = get_origin(expected)
    if origin in _UNION_ORIGINS:
        return any(value_matches_type_hint(value, option) for option in get_args(expected))
    if origin is not None:
        if origin is list:
            return isinstance(value, list)
        if origin is dict:
            return isinstance(value, dict)
        if origin is set:
            return isinstance(value, set)
        if origin is tuple:
            return isinstance(value, tuple)
        return isinstance(value, origin) if isinstance(origin, type) else True
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(expected, type):
        return isinstance(value, expected)
    return True


def type_hint_name(expected: Any) -> str:
    if expected is Any:
        return "any"
    name = getattr(expected, "__name__", "")
    if name:
        return name
    return str(expected).replace("typing.", "")
