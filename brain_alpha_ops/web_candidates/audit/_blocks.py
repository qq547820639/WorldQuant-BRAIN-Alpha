"""Structured block builders for scientific audit records."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_profile_summary,
    expression_similarity,
)

from ._helpers import _is_int_like, _optional_float


def _expression_block(summary: dict[str, Any]) -> dict[str, Any]:
    profile = summary.get("expression_profile") if isinstance(summary.get("expression_profile"), dict) else {}
    return {
        "expression_canonical": str(summary.get("expression_canonical") or ""),
        "expression_fingerprint": str(summary.get("expression_fingerprint") or ""),
        "operators": [str(item) for item in profile.get("operators") or [] if str(item)],
        "fields": [str(item) for item in profile.get("fields") or [] if str(item)],
        "windows": [int(item) for item in profile.get("windows") or [] if _is_int_like(item)],
        "parsed": bool(profile.get("parsed")),
    }


def _lineage_block(
    row: dict[str, Any],
    *,
    parent: dict[str, Any] | None,
    search_row: dict[str, Any] | None,
    search_metadata: dict[str, Any],
) -> dict[str, Any]:
    lineage = search_metadata.get("lineage") if isinstance(search_metadata.get("lineage"), dict) else {}
    variant_reason = (
        search_metadata.get("reason")
        or (search_row or {}).get("reason")
        or ((row.get("submission") or {}) if isinstance(row.get("submission"), dict) else {}).get("variant_reason")
        or ""
    )
    return {
        "parent_alpha_id": str((parent or {}).get("alpha_id") or lineage.get("parent_alpha_id") or row.get("parent_id") or ""),
        "parent_expression_fingerprint": str(
            expression_profile_summary(str((parent or {}).get("expression") or lineage.get("parent_expression") or "")).get("expression_fingerprint")
            if ((parent or {}).get("expression") or lineage.get("parent_expression"))
            else ""
        ),
        "mutation_type": str(row.get("mutation_type") or (search_row or {}).get("mutation_mode") or ""),
        "variant_reason": str(variant_reason or ""),
    }


def _explainability_block(row: dict[str, Any]) -> dict[str, Any]:
    extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
    proof = row.get("official_context_proof") if isinstance(row.get("official_context_proof"), dict) else extra_fields.get("official_context_proof")
    delta = row.get("expression_delta") if isinstance(row.get("expression_delta"), dict) else extra_fields.get("expression_delta")
    optimization_explanation = (
        row.get("optimization_explanation")
        if isinstance(row.get("optimization_explanation"), dict)
        else extra_fields.get("optimization_explanation")
    )
    return {
        "official_context_proof": proof if isinstance(proof, dict) else {},
        "expression_delta": delta if isinstance(delta, dict) else {},
        "optimization_explanation": optimization_explanation if isinstance(optimization_explanation, dict) else {},
    }


def _evidence_block(
    row: dict[str, Any],
    *,
    feedback_sources: list[str] | None,
    scorecard: dict[str, Any],
    quality_diagnosis: dict[str, Any],
    local_quality: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    production_decision = decision if isinstance(decision, dict) else (
        row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
    )
    evidence = {
        "feedback_sources": sorted({str(item) for item in feedback_sources or [] if str(item)}),
        "metric_sources": _metric_sources(row, local_quality=local_quality),
        "score": _optional_float(scorecard.get("total_score", row.get("score"))),
        "decision_band": str(scorecard.get("decision_band") or row.get("decision_band") or ""),
        "production_action": str(production_decision.get("action") or ""),
        "production_reason_codes": [
            str(code)
            for code in production_decision.get("reason_codes") or quality_diagnosis.get("blocking_reasons") or []
            if str(code)
        ],
        "quality_status": str(quality_diagnosis.get("status") or row.get("lifecycle_status") or ""),
    }
    decision_evidence = (
        production_decision.get("decision_evidence")
        if isinstance(production_decision.get("decision_evidence"), dict)
        else {}
    )
    lifecycle_replay = (
        decision_evidence.get("lifecycle_replay")
        if isinstance(decision_evidence.get("lifecycle_replay"), dict)
        else {}
    )
    if lifecycle_replay:
        evidence["lifecycle_replay"] = lifecycle_replay
    return evidence


def _metric_sources(row: dict[str, Any], *, local_quality: dict[str, Any]) -> list[str]:
    sources = {"scorecard"}
    if local_quality:
        sources.add("local_quality")
    if isinstance(local_quality.get("local_backtest"), dict):
        sources.add("local_backtest_prefilter")
    if row.get("official_alpha_id") or row.get("simulation_id") or row.get("official_metrics"):
        sources.add("official_evidence")
    return sorted(sources)


def _parent_similarity(expression: str, parent_expression: str) -> float | None:
    if not expression or not parent_expression:
        return None
    return expression_similarity(expression, parent_expression)


def _similarity_sources(row: dict[str, Any]) -> list[str]:
    sources: set[str] = set()
    for key in ("cloud_correlation_risk", "cloud_similarity_risk", "similarity_risk"):
        if isinstance(row.get(key), dict):
            sources.add(key)
    extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
    if isinstance(extra_fields.get("expression_index"), dict):
        sources.add("expression_index")
    return sorted(sources)
