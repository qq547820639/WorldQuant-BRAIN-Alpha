"""Constants and type aliases for web config."""
from __future__ import annotations

from typing import Callable

from brain_alpha_ops.brain_api.canonical import (
    SUPPORTED_ALPHA_TYPES,
    SUPPORTED_DELAYS,
    SUPPORTED_NEUTRALIZATIONS,
    SUPPORTED_REGIONS,
    SUPPORTED_UNIVERSES,
)
from brain_alpha_ops.config import RunConfig


# Allowed base URLs for user-facing web payloads; production is the only
# runtime environment exposed by the web console.
_ALLOWED_BASE_URLS: dict[str, set[str]] = {
    "production": {"https://api.worldquantbrain.com"},
}

# Upper bounds for web payload numeric parameters.
_MAX_CANDIDATES = 1000
_MAX_VALIDATIONS = 100
_MAX_SIMULATIONS = 100
_MAX_CONCURRENT_SIMULATIONS = 20
_MAX_POOL_SIZE = 5000
_MAX_CYCLES = 10000
_MAX_CYCLE_PAUSE_SECONDS = 3600
_MAX_BACKTEST_BATCH_SIZE = 100

_VALID_REGIONS = SUPPORTED_REGIONS
_VALID_UNIVERSES = SUPPORTED_UNIVERSES
_VALID_DELAYS = SUPPORTED_DELAYS
_VALID_NEUTRALIZATIONS = SUPPORTED_NEUTRALIZATIONS
_VALID_TYPES = SUPPORTED_ALPHA_TYPES


RunConfigLoader = Callable[[], RunConfig]
RunConfigWriter = Callable[[RunConfig], object]
