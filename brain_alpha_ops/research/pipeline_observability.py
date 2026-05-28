"""Observability refresh and generation-guidance helpers for the research pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.observability import error_payload
from brain_alpha_ops.redaction import redact_error_message

from .observability import (
    actionable_duplicate_expression_buckets,
    build_research_observability_snapshot,
    observability_context,
)

logger = logging.getLogger(__name__)


EventCallback = Callable[..., None]
GuardSnapshot = Callable[[], dict]


@dataclass
class ObservabilityRefreshResult:
    throttle: dict[str, Any]
    generation_guidance: dict[str, Any]
    blocking_flags: list[str]


def failed_generation_guidance(cycle: int, generator_type: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": "observability_generation_guidance_summary.v1",
        "active": False,
        "cycle": cycle,
        "source": "research_observability",
        "status": "refresh_failed",
        "risk_level": "unknown",
        "health_flags": [],
        "duplicate_ratio": 0.0,
        "avoid_expression_count": 0,
        "top_duplicate_expressions": [],
        "top_duplicate_fingerprints": [],
        "applied_to_generator": False,
        "generator_type": generator_type,
        "error": message,
    }


def failed_observability_throttle(
    *,
    generation_guidance: dict[str, Any],
    message: str,
    guard_snapshot: dict,
) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "refresh_failed",
        "risk_level": "unknown",
        "active": False,
        "health_flags": [],
        "blocking_flags": [],
        "warning_flags": [],
        "recommended_actions": [],
        "error": message,
        "generation_guidance": dict(generation_guidance),
        "official_call_guard": guard_snapshot,
    }


def apply_observability_generation_guidance(
    *,
    snapshot: dict,
    context: dict,
    cycle: int,
    generator: Any,
    event: EventCallback,
) -> dict[str, Any]:
    expression_index = snapshot.get("expression_index") if isinstance(snapshot.get("expression_index"), dict) else {}
    top_duplicates = actionable_duplicate_expression_buckets(expression_index.get("top_duplicates") or [])[:10]
    health_flags = list(context.get("health_flags") or [])
    duplicate_ratio = float(context.get("duplicate_ratio") or 0.0)
    active = bool(top_duplicates or "high_duplicate_expression_ratio" in health_flags)
    guidance = {
        "schema_version": "observability_generation_guidance.v1",
        "source": "research_observability",
        "risk_level": context.get("risk_level", "unknown"),
        "health_flags": health_flags,
        "duplicate_ratio": duplicate_ratio,
        "avoid_expressions": top_duplicates,
    }
    setter = getattr(generator, "set_observability_guidance", None)
    applied_to_generator = False
    guidance_status = "idle" if not active else "no_generator_hook"
    guidance_error = ""
    if callable(setter):
        try:
            setter(guidance)
            applied_to_generator = True
            guidance_status = "applied" if active else "idle"
        except Exception as exc:
            guidance_error = redact_error_message(exc, max_length=180)
            guidance_status = "apply_failed"
            logger.warning(
                "observability generation guidance failed in cycle %s for %s: %s",
                cycle,
                type(generator).__name__,
                guidance_error,
                exc_info=True,
            )
            event(
                "observability_generation_guidance_failed",
                f"Cycle {cycle}: observability generation guidance could not be applied; generation continues.",
                data=error_payload(
                    exc,
                    error_code="OBSERVABILITY_GENERATION_GUIDANCE_FAILED",
                    max_length=180,
                    phase="observability_generation",
                    cycle=cycle,
                    generator_type=type(generator).__name__,
                ),
                level="WARN",
            )
    compact_guidance = {
        "schema_version": "observability_generation_guidance_summary.v1",
        "active": active,
        "cycle": cycle,
        "source": "research_observability",
        "status": guidance_status,
        "risk_level": context.get("risk_level", "unknown"),
        "health_flags": health_flags[:5],
        "duplicate_ratio": duplicate_ratio,
        "avoid_expression_count": len(top_duplicates),
        "top_duplicate_expressions": [
            str(row.get("expression_canonical") or row.get("expression") or "")[:160]
            for row in top_duplicates[:5]
            if isinstance(row, dict)
        ],
        "top_duplicate_fingerprints": [
            str(row.get("expression_fingerprint") or "")[:16]
            for row in top_duplicates[:5]
            if isinstance(row, dict) and row.get("expression_fingerprint")
        ],
        "applied_to_generator": applied_to_generator,
        "generator_type": type(generator).__name__,
    }
    if guidance_error:
        compact_guidance["error"] = guidance_error
    if active and applied_to_generator:
        event(
            "observability_generation_guidance_applied",
            f"Cycle {cycle}: observability diversified generation "
            f"(duplicates={len(top_duplicates)}, duplicate_ratio={duplicate_ratio}).",
            data={
                "cycle": cycle,
                "observability_generation_guidance": guidance,
                "observability_generation_guidance_summary": compact_guidance,
            },
            level="INFO",
        )
    return compact_guidance


def ready_observability_throttle(
    *,
    context: dict,
    generation_guidance: dict[str, Any],
    guard_snapshot: dict,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "ready",
        "risk_level": context.get("risk_level", "unknown"),
        "health_flags": list(context.get("health_flags") or []),
        "blocking_flags": list(context.get("blocking_flags") or []),
        "warning_flags": list(context.get("warning_flags") or []),
        "recommended_actions": list(context.get("recommended_actions") or context.get("recommendations") or []),
        "backtest_failure_rate": context.get("backtest_failure_rate", 0.0),
        "retryable_error_count": context.get("retryable_error_count", 0),
        "generated_at": context.get("generated_at", ""),
        "generation_guidance": dict(generation_guidance),
        "official_call_guard": guard_snapshot,
    }


def refresh_observability_throttle(
    *,
    storage_dir: str,
    cycle: int,
    generator: Any,
    event: EventCallback,
    guard_snapshot: GuardSnapshot,
    observability_builder: Callable[..., dict[str, Any]] = build_research_observability_snapshot,
) -> ObservabilityRefreshResult:
    try:
        snapshot = observability_builder(
            storage_dir,
            limit=5000,
            top_n=5,
            include_cloud=True,
        )
        context = observability_context(snapshot, top_n=5)
        guidance = apply_observability_generation_guidance(
            snapshot=snapshot,
            context=context,
            cycle=cycle,
            generator=generator,
            event=event,
        )
    except Exception as exc:
        message = redact_error_message(exc, max_length=180)
        guidance = failed_generation_guidance(cycle, type(generator).__name__, message)
        throttle = failed_observability_throttle(
            generation_guidance=guidance,
            message=message,
            guard_snapshot=guard_snapshot(),
        )
        logger.warning("observability refresh failed in cycle %s: %s", cycle, message, exc_info=True)
        event(
            "observability_refresh_failed",
            f"Cycle {cycle}: observability refresh failed; local generation continues.",
            data=error_payload(
                exc,
                error_code="OBSERVABILITY_REFRESH_FAILED",
                max_length=180,
                phase="observability",
                cycle=cycle,
            ),
            level="WARN",
        )
        return ObservabilityRefreshResult(throttle=throttle, generation_guidance=guidance, blocking_flags=[])
    throttle = ready_observability_throttle(
        context=context,
        generation_guidance=guidance,
        guard_snapshot=guard_snapshot(),
    )
    throttle["ok"] = True
    return ObservabilityRefreshResult(
        throttle=throttle,
        generation_guidance=guidance,
        blocking_flags=list(throttle.get("blocking_flags") or []),
    )
