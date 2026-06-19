"""Local-only candidate optimization for the Web candidate pool."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, resolve_default_dataset_id
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.errors import ValidationError
from brain_alpha_ops.jsonl import iter_jsonl_records
from brain_alpha_ops.models import Candidate, new_id, utc_now
from brain_alpha_ops.research.alpha_quality import (
    build_alpha_output_config,
    diagnose_alpha_candidate,
    summarize_quality_diagnostics,
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
from brain_alpha_ops.research.local_backtest_config import (
    PREFILTER_BACKTEST_DATES,
    PREFILTER_BACKTEST_SYMBOLS,
)
from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
from brain_alpha_ops.research.local_backtest_gate import (
    apply_local_backtest_gate,
    blocked_local_gate,
)
from brain_alpha_ops.research.parameter_search import ParameterSearchService
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.web_candidates.audit import (
    attach_scientific_audit,
    scientific_audit_summary,
)
from brain_alpha_ops.web_candidates.decisions import (
    annotate_candidate_decision,
    candidate_decision_action,
)
from brain_alpha_ops.web_candidates.optimization_explainability import (
    OPTIMIZATION_EXPLANATION_SCHEMA_VERSION,
    optimization_explanation_summary,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_main_pool,
    candidate_pool_summary,
)
from brain_alpha_ops.web_config import _MAX_CANDIDATES, bounded_query_int

RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
RepositoryFactory = Callable[[str], ResearchRepository]
ParameterSearchFactory = Callable[[], ParameterSearchService]


def optimize_candidates_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    repository_factory: RepositoryFactory = ResearchRepository,
    parameter_search_factory: ParameterSearchFactory = ParameterSearchService,
) -> dict[str, Any]:
    """Generate bounded local mutation candidates from reworkable pool rows."""

    payload = dict(payload or {})
    run_config = run_config_from_payload(payload)
    dataset_id = _resolve_dataset_id(payload, run_config)
    if not dataset_id:
        return user_error_payload(
            ValidationError("dataset_id is required for candidate optimization"),
            error_code="OPTIMIZE_CANDIDATES_DATASET_ERROR",
            phase="web_optimize_candidates",
        )
    run_config.ops.settings.dataset = dataset_id

    source_candidates = _source_candidates(payload, run_config)
    if not source_candidates:
        return {
            "ok": True,
            "schema_version": "candidate-optimization-result-v1",
            "source": "local_parameter_search",
            "local_only": True,
            "official_api_called": False,
            "submit_allowed": False,
            "candidate_count": 0,
            "optimized_count": 0,
            "returned_count": 0,
            "rejected_count": 0,
            "candidates": [],
            "rejected_candidates_preview": [],
            "summary": _summary(
                run_config,
                dataset_id,
                source_candidates=[],
                processed_candidates=[],
                returned_candidates=[],
                rejected_candidates=[],
                target_pool_size=_target_pool_size(payload, run_config),
                search_budget={},
            ),
        }

    max_candidates = bounded_query_int(payload.get("max_candidates", payload.get("candidate_limit", 3)), 1, min(_MAX_CANDIDATES, 20))
    max_mutations = bounded_query_int(payload.get("max_mutations", 3), 1, 12)
    keep_top = bounded_query_int(payload.get("keep_top", max_mutations), 1, 20)
    target_pool_size = _target_pool_size(payload, run_config)
    alpha_output_config = build_alpha_output_config(
        run_config,
        dataset_id=dataset_id,
        generation_args={
            "source": "candidate_optimization",
            "max_candidates": max_candidates,
            "max_mutations": max_mutations,
            "keep_top": keep_top,
        },
    )
    local_backtest_engine = LocalBacktestEngine(
        n_dates=PREFILTER_BACKTEST_DATES,
        n_symbols=PREFILTER_BACKTEST_SYMBOLS,
    )
    search = parameter_search_factory()
    selected_sources = _rank_rework_sources(source_candidates)[:max_candidates]

    processed_candidates: list[dict[str, Any]] = []
    returned_candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    seen_expressions = {
        _expression_key(row.get("expression"))
        for row in source_candidates
        if isinstance(row, dict) and row.get("expression")
    }
    search_budget = {
        "max_candidates": max_candidates,
        "max_mutations": max_mutations,
        "keep_top": keep_top,
        "bounded": True,
        "live_api_calls": 0,
    }

    for source in selected_sources:
        parent = Candidate.from_dict(source)
        result = search.search(
            parent,
            max_mutations=max_mutations,
            diagnosis=parent.quality_diagnosis or None,
            thresholds=run_config.ops.thresholds,
        )
        for row in result.get("results") or []:
            if len(returned_candidates) >= max_candidates * keep_top:
                break
            if not isinstance(row, dict) or not isinstance(row.get("candidate"), dict):
                continue
            child = Candidate.from_dict(row["candidate"])
            if _expression_key(child.expression) in seen_expressions:
                continue
            seen_expressions.add(_expression_key(child.expression))
            prepared = _prepare_optimized_candidate(
                child,
                parent=parent,
                search_row=row,
                run_config=run_config,
                dataset_id=dataset_id,
                alpha_output_config=alpha_output_config,
                local_backtest_engine=local_backtest_engine,
            )
            prepared_payload = prepared.to_dict()
            prepared_payload = attach_scientific_audit(
                prepared_payload,
                operation="candidate_optimization",
                source="local_parameter_search",
                parent=parent.to_dict(),
                search_row=row,
                feedback_sources=[
                    "parameter_search_diagnosis",
                    "local_quality",
                    "local_backtest_prefilter",
                    "scorecard",
                    "quality_gate",
                ],
                decision=prepared_payload.get("production_decision")
                if isinstance(prepared_payload.get("production_decision"), dict)
                else None,
            )
            processed_candidates.append(prepared_payload)
            if _candidate_rejected_by_local_gate(prepared_payload):
                rejected_candidates.append(prepared_payload)
            else:
                returned_candidates.append(prepared_payload)

    return {
        "ok": True,
        "schema_version": "candidate-optimization-result-v1",
        "source": "local_parameter_search",
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "candidate_count": len(source_candidates),
        "optimized_count": len(processed_candidates),
        "returned_count": len(returned_candidates),
        "rejected_count": len(rejected_candidates),
        "candidates": returned_candidates,
        "rejected_candidates_preview": rejected_candidates[:20],
        "summary": _summary(
            run_config,
            dataset_id,
            source_candidates=selected_sources,
            processed_candidates=processed_candidates,
            returned_candidates=returned_candidates,
            rejected_candidates=rejected_candidates,
            target_pool_size=target_pool_size,
            search_budget=search_budget,
        ),
    }


def persist_optimized_candidates(
    job_id: str,
    run_config: RunConfig,
    result: dict[str, Any],
    *,
    repository_factory: RepositoryFactory = ResearchRepository,
) -> dict[str, Any]:
    repo = repository_factory(run_config.ops.storage_dir)
    persisted = 0
    skipped_invalid = 0
    skipped_reasons: dict[str, int] = {}
    errors: list[str] = []
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        if _candidate_rejected_by_local_gate(row):
            skipped_invalid += 1
            for reason in _candidate_rejection_reasons(row):
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            continue
        try:
            if "scientific_audit" not in row and not (
                isinstance(row.get("extra_fields"), dict)
                and isinstance(row.get("extra_fields", {}).get("scientific_audit"), dict)
            ):
                row = attach_scientific_audit(
                    row,
                    operation="candidate_optimization",
                    source="candidate_persistence",
                    feedback_sources=["parameter_search_diagnosis", "local_quality", "scorecard", "quality_gate"],
                )
            repo.save_candidate(job_id, Candidate.from_dict(row))
            persisted += 1
        except Exception as exc:
            from brain_alpha_ops.redaction import redact_error_message

            errors.append(redact_error_message(exc))
    return {
        "schema_version": "candidate-optimization-persistence-v1",
        "target": "candidates.jsonl",
        "persisted_count": persisted,
        "skipped_invalid_count": skipped_invalid,
        "skipped_invalid_reasons": skipped_reasons,
        "error_count": len(errors),
        "errors": errors[:3],
    }


def _resolve_dataset_id(payload: dict[str, Any], run_config: RunConfig) -> str:
    dataset_id = str(payload.get("dataset_id") or run_config.ops.settings.dataset or "").strip()
    if dataset_id:
        return dataset_id
    try:
        return resolve_default_dataset_id(run_config.ops.storage_dir)
    except Exception:
        return ""


def _source_candidates(payload: dict[str, Any], run_config: RunConfig) -> list[dict[str, Any]]:
    raw = payload.get("candidates")
    if isinstance(raw, list):
        return [dict(row) for row in raw if isinstance(row, dict)]
    raw = payload.get("optimize_candidates")
    if isinstance(raw, list):
        return [dict(row) for row in raw if isinstance(row, dict)]
    path = candidates_ledger_path(run_config.ops.storage_dir)
    return [row for row in iter_jsonl_records(path) if isinstance(row, dict)]


def candidates_ledger_path(storage_dir: str):
    return ResearchRepository(storage_dir)._safe_storage_path("candidates.jsonl")


def _rank_rework_sources(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reworkable = [row for row in candidates if _candidate_needs_optimization(row)]
    rows = reworkable or [row for row in candidates if not _candidate_rejected_by_local_gate(row)]
    return sorted(rows, key=_candidate_score, reverse=True)


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


def _summary(
    run_config: RunConfig,
    dataset_id: str,
    *,
    source_candidates: list[dict[str, Any]],
    processed_candidates: list[dict[str, Any]],
    returned_candidates: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]],
    target_pool_size: int,
    search_budget: dict[str, Any],
) -> dict[str, Any]:
    all_candidates = _all_candidate_rows(run_config, returned_candidates)
    return {
        "schema_version": "candidate-optimization-summary-v1",
        "source": "local_parameter_search",
        "dataset_id": dataset_id,
        "source_candidate_count": len(source_candidates),
        "optimized_count": len(processed_candidates),
        "returned_count": len(returned_candidates),
        "rejected_count": len(rejected_candidates),
        "rejected_reasons": _rejected_reason_counts(rejected_candidates),
        "quality_summary": summarize_quality_diagnostics(processed_candidates),
        "target_pool_size": target_pool_size,
        "main_pool_count": len(candidate_main_pool(all_candidates, target_size=target_pool_size)),
        "pool_summary": candidate_pool_summary(all_candidates, target_size=target_pool_size),
        "search_budget": search_budget,
        "scientific_audit": scientific_audit_summary(processed_candidates),
        "optimization_explanations": optimization_explanation_summary(processed_candidates),
        "automation": {
            "mode": "candidate_pool_optimization",
            "maintain_candidate_pool": True,
            "auto_simulate_after_optimization": False,
            "auto_check_after_simulation": False,
            "submit_allowed": False,
            "official_api_called": False,
        },
    }


def _all_candidate_rows(run_config: RunConfig, extra_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [row for row in iter_jsonl_records(candidates_ledger_path(run_config.ops.storage_dir)) if isinstance(row, dict)]
    rows.extend(extra_rows)
    return rows


def _target_pool_size(payload: dict[str, Any], run_config: RunConfig) -> int:
    return bounded_query_int(
        payload.get("target_pool_size", payload.get("targetPoolSize", run_config.ops.budget.retained_alpha_pool_size)),
        1,
        100,
    )


def _candidate_needs_optimization(row: dict[str, Any]) -> bool:
    if _candidate_rejected_by_local_gate(row):
        return False
    if _candidate_submission_ready(row):
        return False
    return candidate_decision_action(row) == "optimize"


def _candidate_submission_ready(row: dict[str, Any]) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return bool(
        str(row.get("lifecycle_status") or "").lower() == "submission_ready"
        or diagnosis.get("submission_ready") is True
        or gate.get("submission_ready") is True
    )


def _candidate_rejected_by_local_gate(candidate: dict[str, Any]) -> bool:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if diagnosis.get("local_candidate_valid") is False:
        return True
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return True
    support = local_quality.get("local_backtest_support") if isinstance(local_quality.get("local_backtest_support"), dict) else {}
    if support.get("supported") is False:
        return True
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        return True
    return False


def _candidate_rejection_reasons(candidate: dict[str, Any]) -> list[str]:
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    reasons = [str(reason or "").strip() for reason in diagnosis.get("blocking_reasons") or [] if str(reason or "").strip()]
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    for reason in local_quality.get("reasons") or []:
        text = str(reason or "").strip()
        if text:
            reasons.append(text.split(":", 1)[0])
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        reasons.append("local_backtest_failed")
    return sorted(set(reasons)) or ["local_candidate_invalid"]


def _rejected_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        for reason in _candidate_rejection_reasons(candidate):
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _candidate_score(row: dict[str, Any]) -> float:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    try:
        value = float(scorecard.get("total_score", row.get("score")) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if value == value else 0.0


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    results: list[int] = []
    for item in value:
        try:
            results.append(int(item))
        except (TypeError, ValueError):
            continue
    return results


def _candidate_blocking_codes(row: dict[str, Any]) -> list[str]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    codes: set[str] = set()
    primary = diagnosis.get("primary_reason") if isinstance(diagnosis.get("primary_reason"), dict) else {}
    primary_code = str(primary.get("code") or "").strip()
    if primary_code:
        codes.add(primary_code)
    for reason in diagnosis.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text:
            codes.add(text)
    for item in diagnosis.get("reasons") or []:
        if not isinstance(item, dict):
            continue
        if item.get("severity") and item.get("severity") != "blocking":
            continue
        code = str(item.get("code") or "").strip()
        if code:
            codes.add(code)
    return sorted(codes)


def _is_submit_only_blocker(reason: str) -> bool:
    from brain_alpha_ops.web.misc.web_backtest_slots import is_submit_only_quality_reason

    return is_submit_only_quality_reason(reason, "")


def _expression_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())
