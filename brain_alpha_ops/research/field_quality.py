"""Field eligibility helpers for alpha expression generation."""

from __future__ import annotations

from typing import Iterable

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import profile_expression

_NON_SIGNAL_FIELD_TOKENS = {
    "currency",
    "flag",
    "flags",
    "hierarchy",
    "parent",
    "parents",
    "rha",
    "rha2",
    "top",
    "topsp",
    "unit",
    "units",
}

_NON_SIGNAL_IDENTIFIER_TOKENS = {
    "cusip",
    "figi",
    "identifier",
    "isin",
    "sedol",
    "ticker",
}

_NON_SIGNAL_FIELD_IDS = {
    "country",
    "industry",
    "market",
    "sector",
    "subindustry",
    "top",
    "topsp",
    *_NON_SIGNAL_IDENTIFIER_TOKENS,
}

_NON_SIGNAL_EXACT_PREFIXES = (
    "top",
    "topsp",
)

_NON_SIGNAL_TRAILING_TOKENS = {
    "country",
    "industry",
    "market",
    "sector",
    "subindustry",
}


def _is_prefixed_numeric_token(token: str, prefixes: tuple[str, ...]) -> bool:
    return any(token.startswith(prefix) and token[len(prefix):].isdigit() for prefix in prefixes)


def _is_rha_token(token: str) -> bool:
    if not token.startswith("rha"):
        return False
    suffix = token[3:]
    return not suffix or suffix.isdigit()


def _is_non_signal_token(token: str) -> bool:
    return (
        token in _NON_SIGNAL_FIELD_TOKENS
        or token in _NON_SIGNAL_IDENTIFIER_TOKENS
        or _is_prefixed_numeric_token(token, _NON_SIGNAL_EXACT_PREFIXES)
        or _is_rha_token(token)
    )


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
    if _is_non_signal_token(name):
        return False
    field_type = ""
    if isinstance(field, dict):
        field_type = str(field.get("type") or field.get("fieldType") or field.get("dataType") or "")
    else:
        field_type = str(getattr(field, "type", "") or "")
    if field_type.upper() == "VECTOR":
        return False
    tokens = [token for token in name.split("_") if token]
    if any(_is_non_signal_token(token) for token in tokens):
        return False
    if tokens and tokens[-1] in _NON_SIGNAL_TRAILING_TOKENS:
        return False
    return True


def filter_generation_fields(fields: Iterable[object]) -> list[object]:
    """Return generation-eligible official fields while preserving order."""
    return [field for field in fields if is_generation_eligible_field(field)]


def generation_field_ids(fields: Iterable[object]) -> list[str]:
    """Return eligible field ids while preserving order."""
    return [field_id(field).lower() for field in fields if is_generation_eligible_field(field)]


def non_signal_generation_fields(candidate: Candidate) -> list[str]:
    """Return declared or parsed fields that are official metadata, not signals."""
    fields = {
        str(field).strip().lower()
        for field in (candidate.data_fields or [])
        if str(field).strip()
    }
    profile = profile_expression(candidate.expression)
    expression_fields = {str(field).strip().lower() for field in profile.fields if str(field).strip()}
    if any(str(operator).lower().startswith("group_") for operator in profile.operators):
        expression_fields -= {"market", "sector", "industry", "subindustry"}
    fields.update(expression_fields)
    return sorted(field for field in fields if not is_generation_eligible_field(field))
