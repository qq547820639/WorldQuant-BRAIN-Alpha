"""Small standalone helpers split out from ``_helpers.py``.

Kept in a separate module so ``_helpers.py`` stays within the project's
350-line hard limit. These symbols are re-imported by ``_helpers`` and
re-exported via the package ``__init__``, so existing imports
(``from brain_alpha_ops.research.generator._helpers import _safe_float``
or ``from brain_alpha_ops.research.generator import update_known_fields``)
continue to work unchanged.
"""
from __future__ import annotations


def update_known_fields(fields: list[dict]) -> None:
    """Legacy update (deprecated). Use OfficialDataLoader instead."""
    pass  # no-op in new architecture


def _safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
