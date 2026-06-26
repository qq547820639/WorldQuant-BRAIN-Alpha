"""Re-export from the ``official`` subpackage for backward compatibility."""
from __future__ import annotations

# Re-import standard library modules accessed as attributes by tests
# (e.g. ``monkeypatch.setattr(official.time, "monotonic", ...)``).
import time  # noqa: F401

from ._api import (
    OfficialBrainAPI,
    _standard_pagination_progress,
    logger,
)
from ._payload import (
    BrainAPIError,
    _looks_non_production_alpha_id,
    build_simulation_payload,
    normalize_metrics,
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
