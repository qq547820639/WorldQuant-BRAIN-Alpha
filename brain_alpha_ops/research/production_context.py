"""Production context and adaptive strategy profile helpers."""

from __future__ import annotations

from typing import Any


ADAPTIVE_PROFILES = [
    {
        "name": "usa_standard",
        "label": "USA standard production",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "SUBINDUSTRY",
        "reason": "Baseline profile with broad coverage and subindustry neutralization.",
    },
    {
        "name": "usa_liquid",
        "label": "USA liquid universe",
        "region": "USA",
        "universe": "TOP1000",
        "delay": 1,
        "neutralization": "SUBINDUSTRY",
        "reason": "Narrow to a more liquid universe to reduce trading and coverage noise.",
    },
    {
        "name": "usa_sector",
        "label": "USA sector neutral",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "SECTOR",
        "reason": "Test whether broader sector neutralization preserves useful industry signals.",
        "min_tier": "ADVANCED",
    },
    {
        "name": "usa_market",
        "label": "USA market neutral",
        "region": "USA",
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "MARKET",
        "reason": "Relax industry neutralization while preserving market neutrality.",
        "min_tier": "ADVANCED",
    },
    {
        "name": "europe_standard",
        "label": "Europe standard production",
        "region": "EUR",
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "SUBINDUSTRY",
        "reason": "Port the same research logic to Europe to test regional robustness.",
    },
    {
        "name": "global_market",
        "label": "Global market neutral",
        "region": "GLB",
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "MARKET",
        "reason": "Expand to the global universe with a broad market-neutral profile.",
        "min_tier": "ADVANCED",
    },
    {
        "name": "china_standard",
        "label": "China standard production",
        "region": "CHN",
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "SUBINDUSTRY",
        "reason": "Try a differentiated regional market with official-context field validation.",
    },
]


def account_tier(user_profile: dict[str, Any] | None) -> str:
    profile = user_profile or {}
    return str(profile.get("account_tier", "BASIC")).upper()


def eligible_strategy_profiles(user_profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    tier = account_tier(user_profile)
    return [
        dict(profile)
        for profile in ADAPTIVE_PROFILES
        if tier == "ADVANCED" or not profile.get("min_tier")
    ]


def safe_field_ids(official_fields: list[dict[str, Any]] | None) -> list[str]:
    safe_fields: list[str] = []
    for field in official_fields or []:
        field_id = field.get("id") or field.get("name", "")
        field_type = str(field.get("type", "")).upper()
        if field_id and field_type != "VECTOR":
            safe_fields.append(str(field_id))
    return safe_fields


def build_production_context(
    user_profile: dict[str, Any],
    official_fields: list[dict[str, Any]],
    config: Any,
) -> dict[str, Any]:
    """Build live-verified production context after authentication."""
    tier = account_tier(user_profile)
    profiles = eligible_strategy_profiles(user_profile)
    fields = safe_field_ids(official_fields)
    return {
        "account_tier": tier,
        "eligible_profiles": profiles,
        "eligible_profiles_count": len(profiles),
        "safe_fields": fields,
        "safe_field_count": len(fields),
        "neutralization_available": (
            "SUBINDUSTRY" if tier != "ADVANCED" else "SUBINDUSTRY | SECTOR | MARKET"
        ),
        "type_available": "REGULAR",
        "instrument_type": "EQUITY",
        "_reserved": {},
    }
