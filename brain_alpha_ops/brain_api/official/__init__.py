"""Re-export from the ``official`` subpackage for backward compatibility."""
from __future__ import annotations

# Re-import standard library modules accessed as attributes by tests
# (e.g. ``monkeypatch.setattr(official.time, "monotonic", ...)``).
import time  # noqa: F401

from ..base import BrainAPIError  # noqa: F401
from ..official_helpers import (
    build_simulation_payload,  # noqa: F401
)
from ..official_helpers import (
    looks_non_production_alpha_id as _looks_non_production_alpha_id,  # noqa: F401
)
from ..official_helpers import (
    normalize_metrics,  # noqa: F401
)
from ._api import (
    OfficialBrainAPI,
    _standard_pagination_progress,
    logger,
)

__all__ = [
    "OfficialBrainAPI",
    "build_simulation_payload",
    "normalize_metrics",
    "BrainAPIError",
    "_looks_non_production_alpha_id",
    "_standard_pagination_progress",
    "logger",
]
