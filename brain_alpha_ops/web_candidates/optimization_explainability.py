"""Shared explainability helpers for local candidate optimization."""

from __future__ import annotations

from typing import Any

OPTIMIZATION_EXPLANATION_SCHEMA_VERSION = "candidate-optimization-explanation-v1"
OPTIMIZATION_EXPLANATION_SUMMARY_SCHEMA_VERSION = "candidate-optimization-explanation-summary-v1"
OPTIMIZATION_CONCENTRATION_AUDIT_SCHEMA_VERSION = "optimization-concentration-audit-v1"


def optimization_explanation_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize local optimization explanations without changing decisions."""

    total = 0
    explained = 0
    official_context_passed = 0
    official_api_called = 0
    submit_allowed = 0
    next_actions: dict[str, int] = {}
    mutation_modes: dict[str, int] = {}
    parent_failures: dict[str, int] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        total += 1
        extra_fields = candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}
        explanation = extra_fields.get("optimization_explanation")
        if not isinstance(explanation, dict) or explanation.get("schema_version") != OPTIMIZATION_EXPLANATION_SCHEMA_VERSION:
            continue
        explained += 1
        if explanation.get("official_api_called") is True:
            official_api_called += 1
        if explanation.get("submit_allowed") is True:
            submit_allowed += 1
        official_context = explanation.get("official_context") if isinstance(explanation.get("official_context"), dict) else {}
        if official_context.get("passed") is True:
            official_context_passed += 1
        mutation = explanation.get("mutation") if isinstance(explanation.get("mutation"), dict) else {}
        _bump(mutation_modes, str(mutation.get("mode") or "unknown"))
        _bump(parent_failures, str(mutation.get("parent_failure") or "unknown"))
        _bump(next_actions, str(explanation.get("next_action") or "unknown"))
    return {
        "schema_version": OPTIMIZATION_EXPLANATION_SUMMARY_SCHEMA_VERSION,
        "candidate_count": total,
        "explained_count": explained,
        "missing_explanation_count": max(0, total - explained),
        "official_context_passed_count": official_context_passed,
        "official_api_called_count": official_api_called,
        "submit_allowed_count": submit_allowed,
        "non_submit_boundary_intact": official_api_called == 0 and submit_allowed == 0,
        "mutation_modes": dict(sorted(mutation_modes.items())),
        "parent_failures": dict(sorted(parent_failures.items())),
        "next_actions": dict(sorted(next_actions.items())),
        "concentration_audit": optimization_concentration_audit(
            explained_count=explained,
            mutation_modes=mutation_modes,
            parent_failures=parent_failures,
        ),
    }


def optimization_concentration_audit(
    *,
    explained_count: int,
    mutation_modes: dict[str, int],
    parent_failures: dict[str, int],
) -> dict[str, Any]:
    """Return a local-only concentration audit for optimizer explainability.

    This is diagnostic metadata only: it never changes the expressions, ranking,
    or submit policy.  It helps the Web UI and later gates see when a batch is
    mostly repeating one mutation strategy or one parent failure dimension.
    """

    top_mode, top_mode_count = _top_counter_item(mutation_modes)
    top_failure, top_failure_count = _top_counter_item(parent_failures)
    mode_share = _share(top_mode_count, explained_count)
    failure_share = _share(top_failure_count, explained_count)
    unique_modes = len([key for key, count in mutation_modes.items() if key and count > 0])
    unique_failures = len([key for key, count in parent_failures.items() if key and count > 0])
    reasons: list[str] = []
    risk = "none"

    if explained_count > 1 and unique_modes <= 1:
        risk = "high"
        reasons.append("single_mutation_mode")
    elif explained_count >= 3 and mode_share >= 0.6:
        risk = "moderate"
        reasons.append("mutation_mode_concentration")

    if explained_count > 1 and unique_failures <= 1:
        risk = "high"
        reasons.append("single_parent_failure")
    elif explained_count >= 3 and failure_share >= 0.6:
        if risk == "none":
            risk = "moderate"
        reasons.append("parent_failure_concentration")

    return {
        "schema_version": OPTIMIZATION_CONCENTRATION_AUDIT_SCHEMA_VERSION,
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "explained_count": int(explained_count),
        "unique_mutation_mode_count": unique_modes,
        "unique_parent_failure_count": unique_failures,
        "top_mutation_mode": top_mode,
        "top_mutation_mode_count": top_mode_count,
        "top_mutation_mode_share": mode_share,
        "top_parent_failure": top_failure,
        "top_parent_failure_count": top_failure_count,
        "top_parent_failure_share": failure_share,
        "concentration_risk": risk,
        "risk_reasons": sorted(set(reasons)),
    }


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key or "unknown"] = counter.get(key or "unknown", 0) + 1


def _top_counter_item(counter: dict[str, int]) -> tuple[str, int]:
    if not counter:
        return "", 0
    key, count = max(sorted(counter.items()), key=lambda item: item[1])
    return str(key), int(count)


def _share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(float(count) / float(total), 4)
