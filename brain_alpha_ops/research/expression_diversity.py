"""Expression diversity checker — prevents skeleton convergence in alpha generation.

The module analyzes expression skeletons (operator structure without specific
field names) to detect when generated expressions are too structurally similar
to existing ones, which leads to BRAIN cloud correlation rejections.

Problem: 75%+ of generated alphas fail BRAIN cloud correlation checks because
they share the same structural skeleton even though field names differ.

Solution: Track expression skeletons, detect convergence, and force structural
diversification when similarity exceeds threshold.

Usage::

    from brain_alpha_ops.research.expression_diversity import ExpressionDiversityGuard
    guard = ExpressionDiversityGuard()
    if guard.is_converged(new_expression, pool_expressions):
        # Force mutation to a different skeleton
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.fallback_generation import normalize_operator_aliases

_OFFICIAL_OPERATOR_FALLBACK = frozenset(
    {
        "abs", "add", "and", "bucket", "days_from_last_change", "densify",
        "divide", "equal", "greater", "greater_equal", "group_backfill",
        "group_mean", "group_neutralize", "group_rank", "group_scale",
        "group_zscore", "hump", "if_else", "inverse", "is_nan",
        "kth_element", "last_diff_value", "less", "less_equal", "log",
        "max", "min", "multiply", "normalize", "not", "not_equal", "or",
        "power", "quantile", "rank", "reverse", "scale", "sign",
        "signed_power", "sqrt", "subtract", "trade_when", "ts_arg_max",
        "ts_arg_min", "ts_av_diff", "ts_backfill", "ts_corr",
        "ts_count_nans", "ts_covariance", "ts_decay_linear", "ts_delay",
        "ts_delta", "ts_mean", "ts_product", "ts_quantile", "ts_rank",
        "ts_regression", "ts_scale", "ts_std_dev", "ts_step", "ts_sum",
        "ts_zscore", "vec_avg", "vec_sum", "winsorize", "zscore",
    }
)

@lru_cache(maxsize=1)
def _current_official_operator_names() -> frozenset[str]:
    path = Path(__file__).resolve().parents[2] / "data" / "official_operators.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _OFFICIAL_OPERATOR_FALLBACK
    names = {
        str(item.get("name", "")).lower()
        for item in payload
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    return frozenset(names or _OFFICIAL_OPERATOR_FALLBACK)

@dataclass
class DiversityReport:
    """Report of expression diversity for a candidate pool."""

    total_expressions: int = 0
    unique_skeletons: int = 0
    skeleton_diversity_ratio: float = 1.0
    most_common_skeleton: str = ""
    most_common_count: int = 0
    is_converged: bool = False
    convergence_rate: float = 0.0
    recommended_action: str = "none"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_expressions": self.total_expressions,
            "unique_skeletons": self.unique_skeletons,
            "skeleton_diversity_ratio": round(self.skeleton_diversity_ratio, 4),
            "most_common_skeleton": self.most_common_skeleton,
            "most_common_count": self.most_common_count,
            "is_converged": self.is_converged,
            "convergence_rate": round(self.convergence_rate, 4),
            "recommended_action": self.recommended_action,
            "details": self.details,
        }

class ExpressionDiversityGuard:
    """Guard against expression skeleton convergence in alpha generation.

    Tracks structural skeletons of expressions and detects when too many
    expressions share the same structural pattern, triggering forced
    diversification strategies.

    A "skeleton" is the expression with all field names and numeric literals
    replaced by placeholders: rank(returns) and rank(market_cap) both become
    rank(FIELD). ts_mean(close, 20) and ts_mean(volume, 60) both become
    ts_mean(FIELD, N).
    """

    # Maximum allowed share of any single skeleton in the pool
    MAX_SKELETON_CONCENTRATION: float = 0.30
    # Minimum unique skeletons required for a healthy diverse pool
    MIN_UNIQUE_SKELETONS: int = 3
    # Threshold at which we force diversification
    DIVERSITY_ALERT_THRESHOLD: float = 0.50

    def __init__(
        self,
        *,
        max_skeleton_concentration: float | None = None,
        min_unique_skeletons: int | None = None,
    ) -> None:
        self._max_concentration = max_skeleton_concentration or self.MAX_SKELETON_CONCENTRATION
        self._min_unique = min_unique_skeletons or self.MIN_UNIQUE_SKELETONS
        self._skeleton_history: Counter[str] = Counter()

    def skeleton(self, expression: str) -> str:
        """Extract the structural skeleton of an expression.

        Replaces:
        - Field names (word characters following operators) → FIELD
        - Numeric literals (integer or float numbers) → N
        - Whitespace is normalized

        Examples:
            rank(returns) → rank(FIELD)
            ts_mean(close, 20) → ts_mean(FIELD, N)
            group_rank(ts_delta(volume,5), sector) → group_rank(ts_delta(FIELD, N), FIELD)
        """
        # Normalize whitespace
        expr = " ".join(normalize_operator_aliases(expression).split())

        # Replace numeric literals (integers and floats) with N
        expr = re.sub(r"\b\d+(?:\.\d+)?\b", "N", expr)

        # Replace field names inside parentheses
        # Fields are word-like tokens that aren't operators
        KNOWN_OPERATORS = set(_current_official_operator_names())

        # Tokenize and rebuild
        tokens = re.findall(r"[a-zA-Z_]\w*|\S", expr)
        result_parts = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in KNOWN_OPERATORS or token in ("(", ")", ",", "+", "-", "*", "/", "^"):
                result_parts.append(token)
            elif token == "N":
                result_parts.append("N")
            elif token[0].isalpha() and token not in KNOWN_OPERATORS:
                # This is a field name — check if it follows an operator
                if i > 0 and tokens[i - 1] in KNOWN_OPERATORS:
                    result_parts.append("FIELD")
                elif i > 1 and tokens[i - 1] == "(" and tokens[i - 2] in KNOWN_OPERATORS:
                    result_parts.append("FIELD")
                else:
                    # Check if this is a field inside a function call
                    # Simplification: any non-operator, non-number alpha token is a field
                    result_parts.append("FIELD")
            else:
                result_parts.append(token)
            i += 1

        skeleton = " ".join(result_parts)
        # Final normalization: collapse multiple spaces
        skeleton = re.sub(r"\s+", " ", skeleton).strip()
        return skeleton

    def is_converged(
        self,
        new_expression: str,
        pool_expressions: list[str],
    ) -> bool:
        """Check if adding new_expression would cause skeleton convergence.

        Args:
            new_expression: the new expression to check.
            pool_expressions: existing expressions in the pool.

        Returns:
            True if adding this expression would exceed the concentration limit.
        """
        new_skeleton = self.skeleton(new_expression)
        skeletons = [self.skeleton(expr) for expr in pool_expressions]

        # Count how many pool expressions share this skeleton
        same_skeleton_count = sum(1 for s in skeletons if s == new_skeleton)

        # Include the new expression itself
        total_after = len(pool_expressions) + 1
        same_after = same_skeleton_count + 1

        concentration = same_after / max(total_after, 1)
        return concentration > self._max_concentration

    def analyze_pool(self, expressions: list[str]) -> DiversityReport:
        """Analyze expression diversity for a candidate pool.

        Returns a DiversityReport with convergence status and recommendations.

        Args:
            expressions: list of expression strings in the pool.
        """
        if not expressions:
            return DiversityReport(
                total_expressions=0,
                recommended_action="generate_more",
            )

        skeletons = [self.skeleton(expr) for expr in expressions]
        skeleton_counts = Counter(skeletons)

        total = len(expressions)
        unique = len(skeleton_counts)
        most_common = skeleton_counts.most_common(1)
        most_common_skel, most_common_count = most_common[0] if most_common else ("", 0)

        diversity_ratio = unique / max(total, 1)
        max_concentration = most_common_count / max(total, 1)

        is_converged = max_concentration > self._max_concentration or unique < self._min_unique

        if is_converged:
            if max_concentration > self._max_concentration:
                action = "force_skeleton_mutation"
            else:
                action = "force_exploration"
        elif diversity_ratio < self.DIVERSITY_ALERT_THRESHOLD:
            action = "diversity_alert"
        else:
            action = "none"

        # Build skeleton distribution details
        distribution = {
            skel: {
                "count": count,
                "ratio": round(count / total, 4),
                "examples": [
                    expr
                    for expr in expressions
                    if self.skeleton(expr) == skel
                ][:3],
            }
            for skel, count in skeleton_counts.most_common(10)
        }

        return DiversityReport(
            total_expressions=total,
            unique_skeletons=unique,
            skeleton_diversity_ratio=round(diversity_ratio, 4),
            most_common_skeleton=most_common_skel,
            most_common_count=most_common_count,
            is_converged=is_converged,
            convergence_rate=round(max_concentration, 4),
            recommended_action=action,
            details={
                "skeleton_distribution": distribution,
                "total_unique_skeletons": unique,
                "max_concentration": round(max_concentration, 4),
                "concentration_threshold": self._max_concentration,
                "min_unique_threshold": self._min_unique,
            },
        )

    def force_diversify(
        self,
        expression: str,
        *,
        pool_expressions: list[str] | None = None,
        max_attempts: int = 10,
    ) -> list[str]:
        """Generate structurally diverse variants of an expression.

        This is a heuristic approach that suggests structural mutations
        to break skeleton convergence. It does not perform actual expression
        generation but provides mutation direction guidance.

        Args:
            expression: the converged expression.
            pool_expressions: optional existing pool for diversity check.
            max_attempts: maximum mutation directions to suggest.

        Returns:
            List of diversification strategies (not actual expressions).
        """
        strategies: list[str] = []
        current_skeleton = self.skeleton(expression)

        # Strategy 1: Change operator family (ts_ → group_ or vice versa)
        if "ts_" in expression:
            strategies.append("replace_time_series: switch ts_ operators to group_ cross-sectional")
        else:
            strategies.append("add_time_series: add ts_mean, ts_std_dev, or ts_delta operators")

        # Strategy 2: Increase nesting depth
        depth = expression.count("(")
        if depth < 3:
            strategies.append("increase_nesting: add one more layer of operator nesting")

        # Strategy 3: Change the core field family
        strategies.append("change_field_family: replace price/volume fields with fundamental fields")

        # Strategy 4: Add neutralization
        if "neutralize" not in expression.lower():
            strategies.append("add_neutralization: add group_neutralize")

        # Strategy 5: Change window parameters significantly
        strategies.append("change_windows: use substantially different lookback windows")

        # Strategy 6: Add winsorize for robustness
        if "winsorize" not in expression:
            strategies.append("add_winsorize: add winsorize(FIELD, 0.01) for robustness")

        # Strategy 7: Combine two independent sub-signals
        if "+" not in expression and "-" not in expression:
            strategies.append("combine_signals: combine two independent sub-signals with +")

        # Strategy 8: Switch to official time-series decay weighting
        strategies.append("use_ts_decay_linear: replace simple mean with ts_decay_linear for recency weighting")

        return strategies[:max_attempts]
