"""Directed iterative optimizer that applies mutation operators from diagnostics.

It evolves the v2.1 "stall -> switch strategy" approach into failure-dimension
driven mutations:
- low sharpe/fitness -> field_swap + window_perturb
- high correlation -> field_swap_semantic + operator_substitute
- high turnover -> longer_window + structure_refine
- high concentration -> structure_refine

Each mutation operator can be used independently, and optimize() orders
mutations automatically from diagnostic results.

It integrates OfficialDataLoader and FieldDatasetMapper to support semantic
field/operator substitution.

Usage::

    from brain_alpha_ops.research.iterative_optimizer import IterativeOptimizer

    optimizer = IterativeOptimizer(loader, mapper)
    mutations = optimizer.optimize(candidate, diagnosis)
    for mut in mutations:
        logger.debug("Mutation: mode=%s reason=%s", mut.mode, mut.reason)
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
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

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _current_official_operator_names() -> frozenset[str]:
    path = Path(__file__).resolve().parents[2] / "data" / "official_operators.json"
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

# Alternative operators per family, used by operator_substitute.
_STRUCTURE_WRAPS: list[str] = ["winsorize", "zscore", "scale"]


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


# ═══════════════════════════════════════════════════════════════════════
# Directed iterative optimizer
# ═══════════════════════════════════════════════════════════════════════

class IterativeOptimizer:
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

    # Mutation operators

    def field_swap(
        self, expression: str, fields: list[str], dataset_id: str = ""
    ) -> str:
        """Replace a field in the expression with another field from the same class.

        Prefer fields from the same dataset. If the mapper is unavailable, fall
        back to rotating within the provided fields list.
        """
        if not fields or len(fields) < 2:
            return expression

        # Try to pull replacement fields from the same dataset via the mapper.
        if self._mapper and dataset_id:
            dataset_fields = self._mapper.fields_for(dataset_id)
            if dataset_fields and len(dataset_fields) > 1:
                alt_pool = [f for f in dataset_fields if f not in fields]
                if not alt_pool:
                    alt_pool = dataset_fields
            else:
                alt_pool = fields
        else:
            alt_pool = fields

        # Replace one of the fields appearing in the expression.
        target = self._rng.choice(fields) if fields else ""
        if not target or target not in expression:
            return expression

        alternatives = [f for f in alt_pool if f != target]
        if not alternatives:
            return expression
        replacement = self._rng.choice(alternatives)
        return self._safe_replace_token(expression, target, replacement)

    def field_swap_semantic(self, expression: str, dataset_id: str = "") -> str:
        """Replace a field in the expression with another field from the same class.

        Uses FieldDatasetMapper to find a closely related field from the same dataset.
        """
        expression = normalize_operator_aliases(expression)
        field_tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", expression)
        # Filter tokens that could be field names (exclude operators and numbers).
        operator_names = set(self._family_alternatives.keys())
        candidate_fields = [
            t for t in field_tokens
            if t not in operator_names and not t.isdigit()
            and len(t) > 1 and "_" in t
        ]

        if not candidate_fields:
            return expression

        target = self._rng.choice(candidate_fields)
        if self._mapper and dataset_id:
            replacements = self._mapper.fields_for(dataset_id)
            if replacements:
                alternatives = [f for f in replacements if f != target]
                if alternatives:
                    replacement = self._rng.choice(alternatives)
                    return self._safe_replace_token(expression, target, replacement)

        return expression

    def window_perturb(self, expression: str, factor: float = 0.2) -> str:
        """Perturb windows by +/-factor.

        Apply a random +/-random()*factor*value perturbation to all numbers in
        the expression, clamping the result to [3, 252].
        """
        def _perturb(m: re.Match) -> str:
            val = int(m.group(0))
            if val < 2 or val > 1000:  # Non-window numbers such as coefficients.
                return m.group(0)
            delta = self._rng.uniform(-factor, factor) * val
            new_val = int(val + delta)
            new_val = max(3, min(252, new_val))
            return str(new_val)

        return re.sub(r"\b\d+\b", _perturb, expression)

    def structure_refine(self, expression: str) -> str:
        """Add or remove a normalization layer.

        50% of the time this adds a normalization wrapper
        (winsorize/zscore/scale); otherwise it removes the outermost wrapper if
        one exists.
        """
        if self._rng.random() < 0.5:
            # Add a wrapper.
            wrap = self._rng.choice(_STRUCTURE_WRAPS)
            # Check whether the expression is already wrapped.
            stripped = expression.strip()
            for existing_wrap in _STRUCTURE_WRAPS:
                if stripped.startswith(f"{existing_wrap}(") and stripped.endswith(")"):
                    return expression  # Already wrapped; do not wrap again.
            # winsorize requires a std parameter.
            if wrap == "winsorize":
                return f"{wrap}({expression}, std=4)"
            return f"{wrap}({expression})"
        else:
            # Remove the outermost wrapper.
            stripped = expression.strip()
            for existing_wrap in _STRUCTURE_WRAPS:
                prefix = f"{existing_wrap}("
                if stripped.startswith(prefix) and stripped.endswith(")"):
                    inner = stripped[len(prefix):-1]
                    # Handle parameterized forms such as winsorize(expr, std=4).
                    if "," in inner:
                        # Keep the portion before the first comma up to the matching bracket.
                        inner = inner[:inner.rfind(",")].strip()
                    return inner if inner else expression
            return expression

    def operator_substitute(self, expression: str) -> str:
        """Replace an operator with another operator from the same family.

        Identify operators in the expression and replace one with a family peer.
        """
        # Extract all operator names.
        expression = normalize_operator_aliases(expression)
        op_pattern = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
        known_ops = set(self._family_alternatives.keys())

        substituted = False
        result = expression

        for op in op_pattern:
            if op in known_ops and op in self._family_alternatives:
                alternatives = self._family_alternatives[op]
                if alternatives:
                    replacement = self._rng.choice(alternatives)
                    # Safe replacement as a whole token, not a substring.
                    result = self._safe_replace_token(result, op, replacement)
                    substituted = True
                    break  # Replace only one operator at a time.

        return result if substituted else expression

    # Helpers

    @staticmethod
    def _safe_replace_token(text: str, old: str, new: str) -> str:
        """Safely replace a token, ensuring old is a whole word."""
        # Use word-boundary matching.
        pattern = r"\b" + re.escape(old) + r"\b"
        if not re.search(pattern, text):
            return text
        return re.sub(pattern, new, text, count=1)


# ═══════════════════════════════════════════════════════════════════════
# Standalone helper functions (compatible with existing mutate_expression calls).
# ═══════════════════════════════════════════════════════════════════════

_DEFAULT_WINDOWS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]


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
