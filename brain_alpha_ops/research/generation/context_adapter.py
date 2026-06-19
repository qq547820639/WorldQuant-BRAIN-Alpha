"""ContextAdapter — adapts hypothesis preferences to available context."""

from __future__ import annotations

import random
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.research.hypothesis_library import Hypothesis


class ContextAdapter:
    """Adapts a hypothesis to available region/universe/delay context.

    Cross-filters hypothesis.adaptation preferences against what's actually
    available, producing a concrete context dict for Candidate construction.
    """

    # Default available context — used when no external info is provided
    DEFAULT_REGIONS: list[str] = [
        "USA",
        "EUROPE",
        "DEV",
        "ASIA",
        "DEV_EX_US",
        "FRONTIER",
    ]
    DEFAULT_UNIVERSES: list[str] = [
        "TOP3000",
        "TOP1000",
        "MID_LARGE_CAP",
        "SMID_CAP",
        "SMALL_CAP",
        "MICRO_CAP",
        "ALL_CAP",
    ]
    DEFAULT_DELAYS: list[int] = [1, 2, 3, 4, 5]

    def __init__(self) -> None:
        self._available_regions: list[str] = list(self.DEFAULT_REGIONS)
        self._available_universes: list[str] = list(self.DEFAULT_UNIVERSES)
        self._available_delays: list[int] = list(self.DEFAULT_DELAYS)

    def set_available_context(
        self,
        regions: list[str] | None = None,
        universes: list[str] | None = None,
        delays: list[int] | None = None,
    ) -> None:
        """Override the default available context."""
        if regions is not None:
            self._available_regions = list(regions)
        if universes is not None:
            self._available_universes = list(universes)
        if delays is not None:
            self._available_delays = list(delays)

    def adapt(self, hypothesis: "Hypothesis") -> dict[str, Any]:
        """Generate a concrete context dict for *hypothesis*.

        Returns:
            Dict with keys: region, universe, delay.
        """
        adapt = hypothesis.adaptation

        # Region: prefer hypothesis preferences, filter by availability
        preferred_regions = adapt.preferred_regions or self.DEFAULT_REGIONS
        suitable_regions = [
            r
            for r in preferred_regions
            if r in self._available_regions
            and r not in adapt.unsuitable_regions
        ]
        region = (
            random.choice(suitable_regions)
            if suitable_regions
            else (
                self._available_regions[0]
                if self._available_regions
                else self.DEFAULT_REGIONS[0]
            )
        )

        # Universe: prefer hypothesis preferences
        preferred_universes = (
            adapt.preferred_universes or self.DEFAULT_UNIVERSES
        )
        suitable_universes = [
            u for u in preferred_universes if u in self._available_universes
        ]
        universe = (
            random.choice(suitable_universes)
            if suitable_universes
            else (
                self._available_universes[0]
                if self._available_universes
                else self.DEFAULT_UNIVERSES[0]
            )
        )

        # Delay: prefer hypothesis preferences
        preferred_delays = adapt.preferred_delays or self.DEFAULT_DELAYS
        suitable_delays = [
            d for d in preferred_delays if d in self._available_delays
        ]
        delay = random.choice(suitable_delays) if suitable_delays else 1

        return {"region": region, "universe": universe, "delay": delay}


__all__ = ["ContextAdapter"]
