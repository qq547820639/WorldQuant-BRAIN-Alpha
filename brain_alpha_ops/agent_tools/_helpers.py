"""Standalone helper functions for the agent tool facade.

These helpers convert domain objects to plain dicts and wrap the shared
``tool_error`` formatter.  They are module-level functions so that the
``BrainAlphaToolbox`` class and its mixins can reference them without
introducing a circular import on the package ``__init__``.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.errors import tool_error

MAX_TOOL_CANDIDATES = 100


def _tool_error(exc: Exception, error_code: str, **context: Any) -> dict[str, Any]:
    return tool_error(exc, error_code=error_code, **context)


def _field_to_dict(field: Any) -> dict[str, Any]:
    return {
        "id": getattr(field, "id", ""),
        "name": getattr(field, "name", ""),
        "category": getattr(field, "category", ""),
        "type": getattr(field, "type", ""),
        "dataset_id": getattr(getattr(field, "dataset", None), "id", ""),
        "coverage": getattr(field, "coverage", None),
    }


def _operator_to_dict(operator: Any) -> dict[str, Any]:
    return {
        "id": getattr(operator, "id", ""),
        "name": getattr(operator, "name", ""),
        "category": getattr(operator, "category", getattr(operator, "op_type", "")),
        "arity": getattr(operator, "arity", None),
    }


def _dataset_to_dict(dataset: Any) -> dict[str, Any]:
    return {
        "id": getattr(dataset, "id", ""),
        "name": getattr(dataset, "name", ""),
        "category": getattr(dataset, "category", ""),
        "field_count": getattr(dataset, "field_count", None),
    }
