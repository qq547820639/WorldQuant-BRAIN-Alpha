"""Standalone helper functions for ``mutate_expression`` callers.

Extracted from the original ``iterative_optimizer.py`` monolith. These
thin wrappers instantiate a default ``IterativeOptimizer`` and forward to
the corresponding mutation method, preserving the legacy
``window_perturb_expression`` / ``operator_substitute_expression`` /
``structure_refine_expression`` API.
"""

from __future__ import annotations

from brain_alpha_ops.research.fallback_generation import normalize_operator_aliases

from brain_alpha_ops.research.iterative_optimizer._optimizer import IterativeOptimizer


def window_perturb_expression(expression: str, factor: float = 0.2) -> str:
    """Standalone window perturbation helper for mutate_expression mode='window_perturb'."""
    opt = IterativeOptimizer()
    return opt.window_perturb(expression, factor)


def operator_substitute_expression(expression: str) -> str:
    """Standalone operator substitution helper for mutate_expression mode='operator_substitute'."""
    opt = IterativeOptimizer()
    return opt.operator_substitute(normalize_operator_aliases(expression))


def structure_refine_expression(expression: str) -> str:
    """Standalone structure refinement helper for mutate_expression mode='structure_refine'."""
    opt = IterativeOptimizer()
    return opt.structure_refine(expression)
