"""Dynamic Alpha theme engine — data structures and constants.

Defines the ``ThemeTemplate`` dataclass plus the window/group/production
constants used by the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ThemeTemplate:
    """A dynamically generated Alpha expression template."""
    id: str
    name: str
    category: str                      # "momentum", "value", "quality", "volatility", "hybrid", etc.
    expression: str                    # expression with {FIELD} / {WINDOW} placeholders
    field_slots: list[str] = field(default_factory=list)
    description: str = ""


# High-structure templates are used first when the active dataset has enough
# eligible fields.  They improve candidate quality by changing the expression
# itself: multi-field signal construction, time-series normalization, and
# cross-sectional risk control.  Submission gates still require official PASS.
PRODUCTION_STRUCTURE_SKELETONS: list[str] = [
    "rank(winsorize(ts_delta({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}) + {FIELD_C} - {FIELD_D}, std=4))",
    "rank(winsorize(ts_mean({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}) + {FIELD_C} - {FIELD_D}, std=4))",
    "zscore(winsorize(ts_delta({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}) + {FIELD_C} - {FIELD_D}, std=4))",
    "group_rank(winsorize(ts_delta({FIELD_A}, {WINDOW}) / ts_std_dev({FIELD_B}, {WINDOW2}) + {FIELD_C} - {FIELD_D}, std=4), {GROUP})",
]

# Default window sizes for template generation
# M-01 v3: Extended window set — fine-grained short windows for reversal/liquidity,
# standard mid windows for momentum/quality, long windows for value/growth anchoring.
DEFAULT_WINDOWS = [2, 3, 5, 8, 10, 12, 15, 18, 20, 25, 30, 40, 50, 60, 90, 120, 150, 180, 200, 252]
DEFAULT_GROUPS = ["sector", "industry", "subindustry"]
