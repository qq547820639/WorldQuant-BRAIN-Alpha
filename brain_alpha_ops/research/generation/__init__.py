"""Hypothesis-driven generation sub-package.

Exposes six component classes via lazy ``__getattr__`` re-export so that
importers of the historical path
``brain_alpha_ops.research.hypothesis_driven_generator`` (and the new path
``brain_alpha_ops.research.generation``) receive the same objects.
"""

from __future__ import annotations

import importlib
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "GenerationModeRouter": (
        "brain_alpha_ops.research.generation.mode_router",
        "GenerationModeRouter",
    ),
    "HypothesisSelector": (
        "brain_alpha_ops.research.generation.selectors",
        "HypothesisSelector",
    ),
    "ExpressionFamilySelector": (
        "brain_alpha_ops.research.generation.selectors",
        "ExpressionFamilySelector",
    ),
    "FieldSelector": (
        "brain_alpha_ops.research.generation.field_selector",
        "FieldSelector",
    ),
    "ContextAdapter": (
        "brain_alpha_ops.research.generation.context_adapter",
        "ContextAdapter",
    ),
    "HypothesisDrivenGenerator": (
        "brain_alpha_ops.research.generation.generator",
        "HypothesisDrivenGenerator",
    ),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    module_name, attr_name = target
    try:
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    except (ImportError, AttributeError) as exc:
        raise type(exc)(
            f"Failed to import {name!r} from {module_name!r}: {exc}"
        ) from exc
