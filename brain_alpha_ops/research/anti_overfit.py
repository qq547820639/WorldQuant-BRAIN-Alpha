"""Compatibility exports for the canonical scoring anti-overfit service."""

from __future__ import annotations

from brain_alpha_ops.scoring.anti_overfit import (
    ANTI_OVERFIT_SCHEMA_VERSION,
    AntiOverfitService,
    evaluate_candidate,
)

__all__ = [
    "ANTI_OVERFIT_SCHEMA_VERSION",
    "AntiOverfitService",
    "evaluate_candidate",
]
