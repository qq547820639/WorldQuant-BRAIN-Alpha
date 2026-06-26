"""Candidate dedupe, merge, and counting helpers."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.live_submit_readiness_assessment import float_or_none as _float_or_none

from ._thresholds import _int


def _candidate_key(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("alpha_id")
        or candidate.get("official_alpha_id")
        or candidate.get("simulation_id")
        or candidate.get("expression")
        or id(candidate)
    )


def _append_unique(items: list[str], value: str) -> list[str]:
    text = str(value).strip()
    if text and text not in items:
        items.append(text)
    return items


def _merged_string_list(*values: Any) -> list[str]:
    merged: list[str] = []
    for value in values:
        items = value if isinstance(value, list) else ([value] if value else [])
        for item in items:
            merged = _append_unique(merged, str(item))
    return merged


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _candidate_evidence_rank(candidate: dict[str, Any]) -> tuple[int, int, float]:
    reasons = candidate.get("blocking_reasons") if isinstance(candidate.get("blocking_reasons"), list) else []
    return (
        1 if candidate.get("eligible") is True else 0,
        -len(reasons),
        _float_or_none(candidate.get("score")) or 0.0,
    )


def _merge_assessed_candidate_evidence(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    base = incoming if _candidate_evidence_rank(incoming) > _candidate_evidence_rank(current) else current
    merged = dict(base)
    blocking_reasons = _merged_string_list(current.get("blocking_reasons"), incoming.get("blocking_reasons"))
    if current.get("eligible") is not incoming.get("eligible"):
        blocking_reasons = _append_unique(blocking_reasons, "duplicate_candidate_conflicting_evidence")
    missing_fields = _merged_string_list(
        current.get("missing_official_metric_fields"),
        incoming.get("missing_official_metric_fields"),
    )
    pending_checks = _merged_string_list(current.get("pending_official_checks"), incoming.get("pending_official_checks"))
    scientific_reasons = _merged_string_list(
        current.get("scientific_readiness_reasons"),
        incoming.get("scientific_readiness_reasons"),
    )
    candidate_sources = _merged_string_list(
        current.get("candidate_sources") or current.get("candidate_source"),
        incoming.get("candidate_sources") or incoming.get("candidate_source"),
    )
    merged["blocking_reasons"] = blocking_reasons
    merged["missing_official_metric_fields"] = missing_fields
    merged["pending_official_checks"] = pending_checks
    merged["scientific_readiness_reasons"] = scientific_reasons
    merged["candidate_sources"] = candidate_sources
    merged["eligible"] = bool(current.get("eligible") and incoming.get("eligible") and not blocking_reasons)
    return merged


def _dedupe_assessed_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = _candidate_key(candidate)
        if key not in deduped:
            deduped[key] = candidate
            order.append(key)
            continue
        deduped[key] = _merge_assessed_candidate_evidence(deduped[key], candidate)
    return [deduped[key] for key in order]


def _blocking_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        reasons = candidate.get("blocking_reasons")
        if not isinstance(reasons, list):
            continue
        for reason in reasons:
            key = str(reason)
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _merge_chain_summaries(items: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "local_only_jobs": 0,
        "official_api_called_jobs": 0,
        "official_validation_passed": 0,
        "officially_simulated": 0,
        "submission_ready": 0,
        "submitted_this_run": 0,
    }
    for item in items:
        summary = item.get("chain_summary") if isinstance(item.get("chain_summary"), dict) else item
        if not isinstance(summary, dict):
            continue
        for key in totals:
            totals[key] += _int(summary.get(key))
    return totals
