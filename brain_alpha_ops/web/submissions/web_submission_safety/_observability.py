"""Observability submission preflight.

Extracted from the former ``web_submission_safety.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.web_check_availability import build_context_health_explanation

from ._blocks import ObservabilityBuilder, SafeErrorMessage


def observability_submission_preflight(
    storage_dir: str,
    *,
    limit: int = 5000,
    top_n: int = 5,
    observability_builder: ObservabilityBuilder = build_research_observability_snapshot,
    safe_error_message: SafeErrorMessage = str,
) -> dict[str, Any]:
    try:
        snapshot = observability_builder(storage_dir, limit=limit, top_n=top_n, include_cloud=True)
    except Exception as exc:
        fallback_explanation = build_context_health_explanation({
            "risk_level": "unknown",
            "health_flags": ["observability_preflight_unavailable"],
            "blocking_flags": ["observability_preflight_unavailable"],
            "warning_flags": ["observability_preflight_unavailable"],
            "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
        })
        return {
            "ok": False,
            "schema_version": "submission_observability_preflight.v1",
            "risk_level": "unknown",
            "health_flags": ["observability_preflight_unavailable"],
            "blocking_flags": ["observability_preflight_unavailable"],
            "warning_flags": ["observability_preflight_unavailable"],
            "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
            "risk_explanation": fallback_explanation,
            "state_navigation": fallback_explanation.get("navigation"),
            "requires_confirmation": True,
            "error": safe_error_message(exc),
        }
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    official_call_guard = snapshot.get("official_call_guard") if isinstance(snapshot.get("official_call_guard"), dict) else {}
    blocking_flags = [str(item) for item in health.get("blocking_flags") or [] if str(item)]
    warning_flags = [str(item) for item in health.get("warning_flags") or [] if str(item)]
    health_flags = [str(item) for item in health.get("health_flags") or [] if str(item)]
    actions = [str(item) for item in health.get("actions") or [] if str(item)]
    risk_level = str(health.get("risk_level") or "unknown")
    flag_details = health.get("flag_details") if isinstance(health.get("flag_details"), dict) else {}
    context_explanation = build_context_health_explanation({
        "risk_level": risk_level,
        "health_flags": health_flags,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
        "actions": actions,
        "flag_details": flag_details,
        "source_schema_version": snapshot.get("schema_version", ""),
        "generated_at": snapshot.get("generated_at", ""),
    })
    return {
        "ok": True,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": risk_level,
        "health_flags": health_flags,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
        "actions": actions,
        "flag_details": flag_details,
        "risk_explanation": context_explanation if blocking_flags or warning_flags else {},
        "state_navigation": context_explanation.get("navigation") if blocking_flags else {},
        "requires_confirmation": bool(blocking_flags),
        "official_call_guard": official_call_guard,
        "source_schema_version": snapshot.get("schema_version", ""),
        "generated_at": snapshot.get("generated_at", ""),
    }
