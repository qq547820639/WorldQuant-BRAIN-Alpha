"""Canonical compliance checks for config-derived values.

Contains checks 1-3:
* Threshold zero deviation
* API path alignment
* Settings enum alignment
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════
# Check 1: Threshold Zero Deviation
# ═══════════════════════════════════════════════════════════════════════

def _check_thresholds(run_config: Any) -> dict[str, Any]:
    """Verify all configured thresholds match BRAIN canonical values."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS

    thresholds = run_config.ops.thresholds
    results: dict[str, dict[str, Any]] = {}
    deviations: list[str] = []

    for key, canonical in CANONICAL_THRESHOLDS.items():
        try:
            configured = getattr(thresholds, key, None)
        except AttributeError:
            configured = None

        match = configured == canonical
        results[key] = {
            "configured": configured,
            "canonical": canonical,
            "match": match,
            "deviation": (configured - canonical) if configured is not None and not match else 0,
        }
        if not match:
            deviations.append(f"{key}: configured={configured}, canonical={canonical}")

    return {
        "name": "threshold_zero_deviation",
        "passed": len(deviations) == 0,
        "details": results,
        "deviations": deviations,
        "total": len(CANONICAL_THRESHOLDS),
        "matching": sum(1 for r in results.values() if r["match"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 2: API Path Alignment
# ═══════════════════════════════════════════════════════════════════════

def _check_api_paths(run_config: Any) -> dict[str, Any]:
    """Verify all configured API paths match BRAIN canonical paths."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS

    api_config = run_config.ops.official_api
    deviations: list[str] = []
    results: dict[str, dict[str, Any]] = {}

    path_mapping = {
        "authentication": "authentication_path",
        "simulations": "simulations_path",
        "data_categories": "data_categories_path",
        "data_sets": "data_sets_path",
        "data_set_detail": "data_set_path_template",
        "data_fields": "data_fields_path",
        "data_field_detail": "data_field_path_template",
        "operators": "operators_path",
        "user_alphas": "user_alphas_path",
        "user_profile": "user_profile_path",
        "alpha_check": "alpha_check_path_template",
        "alpha_submit": "alpha_submit_path_template",
        "alpha_detail": "alpha_path_template",
        "alpha_correlations": "alpha_correlations_path",
    }

    for canonical_key, config_attr in path_mapping.items():
        canonical_path = CANONICAL_API_PATHS[canonical_key]
        configured = getattr(api_config, config_attr, None)
        match = configured == canonical_path
        results[config_attr] = {
            "configured": configured,
            "canonical": canonical_path,
            "match": match,
        }
        if not match:
            deviations.append(
                f"{config_attr}: configured='{configured}', canonical='{canonical_path}'"
            )

    # Check base_url
    base_match = api_config.base_url == "https://api.worldquantbrain.com"
    results["base_url"] = {
        "configured": api_config.base_url,
        "canonical": "https://api.worldquantbrain.com",
        "match": base_match,
    }
    if not base_match:
        deviations.append(
            f"base_url: configured='{api_config.base_url}', canonical='https://api.worldquantbrain.com'"
        )

    return {
        "name": "api_path_alignment",
        "passed": len(deviations) == 0,
        "details": results,
        "deviations": deviations,
        "total": len(path_mapping) + 1,
        "matching": sum(1 for r in results.values() if r["match"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 3: Settings Enum Alignment
# ═══════════════════════════════════════════════════════════════════════

def _check_settings_enums(run_config: Any) -> dict[str, Any]:
    """Verify settings values are within BRAIN allowed enum sets."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS

    settings = run_config.ops.settings
    results: dict[str, dict[str, Any]] = {}
    deviations: list[str] = []

    # Check settings fields against canonical enums
    setting_checks = [
        ("instrumentType", settings.instrumentType),
        ("region", settings.region),
        ("universe", settings.universe),
        ("neutralization", settings.neutralization),
        ("pasteurization", settings.pasteurization),
        ("unitHandling", settings.unitHandling),
        ("nanHandling", settings.nanHandling),
        ("language", settings.language),
        ("type", settings.type),
    ]

    for field_name, value in setting_checks:
        allowed = CANONICAL_SETTINGS.get(field_name, set())
        if not isinstance(allowed, (set, frozenset)):
            allowed = set()
        match = value in allowed
        results[field_name] = {
            "configured": value,
            "allowed": sorted(allowed),
            "match": match,
        }
        if not match:
            deviations.append(
                f"{field_name}: configured='{value}', allowed={sorted(allowed)}"
            )

    # Check delay separately (integer, not string enum)
    if settings.delay not in CANONICAL_SETTINGS.get("delay", {0, 1}):
        deviations.append(
            f"delay: configured={settings.delay}, allowed=[0, 1]"
        )
        results["delay"] = {
            "configured": settings.delay,
            "allowed": sorted(CANONICAL_SETTINGS.get("delay", {0, 1})),
            "match": False,
        }
    else:
        results["delay"] = {
            "configured": settings.delay,
            "allowed": sorted(CANONICAL_SETTINGS.get("delay", {0, 1})),
            "match": True,
        }

    return {
        "name": "settings_enum_alignment",
        "passed": len(deviations) == 0,
        "details": results,
        "deviations": deviations,
        "total": len(results),
        "matching": sum(1 for r in results.values() if r["match"]),
    }
