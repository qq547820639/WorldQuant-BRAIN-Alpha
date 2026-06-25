"""Optimization explanation and expression proof builders."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.web_candidates.decisions import candidate_decision_action
from brain_alpha_ops.web_candidates.optimization_explainability import (
    OPTIMIZATION_EXPLANATION_SCHEMA_VERSION,
)

from ._helpers import (
    _candidate_rejected_by_local_gate,
    _candidate_score,
    _int_list,
    _optional_float,
    _optional_int,
    _string_list,
)


def _attach_expression_proof(candidate: Candidate, *, proof: dict[str, Any], delta: dict[str, Any]) -> None:
    extra_fields = dict(candidate.extra_fields or {})
    extra_fields["official_context_proof"] = proof
    extra_fields["expression_delta"] = delta
    candidate.extra_fields = extra_fields
    quality = dict(candidate.quality_diagnosis or {})
    quality["official_context_proof"] = proof
    quality["expression_delta"] = delta
    candidate.quality_diagnosis = quality


def _attach_optimization_explanation(
    candidate: Candidate,
    *,
    parent: Candidate,
    search_row: dict[str, Any],
    proof: dict[str, Any],
    delta: dict[str, Any],
) -> None:
    explanation = _optimization_explanation(
        candidate,
        parent=parent,
        search_row=search_row,
        proof=proof,
        delta=delta,
    )
    extra_fields = dict(candidate.extra_fields or {})
    extra_fields["optimization_explanation"] = explanation
    candidate.extra_fields = extra_fields
    quality = dict(candidate.quality_diagnosis or {})
    quality["optimization_explanation"] = explanation
    candidate.quality_diagnosis = quality


def _optimization_explanation(
    candidate: Candidate,
    *,
    parent: Candidate,
    search_row: dict[str, Any],
    proof: dict[str, Any],
    delta: dict[str, Any],
) -> dict[str, Any]:
    metadata = search_row.get("metadata") if isinstance(search_row.get("metadata"), dict) else {}
    parent_diagnosis = parent.quality_diagnosis if isinstance(parent.quality_diagnosis, dict) else {}
    scorecard = candidate.scorecard if isinstance(candidate.scorecard, dict) else {}
    decision = candidate.extra_fields.get("production_decision") if isinstance(candidate.extra_fields, dict) else {}
    return {
        "schema_version": OPTIMIZATION_EXPLANATION_SCHEMA_VERSION,
        "source": "local_parameter_search",
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "parent": {
            "alpha_id": parent.alpha_id,
            "decision_action": candidate_decision_action(parent.to_dict()),
            "failed_dimensions": [str(item) for item in parent_diagnosis.get("failed_dimensions") or [] if str(item)],
            "blocking_reasons": [str(item) for item in parent_diagnosis.get("blocking_reasons") or [] if str(item)],
            "score": _candidate_score(parent.to_dict()),
        },
        "mutation": {
            "mode": candidate.mutation_type or str(search_row.get("mutation_mode") or "parameter_search"),
            "reason": str(metadata.get("reason") or search_row.get("reason") or ""),
            "parent_failure": str(metadata.get("parent_failure") or ""),
            "rank_input_index": _optional_int(metadata.get("rank_input_index")),
            "search_score": _optional_float(search_row.get("score")),
            "optimizer_trace": _optimizer_trace(metadata.get("optimizer_trace")),
        },
        "expression_change": _expression_change_summary(delta),
        "official_context": _official_context_explanation(proof),
        "decision": {
            "action": str((decision or {}).get("action") or candidate_decision_action(candidate.to_dict())),
            "next_state": str((decision or {}).get("next_state") or candidate.lifecycle_status or ""),
            "blocking": bool((decision or {}).get("blocking")),
            "decision_band": str(scorecard.get("decision_band") or ""),
            "score": _optional_float(scorecard.get("total_score")),
        },
        "next_action": "reject_local_prefilter" if _candidate_rejected_by_local_gate(candidate.to_dict()) else "retain_for_candidate_pool",
    }


def _expression_change_summary(delta: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": str(delta.get("schema_version") or "expression-delta.v1"),
        "changed": bool(delta.get("changed")),
        "fields_added": _string_list(delta.get("fields_added")),
        "fields_removed": _string_list(delta.get("fields_removed")),
        "operators_added": _string_list(delta.get("operators_added")),
        "operators_removed": _string_list(delta.get("operators_removed")),
        "windows_added": _int_list(delta.get("windows_added")),
        "windows_removed": _int_list(delta.get("windows_removed")),
    }


def _official_context_explanation(proof: dict[str, Any]) -> dict[str, Any]:
    dataset = proof.get("dataset") if isinstance(proof.get("dataset"), dict) else {}
    return {
        "schema_version": str(proof.get("schema_version") or "expression-official-context-proof.v1"),
        "source": str(proof.get("source") or "local_official_context_cache"),
        "passed": proof.get("passed") is True,
        "official_api_called": proof.get("official_api_called") is True,
        "reasons": _string_list(proof.get("reasons")),
        "missing_fields": _string_list(proof.get("missing_fields")),
        "missing_operators": _string_list(proof.get("missing_operators")),
        "dataset_mismatches": _string_list(proof.get("dataset_mismatches")),
        "dataset_id": str(dataset.get("id") or ""),
        "checked_fields": _string_list(proof.get("checked_fields")),
    }


def _optimizer_trace(value: Any) -> dict[str, Any]:
    trace = value if isinstance(value, dict) else {}
    return {
        "schema_version": str(trace.get("schema_version") or "optimizer-trace-v1"),
        "failed_dimension": str(trace.get("failed_dimension") or trace.get("parent_failure") or ""),
        "selected_strategy": str(trace.get("selected_strategy") or ""),
        "strategy_order": _string_list(trace.get("strategy_order")),
        "strategy_index": _optional_int(trace.get("strategy_index")),
        "suggested_modes": _string_list(trace.get("suggested_modes")),
        "official_api_called": trace.get("official_api_called") is True,
        "submit_allowed": trace.get("submit_allowed") is True,
    }


def _mark_official_context_proof_failed(candidate: Candidate, proof: dict[str, Any]) -> None:
    reasons = list(proof.get("reasons") or []) or ["official_context_proof_failed"]
    local = dict(candidate.local_quality or {})
    local_reasons = list(local.get("reasons") or [])
    for reason in reasons:
        text = "official_context_proof:" + str(reason)
        if text not in local_reasons:
            local_reasons.append(text)
    local["passed"] = False
    local["reasons"] = local_reasons
    local["official_context_proof"] = proof
    local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - 12.0, 2))
    candidate.local_quality = local


def _source_tags(child_tags: list[str], parent_tags: list[str]) -> list[str]:
    tags = list(child_tags or [])
    for tag in list(parent_tags or []) + ["local_only", "parameter_search", "candidate_pool_optimization"]:
        if tag and tag not in tags:
            tags.append(tag)
    return tags
