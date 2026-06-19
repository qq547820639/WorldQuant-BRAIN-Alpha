"""Hypothesis-Driven Alpha Generator — structured generation from market hypotheses.

Implements a 3-mode generation strategy:
  - hypothesis_driven (70% default): 6-step pipeline from hypothesis to Candidate
  - experience_feedback (20% default): biased ThemeEngine using winning patterns
  - random_exploration (10% default): pure fallback to DynamicThemeEngine

This module is a backward-compatible shim.  The six component classes are
now defined in ``brain_alpha_ops.research.generation``.  This module
re-exports them so existing import paths continue to work unchanged.

Usage::

    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator

    library = HypothesisLibrary("brain_alpha_ops/research/hypotheses").load_all()
    gen = HypothesisDrivenGenerator(loader, mapper, theme_engine, selector, library)
    candidates = gen.generate(20, dataset_id="analyst4")
"""
from __future__ import annotations

from brain_alpha_ops.research.generation.context_adapter import ContextAdapter
from brain_alpha_ops.research.generation.field_selector import FieldSelector
from brain_alpha_ops.research.generation.generator import HypothesisDrivenGenerator
from brain_alpha_ops.research.generation.mode_router import GenerationModeRouter
from brain_alpha_ops.research.generation.selectors import (
    ExpressionFamilySelector,
    HypothesisSelector,
)

_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD = 0.90

__all__ = [
    "HypothesisDrivenGenerator",
    "GenerationModeRouter",
    "HypothesisSelector",
    "ExpressionFamilySelector",
    "FieldSelector",
    "ContextAdapter",
]
