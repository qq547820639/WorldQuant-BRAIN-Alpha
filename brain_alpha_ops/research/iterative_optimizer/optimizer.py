"""``IterativeOptimizer`` class assembly with data model and helpers.

Consolidated from the original ``iterative_optimizer.py`` monolith. Holds the
``MutationResult`` dataclass, operator family / default window constants,
loader/json introspection helpers, the ``IterativeOptimizer`` class (with
``_MutationsMixin`` mixed in from ``mutations``), and the standalone
``window_perturb_expression`` / ``operator_substitute_expression`` /
``structure_refine_expression`` wrappers.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brain_alpha_ops.data.field_dataset_mapper import FieldDatasetMapper
from brain_alpha_ops.data.loader import OfficialDataLoader
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.failure_strategy_ranking import (
    get_strategy_for_failure as _ranking_strategies_for,
)
from brain_alpha_ops.research.failure_strategy_ranking import (
    load_failure_strategy_ranking as _load_failure_strategy_ranking,
)
from brain_alpha_ops.research.fallback_generation import normalize_operator_aliases

from .mutations import _MutationsMixin

# Preserve the original ``brain_alpha_ops.research.iterative_optimizer``
# logger name so downstream log filters and test caplog assertions keep
# working after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.iterative_optimizer")


# ═══════════════════════════════════════════════════════════════════════
# Operator family grouping based on BRAIN operator semantics.
# ═══════════════════════════════════════════════════════════════════════

_OPERATOR_FAMILIES: dict[str, list[str]] = {
    "ranking":       ["ts_rank", "rank", "group_rank"],
    "standardization": ["zscore", "scale", "group_zscore"],
    "moving_average":  ["ts_mean", "ts_sum", "ts_product", "ts_arg_max", "ts_arg_min"],
    "difference":      ["ts_delta", "ts_av_diff"],
    "volatility":      ["ts_std_dev", "ts_skewness", "ts_kurtosis"],
    "correlation":     ["ts_corr", "ts_covariance"],
    "winsorization":   ["winsorize"],
    "decay":           ["ts_decay_linear"],
    "step":            ["ts_step"],
    "minmax":          ["ts_min", "ts_max"],
}


# ═══════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MutationResult:
    """Result of a single mutation."""
    expression: str
    mode: str                        # field_swap | window_perturb | structure_refine | operator_substitute
    reason: str                      # Why this mutation was chosen.
    parent_failure: str              # Original failure dimension.
    metadata: dict[str, Any] = field(default_factory=dict)


# Default window candidates used by the standalone ``window_perturb_expression``
# helper when no IterativeOptimizer instance is supplied.
_DEFAULT_WINDOWS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]


# ═══════════════════════════════════════════════════════════════════════
# Loader / JSON introspection helpers
# ═══════════════════════════════════════════════════════════════════════

def _current_official_operator_names() -> frozenset[str]:
    # NOTE: ``parents[3]`` (not ``parents[2]``) because this module now lives
    # one directory deeper (``research/iterative_optimizer/optimizer.py``)
    # than the original ``research/iterative_optimizer.py`` monolith. The
    # resolved path remains ``<project_root>/data/official_operators.json``.
    path = Path(__file__).resolve().parents[3] / "data" / "official_operators.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    return frozenset(
        str(item.get("name", "")).lower()
        for item in payload
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    )


def _operator_names_from_loader(loader: Any) -> set[str]:
    get_operators = getattr(loader, "get_operators", None)
    if not callable(get_operators):
        return set()
    try:
        return {
            str(getattr(op, "name", "")).lower()
            for op in get_operators()
            if str(getattr(op, "name", "")).strip()
        }
    except Exception:
        logger.exception("iterative_optimizer: unexpected error")
        logger.warning("official operator metadata unavailable for iterative optimizer", exc_info=True)
        return set()


# ═══════════════════════════════════════════════════════════════════════
# IterativeOptimizer class
# ═══════════════════════════════════════════════════════════════════════

class IterativeOptimizer(_MutationsMixin):
    """Directed optimizer driven by diagnostic information.

    Converts diagnostics.diagnose() output into directed mutation operations,
    prioritizing the most severe failure dimensions.
    """

    # Failure dimension -> mutation strategy mapping.
    _FAILURE_TO_STRATEGY: dict[str, list[str]] = {
        "sharpe":              ["field_swap", "window_perturb", "structure_refine"],
        "fitness":             ["field_swap", "structure_refine", "operator_substitute"],
        "correlation":         ["field_swap_semantic", "operator_substitute", "structure_refine"],
        "turnover_platform":   ["longer_window", "structure_refine"],
        "turnover_quality":    ["longer_window", "structure_refine"],
        "turnover_low":        ["window_perturb", "field_swap"],
        "concentration":       ["structure_refine", "field_swap"],
        "margin":              ["structure_refine", "operator_substitute"],
        "sub_universe_sharpe": ["structure_refine", "field_swap"],
        "gate":                ["structure_refine", "field_swap"],
    }

    def __init__(
        self,
        loader: OfficialDataLoader | None = None,
        mapper: FieldDatasetMapper | None = None,
        rng: random.Random | None = None,
    ):
        """Initialize the directed iterative optimizer.

        Args:
            loader: OfficialDataLoader instance for field/operator metadata.
                Defaults to OfficialDataLoader.instance() if None.
            mapper: Optional FieldDatasetMapper for semantic field relationships.
            rng: Optional seeded Random instance for reproducible mutation
                selection. Defaults to Random(42) if None.
        """
        self._loader = loader or OfficialDataLoader.instance()
        self._mapper = mapper
        self._rng = rng or random.Random(42)
        self._official_operators = _operator_names_from_loader(self._loader) or set(_current_official_operator_names())
        self._family_alternatives = self._build_family_alternatives()
        # P2-15 (2026-06-13): strategy order is now learned from
        # ``ab_tests.jsonl`` rather than hard-coded. The legacy
        # ``_FAILURE_TO_STRATEGY`` class attribute is kept for backward
        # compatibility (and is what tests that do not seed AB data fall
        # back to); ``strategy_ranking`` is the data-driven overlay.
        self.strategy_ranking: dict[str, list[str]] = _load_failure_strategy_ranking()

    def _build_family_alternatives(self) -> dict[str, list[str]]:
        """Return same-family alternatives restricted to official operators."""
        alternatives: dict[str, list[str]] = {}
        for _family, ops in _OPERATOR_FAMILIES.items():
            official_ops = [op for op in ops if op in self._official_operators]
            for op in official_ops:
                alternatives[op] = [candidate for candidate in official_ops if candidate != op]
        return alternatives

    # Main entry point.

    def optimize(
        self,
        candidate: Candidate,
        diagnosis: dict[str, Any],
        max_mutations: int = 4,
    ) -> list[MutationResult]:
        """Generate a directed mutation sequence from a diagnosis.

        Failure dimensions are ordered by severity, and for each one the first
        executable mutation from its strategy list is chosen.

        Args:
            candidate: candidate Alpha to optimize
            diagnosis: output from diagnostics.diagnose()
            max_mutations: maximum number of mutations

        Returns:
            List of MutationResult objects (possibly fewer than max_mutations)
        """
        expression = normalize_operator_aliases(candidate.expression or "")
        fields = candidate.data_fields or []
        dataset_id = getattr(candidate, "dataset_id", "") or ""

        results: list[MutationResult] = []
        attempted_modes: set[str] = set()

        failed_dims = diagnosis.get("failed_dimensions", [])
        suggested_mutations = diagnosis.get("suggested_mutations", [])

        # Trace suggested modes without changing the existing strategy order.
        suggested_modes = [
            str(m.get("mutation_mode") or "")
            for m in suggested_mutations
            if isinstance(m, dict) and str(m.get("mutation_mode") or "").strip()
        ]

        for dim in failed_dims:
            if len(results) >= max_mutations:
                break

            # P2-15 (2026-06-13): prefer the data-driven ranking when the
            # optimizer instance has been told about new AB rows. The
            # hard-coded ``_FAILURE_TO_STRATEGY`` table is still the
            # baseline and is consulted when the learned ranking lacks
            # evidence for this dimension.
            learned = _ranking_strategies_for(dim, self.strategy_ranking)
            default = self._FAILURE_TO_STRATEGY.get(dim, ["field_swap", "structure_refine"])
            if not learned:
                logger.debug("No AB data for dimension '%s', using hardcoded defaults: %s", dim, default)
            strategies = learned or list(default)
            for strategy_index, strategy in enumerate(strategies):
                if len(results) >= max_mutations:
                    break
                if strategy in attempted_modes:
                    continue

                mut = self._apply_strategy(strategy, expression, fields, dataset_id, dim)
                if mut and mut.expression != expression:
                    mut.metadata = {
                        **dict(mut.metadata or {}),
                        "optimizer_trace": {
                            "schema_version": "optimizer-trace-v1",
                            "failed_dimension": str(dim),
                            "selected_strategy": str(strategy),
                            "strategy_order": [str(item) for item in strategies],
                            "strategy_index": strategy_index,
                            "suggested_modes": suggested_modes,
                            "official_api_called": False,
                            "submit_allowed": False,
                        },
                    }
                    results.append(mut)
                    attempted_modes.add(strategy)

        # If no mutation succeeded, try the generic structure_refine fallback.
        if not results and "structure_refine" not in attempted_modes:
            mut = self._apply_strategy("structure_refine", expression, fields, dataset_id, "general")
            if mut and mut.expression != expression:
                mut.metadata = {
                    **dict(mut.metadata or {}),
                    "optimizer_trace": {
                        "schema_version": "optimizer-trace-v1",
                        "failed_dimension": "general",
                        "selected_strategy": "structure_refine",
                        "strategy_order": ["structure_refine"],
                        "strategy_index": 0,
                        "suggested_modes": suggested_modes,
                        "official_api_called": False,
                        "submit_allowed": False,
                    },
                }
                results.append(mut)

        return results

    def _apply_strategy(
        self, strategy: str, expression: str, fields: list[str],
        dataset_id: str, failure_dim: str,
    ) -> MutationResult | None:
        """Execute a single strategy and return a MutationResult or None."""
        try:
            if strategy == "field_swap":
                new_expr = self.field_swap(expression, fields, dataset_id)
                return MutationResult(
                    expression=new_expr, mode="field_swap",
                    reason=f"Field swap to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "field_swap_semantic":
                new_expr = self.field_swap_semantic(expression, dataset_id)
                return MutationResult(
                    expression=new_expr, mode="field_swap_semantic",
                    reason=f"Semantic field swap to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "window_perturb":
                new_expr = self.window_perturb(expression)
                return MutationResult(
                    expression=new_expr, mode="window_perturb",
                    reason=f"Window perturb to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "longer_window":
                new_expr = self.window_perturb(expression, factor=2.0)
                return MutationResult(
                    expression=new_expr, mode="longer_window",
                    reason=f"Longer window to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "structure_refine":
                new_expr = self.structure_refine(expression)
                return MutationResult(
                    expression=new_expr, mode="structure_refine",
                    reason=f"Structure refine to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "operator_substitute":
                new_expr = self.operator_substitute(expression)
                return MutationResult(
                    expression=new_expr, mode="operator_substitute",
                    reason=f"Operator substitute to address {failure_dim}",
                    parent_failure=failure_dim,
                )
        except Exception:
            logger.warning(
                "iterative optimizer strategy failed: strategy=%s failure_dim=%s",
                strategy,
                failure_dim,
                exc_info=True,
            )
        return None


# ═══════════════════════════════════════════════════════════════════════
# Standalone helper functions for ``mutate_expression`` callers.
# ═══════════════════════════════════════════════════════════════════════

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
