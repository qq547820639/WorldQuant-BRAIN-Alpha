"""Field eligibility helpers for alpha expression generation."""

from __future__ import annotations

from typing import Iterable


_NON_SIGNAL_FIELD_TOKENS = {
    "currency",
    "flag",
    "flags",
    "unit",
    "units",
}

_NON_SIGNAL_FIELD_IDS = {
    "country",
    "industry",
    "market",
    "sector",
    "subindustry",
}


def field_id(field: object) -> str:
    """Return the official field id/name for dataclass or dict records."""
    if isinstance(field, dict):
        return str(field.get("id") or field.get("name") or "").strip()
    return str(getattr(field, "id", "") or getattr(field, "name", "") or field or "").strip()


def is_generation_eligible_field(field: object) -> bool:
    """Whether an official field is suitable for expression generation.

    This does not decide whether a field exists in BRAIN.  It only keeps the
    generator from spending candidate slots on obvious metadata fields such as
    reporting currency or boolean flags.
    """
    name = field_id(field).lower()
    if not name:
        return False
    if name in _NON_SIGNAL_FIELD_IDS:
        return False
    field_type = ""
    if isinstance(field, dict):
        field_type = str(field.get("type") or field.get("fieldType") or field.get("dataType") or "")
    else:
        field_type = str(getattr(field, "type", "") or "")
    if field_type.upper() == "VECTOR":
        return False
    tokens = {token for token in name.split("_") if token}
    return not bool(tokens & _NON_SIGNAL_FIELD_TOKENS)


def filter_generation_fields(fields: Iterable[object]) -> list[object]:
    """Return generation-eligible official fields while preserving order."""
    return [field for field in fields if is_generation_eligible_field(field)]


def generation_field_ids(fields: Iterable[object]) -> list[str]:
    """Return eligible field ids while preserving order."""
    return [field_id(field).lower() for field in fields if is_generation_eligible_field(field)]
