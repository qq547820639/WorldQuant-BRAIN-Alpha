"""WQB-compatible read-only filtering helpers for official BRAIN queries."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .base import BrainAPIError

_OPENING = {"[": True, "(": False}
_CLOSING = {"]": True, ")": False}
_INFINITE_VALUES = {"", "inf", "+inf", "infinity", "+infinity", "-inf", "-infinity", "none", "null", "*"}
_WQB_OPTION_ALIASES = {
    "instrumentType": "instrument_type",
    "instrument_type": "instrument_type",
    "region": "region",
    "delay": "delay",
    "universe": "universe",
    "dataset": "dataset",
    "datasetId": "dataset",
    "dataset_id": "dataset",
    "dataSetId": "dataset",
    "data_set_id": "dataset",
}


@dataclass(frozen=True)
class FilterRange:
    """Represent WQB-style inclusive/exclusive range query constraints."""

    lower: Any = None
    upper: Any = None
    include_lower: bool = True
    include_upper: bool = True

    @classmethod
    def parse(cls, value: Any) -> "FilterRange":
        if isinstance(value, FilterRange):
            return value
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise BrainAPIError("FilterRange tuple/list values must contain exactly two entries")
            return cls(value[0], value[1])
        text = str(value or "").strip()
        if not text:
            return cls()
        if text[0] in _OPENING and text[-1:] in _CLOSING:
            parts = [part.strip() for part in text[1:-1].split(",", 1)]
            if len(parts) != 2:
                raise BrainAPIError(f"invalid FilterRange expression: {text}")
            return cls(
                _range_endpoint(parts[0]),
                _range_endpoint(parts[1]),
                include_lower=_OPENING[text[0]],
                include_upper=_CLOSING[text[-1]],
            )
        return cls(text, text)

    def to_params(self, field_name: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if not field_name:
            raise BrainAPIError("filter field name must be non-empty")
        if _has_endpoint(self.lower):
            params[f"{field_name}{'>=' if self.include_lower else '>'}"] = self.lower
        if _has_endpoint(self.upper):
            params[f"{field_name}{'<=' if self.include_upper else '<'}"] = self.upper
        return params


def build_filter_params(field_name: str, value: Any) -> dict[str, Any]:
    """Return query params for scalar or range-valued official API filters."""
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        if stripped[:1] in _OPENING and stripped[-1:] in _CLOSING:
            return FilterRange.parse(stripped).to_params(field_name)
    if isinstance(value, (FilterRange, list, tuple)):
        return FilterRange.parse(value).to_params(field_name)
    return {field_name: value}


def normalize_wqb_options(
    options: Mapping[str, Any] | None,
    *,
    allowed: set[str] | frozenset[str] | None = None,
    label: str = "options",
) -> dict[str, Any]:
    """Normalize WQB-style option keys without silently accepting unknowns."""
    if options is None:
        return {}
    if not isinstance(options, Mapping):
        raise BrainAPIError(f"{label} must be a mapping")
    allowed_keys = set(allowed) if allowed is not None else None
    normalized: dict[str, Any] = {}
    for raw_key, value in options.items():
        key = str(raw_key or "").strip()
        canonical = _WQB_OPTION_ALIASES.get(key)
        if not canonical:
            raise BrainAPIError(f"unsupported {label} key: {raw_key}")
        if allowed_keys is not None and canonical not in allowed_keys:
            raise BrainAPIError(f"unsupported {label} key for this surface: {raw_key}")
        if _is_blank(value):
            continue
        existing = normalized.get(canonical)
        if existing is not None and str(existing) != str(value):
            raise BrainAPIError(f"conflicting {label} values for {canonical}")
        normalized[canonical] = value
    return normalized


def resolve_compat_value(name: str, explicit: Any, options: Mapping[str, Any], *, label: str = "options") -> Any:
    """Resolve explicit keyword arguments against normalized WQB options."""
    option_value = options.get(name)
    if _is_blank(explicit):
        return option_value
    if option_value is not None and str(option_value) != str(explicit):
        raise BrainAPIError(f"conflicting {name} between explicit argument and {label}")
    return explicit


def resolve_compat_alias(name: str, primary: Any, alias: Any, *, alias_name: str) -> Any:
    """Resolve two same-meaning parameters and fail closed on conflicts."""
    if _is_blank(alias):
        return primary
    if not _is_blank(primary) and str(primary) != str(alias):
        raise BrainAPIError(f"conflicting {name} and {alias_name}")
    return alias


def clamp_query_limit(limit: int, *, maximum: int, label: str) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError) as exc:
        raise BrainAPIError(f"{label} limit must be an integer") from exc
    if value <= 0 or value > maximum:
        raise BrainAPIError(f"{label} limit must be in 1..{maximum}")
    return value


def clamp_query_offset(offset: int, *, limit: int, max_window: int, label: str) -> int:
    try:
        value = int(offset)
    except (TypeError, ValueError) as exc:
        raise BrainAPIError(f"{label} offset must be an integer") from exc
    max_offset = max(0, int(max_window) - int(limit))
    if value < 0 or value > max_offset:
        raise BrainAPIError(f"{label} offset must be in 0..{max_offset}")
    return value


def expected_pages(total: int, limit: int) -> int:
    try:
        total_value = max(0, int(total or 0))
        limit_value = max(0, int(limit or 0))
    except (TypeError, ValueError):
        return 0
    return int(math.ceil(total_value / limit_value)) if total_value and limit_value else 0


def _range_endpoint(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _INFINITE_VALUES:
        return None
    return text


def _has_endpoint(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in _INFINITE_VALUES:
        return False
    return True


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
