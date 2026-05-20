"""Canonical BRAIN platform contract values used across adapters and gates.

This module is intentionally dependency-free so configuration validation,
web payload parsing, and compliance checks can share the same source of truth
without importing heavier API or research modules.
"""

CANONICAL_THRESHOLDS = {
    "min_sharpe": 1.25,
    "min_sharpe_delay0": 2.0,
    "min_fitness": 1.0,
    "min_fitness_delay0": 1.3,
    "min_turnover": 0.01,
    "platform_max_turnover": 0.70,
    "max_self_correlation": 0.70,
    "max_weight_concentration": 0.10,
    "sub_universe_sharpe_min_ratio": 0.75,
}

CANONICAL_API_PATHS = {
    "authentication": "/authentication",
    "simulations": "/simulations",
    "data_sets": "/data-sets",
    "data_fields": "/data-fields",
    "operators": "/operators",
    "user_alphas": "/users/self/alphas",
    "user_profile": "/users/self",
    "alpha_check": "/alphas/{alpha_id}/check",
    "alpha_submit": "/alphas/{alpha_id}/submit",
    "alpha_detail": "/alphas/{alpha_id}",
    "alpha_correlations": "/alphas/correlations/check",
}

SUPPORTED_INSTRUMENT_TYPES = {"EQUITY"}
SUPPORTED_REGIONS = {"USA", "CHN", "EUR", "GLB"}
SUPPORTED_UNIVERSES = {"TOP3000", "TOP1000", "TOP500"}
SUPPORTED_DELAYS = {0, 1}
SUPPORTED_NEUTRALIZATIONS = {"SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"}
SUPPORTED_PASTEURIZATION = {"ON", "OFF"}
SUPPORTED_UNIT_HANDLING = {"VERIFY", "RAW", "NONE"}
SUPPORTED_NAN_HANDLING = {"ON", "OFF"}
SUPPORTED_LANGUAGES = {"FASTEXPR"}
SUPPORTED_ALPHA_TYPES = {"REGULAR", "POWER_POOL", "ATOM", "PYRAMID"}

CANONICAL_SETTINGS = {
    "instrumentType": SUPPORTED_INSTRUMENT_TYPES,
    "region": SUPPORTED_REGIONS,
    "universe": SUPPORTED_UNIVERSES,
    "delay": SUPPORTED_DELAYS,
    "neutralization": SUPPORTED_NEUTRALIZATIONS,
    "pasteurization": SUPPORTED_PASTEURIZATION,
    "unitHandling": SUPPORTED_UNIT_HANDLING,
    "nanHandling": SUPPORTED_NAN_HANDLING,
    "language": SUPPORTED_LANGUAGES,
    "type": SUPPORTED_ALPHA_TYPES,
}

CANONICAL_METRIC_NAMES = {
    "sharpe",
    "fitness",
    "turnover",
    "returns",
    "drawdown",
    "correlation",
    "weight_concentration",
    "sub_universe_sharpe",
    "margin",
    "subUniverseSize",
    "alphaSize",
}
