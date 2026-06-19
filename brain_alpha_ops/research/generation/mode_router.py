"""GenerationModeRouter — weighted random routing to 3 generation modes."""

from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)


class GenerationModeRouter:
    """Routes generation requests to one of three modes based on configured ratios.

    Uses weighted random sampling. Internal counters track actual proportions.
    The ratio converges to the target over many calls (law of large numbers).

    Usage::

        router = GenerationModeRouter("70/20/10")
        mode = router.route()  # → "hypothesis_driven" (70% of the time)
    """

    VALID_MODES: tuple[str, ...] = (
        "hypothesis_driven",
        "experience_feedback",
        "random_exploration",
    )

    def __init__(self, ratio_str: str = "70/20/10") -> None:
        """Parse ratio string like "70/20/10" into per-mode weights."""
        self._hypothesis_ratio: float = 0.70
        self._experience_ratio: float = 0.20
        self._random_ratio: float = 0.10

        parts = ratio_str.strip().split("/")
        if len(parts) == 3:
            try:
                h, e, r = [float(p) for p in parts]
                total = h + e + r
                if total > 0:
                    self._hypothesis_ratio = h / total
                    self._experience_ratio = e / total
                    self._random_ratio = r / total
            except (ValueError, ZeroDivisionError):
                logger.warning(
                    "GenerationModeRouter: invalid ratio '%s', using default 70/20/10.",
                    ratio_str,
                )

        # Counters for monitoring actual proportions
        self._hypothesis_count: int = 0
        self._experience_count: int = 0
        self._random_count: int = 0

    def route(self) -> str:
        """Return the mode for the next generation call."""
        population = list(self.VALID_MODES)
        weights = [
            self._hypothesis_ratio,
            self._experience_ratio,
            self._random_ratio,
        ]
        chosen: str = random.choices(population, weights=weights, k=1)[0]

        if chosen == "hypothesis_driven":
            self._hypothesis_count += 1
        elif chosen == "experience_feedback":
            self._experience_count += 1
        else:
            self._random_count += 1

        return chosen

    def reset(self) -> None:
        """Reset internal counters."""
        self._hypothesis_count = 0
        self._experience_count = 0
        self._random_count = 0

    @property
    def actual_ratios(self) -> dict[str, float]:
        """Return observed ratios from counters."""
        total = (
            self._hypothesis_count
            + self._experience_count
            + self._random_count
        )
        if total == 0:
            return {
                "hypothesis_driven": 0.0,
                "experience_feedback": 0.0,
                "random_exploration": 0.0,
            }
        return {
            "hypothesis_driven": self._hypothesis_count / total,
            "experience_feedback": self._experience_count / total,
            "random_exploration": self._random_count / total,
        }


__all__ = ["GenerationModeRouter"]
