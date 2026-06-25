"""Optimized candidate preparation pipeline."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate, new_id, utc_now
from brain_alpha_ops.research.alpha_quality import (
    build_alpha_output_config,
    diagnose_alpha_candidate,
)
from brain_alpha_ops.research.expression_official_context import (
    expression_delta,
    expression_official_context_proof,
)
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)
from brain_alpha_ops.research.field_quality import non_signal_generation_fields
from brain_alpha_ops.research.generator import (
    extract_fields,
    extract_operators,
    local_quality,
)
from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
from brain_alpha_ops.research.local_backtest_gate import (
    apply_local_backtest_gate,
    blocked_local_gate,
)
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.web_candidates.decisions import (
    annotate_candidate_decision,
)

from ._explainability import (
    _attach_expression_proof,
    _attach_optimization_explanation,
    _mark_official_context_proof_failed,
    _source_tags,
)


def _prepare_optimized_candidate(
    candidate: Candidate,
    *,
    parent: Candidate,
    search_row: dict[str, Any],
    run_config: RunConfig,
    dataset_id: str,
    alpha_output_config: dict[str, Any],
    local_backtest_engine: LocalBacktestEngine,
) -> Candidate:
    candidate.alpha_id = new_id("alpha")
    candidate.official_alpha_id = ""
    candidate.simulation_id = ""
    candidate.official_metrics = {}
    candidate.dataset_id = candidate.dataset_id or dataset_id
    candidate.parent_id = parent.alpha_id
    candidate.mutation_type = candidate.mutation_type or str(search_row.get("mutation_mode") or "parameter_search")
    candidate.source_tags = _source_tags(candidate.source_tags, parent.source_tags)
    candidate.local_quality = local_quality(candidate, run_config.ops.budget.min_local_quality_score)
    proof = expression_official_context_proof(
        candidate.expression,
        dataset_id=candidate.dataset_id or dataset_id,
        data_dir=run_config.ops.storage_dir,
    )
    delta = expression_delta(candidate.expression, parent.expression)
    _attach_expression_proof(candidate, proof=proof, delta=delta)
    if proof.get("passed") is not True:
        _mark_official_context_proof_failed(candidate, proof)
    apply_local_backtest_gate(
        candidate,
        engine=local_backtest_engine,
        cache_key=candidate.dataset_id or run_config.ops.settings.dataset or "default",
        extract_fields=extract_fields,
        extract_operators=extract_operators,
        reject_unsupported=True,
        reject_failed_metrics=True,
    )
    non_signal_fields = non_signal_generation_fields(candidate)
    if non_signal_fields:
        local = dict(candidate.local_quality or {})
        reasons = list(local.get("reasons") or [])
        reason = "non_signal_generation_fields=" + ",".join(non_signal_fields[:8])
        if reason not in reasons:
            reasons.append(reason)
        local["passed"] = False
        local["reasons"] = reasons
        local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - 8.0, 2))
        local["non_signal_generation_fields"] = non_signal_fields
        candidate.local_quality = local
    if high_turnover_generation_risk_reasons(candidate.expression):
        local = dict(candidate.local_quality or {})
        reasons = list(local.get("reasons") or [])
        if "generation_risk_blocked" not in reasons:
            reasons.append("generation_risk_blocked")
        local["passed"] = False
        local["reasons"] = reasons
        candidate.local_quality = local
    candidate.scorecard = build_scorecard(candidate, run_config.ops.thresholds, run_config.ops.scoring)
    candidate.alpha_output_config = {**alpha_output_config, "official_api_called": False, "allow_submit": False}
    candidate.lifecycle_status = "local_prefilter_rejected" if candidate.local_quality.get("passed") is False else "candidate_pool_retained"
    if candidate.local_quality.get("passed") is False:
        candidate.gate = blocked_local_gate(list(candidate.local_quality.get("reasons") or []))
    else:
        candidate.gate = {}
    candidate.quality_diagnosis = diagnose_alpha_candidate(
        candidate,
        run_config=run_config,
        output_config=candidate.alpha_output_config,
    )
    decision_payload = annotate_candidate_decision(
        candidate.to_dict(),
        min_official_score=run_config.ops.budget.min_prior_score_for_official_simulation,
        update_lifecycle=True,
    )
    candidate.lifecycle_status = decision_payload.get("lifecycle_status", candidate.lifecycle_status)
    candidate.quality_diagnosis = decision_payload.get("quality_diagnosis", candidate.quality_diagnosis)
    candidate.extra_fields = decision_payload.get("extra_fields", candidate.extra_fields)
    _attach_expression_proof(candidate, proof=proof, delta=delta)
    _attach_optimization_explanation(
        candidate,
        parent=parent,
        search_row=search_row,
        proof=proof,
        delta=delta,
    )
    submission = dict(candidate.submission or {})
    submission.update({
        "source": "candidate_optimization",
        "parent_alpha_id": parent.alpha_id,
        "parent_expression": parent.expression,
        "search_score": search_row.get("score"),
        "official_context_proof_passed": proof.get("passed") is True,
        "official_api_called": False,
        "allow_submit": False,
        "updated_at": utc_now(),
    })
    candidate.submission = submission
    return candidate
