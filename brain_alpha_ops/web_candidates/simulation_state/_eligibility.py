"""Eligibility helpers for Web candidate simulation state."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.expression_ast import profile_expression
from brain_alpha_ops.research.field_quality import is_generation_eligible_field
from brain_alpha_ops.submission_readiness import missing_official_metric_fields
from brain_alpha_ops.web_candidates.audit import scientific_audit_policy_reasons
from brain_alpha_ops.web_candidates.simulation_state._cooldown import is_simulation_cooling_down
from brain_alpha_ops.web_candidates.simulation_state._scoring import candidate_score

GROUP_KEY_FIELDS = frozenset({"market", "sector", "industry", "subindustry"})


def _candidate_dataset_key(candidate: dict[str, Any], default_dataset: str = "") -> str:
    settings = candidate.get("settings") if isinstance(candidate.get("settings"), dict) else {}
    return str(
        candidate.get("dataset_id")
        or candidate.get("dataset")
        or settings.get("dataset")
        or default_dataset
        or ""
    ).strip().lower()


def simulation_target_key(candidate: dict[str, Any], *, default_dataset: str = "") -> str:
    expression = "".join(str(candidate.get("expression") or "").split()).lower()
    if expression:
        dataset = _candidate_dataset_key(candidate, default_dataset)
        return f"expression:{expression}:dataset:{dataset}"
    alpha_id = str(candidate.get("alpha_id") or "").strip()
    return f"alpha_id:{alpha_id}" if alpha_id else ""


def dedupe_simulation_targets(candidates: list[dict[str, Any]], *, default_dataset: str = "") -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = simulation_target_key(candidate, default_dataset=default_dataset)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        targets.append(candidate)
    return targets


def eligible_for_simulation(candidate: dict[str, Any], min_score: float, *, now: float | None = None) -> bool:
    if is_simulation_cooling_down(candidate, now=now):
        return False
    if _has_complete_official_simulation_result(candidate):
        return False
    if candidate.get("simulation_id"):
        lifecycle = str(candidate.get("lifecycle_status", "")).lower()
        if "simulation_running" in lifecycle or "simulation_submitted" in lifecycle:
            return False
    if candidate_score(candidate) < min_score:
        return False
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return False
    if _has_explicit_unsupported_local_backtest(candidate, local_quality):
        return False
    if _has_non_signal_candidate_fields(candidate):
        return False
    if scientific_audit_policy_reasons(candidate):
        return False
    return True


def _has_non_signal_candidate_fields(candidate: dict[str, Any]) -> bool:
    raw_fields = candidate.get("data_fields")
    fields: set[str] = {
        str(field).strip().lower()
        for field in (raw_fields if isinstance(raw_fields, list) else [])
        if str(field).strip()
    }
    expression = str(candidate.get("expression") or "").strip()
    if expression:
        profile = profile_expression(expression)
        expression_fields = {str(field).strip().lower() for field in profile.fields if str(field).strip()}
        if any(str(operator).lower().startswith("group_") for operator in profile.operators):
            expression_fields -= GROUP_KEY_FIELDS
        fields.update(expression_fields)
    if not fields:
        return False
    return any(field and not is_generation_eligible_field(field) for field in fields)


def _has_explicit_unsupported_local_backtest(
    candidate: dict[str, Any],
    local_quality: dict[str, Any] | None = None,
) -> bool:
    """Block official simulation only when local backtest support is explicitly false."""
    sources: list[dict[str, Any]] = []
    if isinstance(local_quality, dict):
        sources.append(local_quality)
    if isinstance(candidate, dict):
        sources.append(candidate)
    for source in sources:
        support = source.get("local_backtest_support")
        if not isinstance(support, dict):
            continue
        supported = support.get("supported")
        if supported is False:
            return True
        if isinstance(supported, str) and supported.strip().lower() in {"false", "0", "no"}:
            return True
    return False


def _has_complete_official_simulation_result(candidate: dict[str, Any]) -> bool:
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    if not metrics:
        return False
    if missing_official_metric_fields(metrics):
        return False
    return str(metrics.get("pass_fail") or "").strip().upper() in {"PASS", "FAIL"}
