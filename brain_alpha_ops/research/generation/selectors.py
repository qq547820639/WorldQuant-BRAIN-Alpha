"""HypothesisSelector and ExpressionFamilySelector — weighted selection helpers."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.research.hypothesis_library import (
        ExpressionFamily,
        Hypothesis,
        HypothesisLibrary,
    )


class HypothesisSelector:
    """Selects a hypothesis weighted by experience weights.

    Higher experience_weights.overall → higher selection probability.
    Maintains a recently-used exclusion set to avoid repetition.
    """

    DEFAULT_RECENCY_SIZE: int = 3

    def __init__(self, library: "HypothesisLibrary") -> None:
        self._library = library
        self._recently_used: list[str] = []
        self._max_recency: int = self.DEFAULT_RECENCY_SIZE

    def select(self) -> "Hypothesis | None":
        """Select a hypothesis by weighted random choice.

        Returns None if no hypotheses are available.
        """
        all_h = self._library.get_all()
        if not all_h:
            return None

        # Build candidate pool, excluding recently used if possible
        excluded_ids: set[str] = set(self._recently_used[-self._max_recency:])
        pool = [h for h in all_h if h.id not in excluded_ids]
        if not pool:
            # All hypotheses recently used — fall back to full pool
            pool = all_h
            excluded_ids.clear()

        # Weighted random selection by experience_weights.overall, scaled by
        # the feedback weight recorded via ``HypothesisLibrary.adjust_weight``
        # (closes the hypothesis feedback loop: prod_correlation penalties
        # reduce a hypothesis's selection probability, diversity rewards
        # increase it). Defaults to 1.0 (neutral) when no feedback recorded.
        weights = [
            max(0.01, h.experience_weights.overall * self._library.get_hypothesis_weight(h.id))
            for h in pool
        ]
        chosen: "Hypothesis" = random.choices(pool, weights=weights, k=1)[0]

        # Update recency tracker
        self._recently_used.append(chosen.id)
        if len(self._recently_used) > self._max_recency * 3:
            self._recently_used = self._recently_used[-self._max_recency:]

        return chosen

    def exclude_recently_used(self, max_recency: int) -> None:
        """Set the number of recently-used hypotheses to exclude."""
        self._max_recency = max(1, max_recency)


class ExpressionFamilySelector:
    """Selects an expression family and window from a hypothesis.

    Weighted by expression_family_weights and window_weights respectively.
    """

    def __init__(self) -> None:
        pass

    def select(self, hypothesis: "Hypothesis") -> "ExpressionFamily | None":
        """Select an expression family weighted by its experience weight."""
        families = hypothesis.expression_families
        if not families:
            return None
        weights = [max(0.01, ef.weight) for ef in families]
        chosen: "ExpressionFamily" = random.choices(
            families, weights=weights, k=1
        )[0]
        return chosen

    def select_window(
        self,
        expr_family: "ExpressionFamily",
        window_weights: dict[str, float] | None = None,
    ) -> int:
        """Select a window size from the expression family's window list.

        Window selection is weighted by *window_weights* (from experience_weights)
        if provided, otherwise uniform random.
        """
        windows = expr_family.get_all_windows()
        if not windows:
            return 12  # sensible default

        if window_weights:
            weights = [
                max(0.01, window_weights.get(str(w), 1.0)) for w in windows
            ]
        else:
            weights = None

        if weights is not None and sum(weights) > 0:
            chosen: int = random.choices(windows, weights=weights, k=1)[0]
        else:
            chosen = random.choice(windows)
        return chosen


__all__ = ["HypothesisSelector", "ExpressionFamilySelector"]
