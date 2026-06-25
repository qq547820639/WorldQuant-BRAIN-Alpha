"""Main orchestration for local candidate optimization."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, resolve_default_dataset_id
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.errors import ValidationError
from brain_alpha_ops.jsonl import iter_jsonl_records
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.alpha_quality import build_alpha_output_config
from brain_alpha_ops.research.local_backtest_config import (
    PREFILTER_BACKTEST_DATES,
    PREFILTER_BACKTEST_SYMBOLS,
)
from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine  # noqa: F401
from brain_alpha_ops.research.parameter_search import ParameterSearchService
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_candidates.audit import attach_scientific_audit
from brain_alpha_ops.web_config import _MAX_CANDIDATES, bounded_query_int

from ._helpers import (
    _candidate_needs_optimization,
    _candidate_rejected_by_local_gate,
    _candidate_rejection_reasons,
    _candidate_score,
    _expression_key,
)
from ._prepare import _prepare_optimized_candidate
from ._summary import _summary, _target_pool_size

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

    # Late import so monkeypatch of LocalBacktestEngine on the package works.
    from brain_alpha_ops.web_candidates.optimization import LocalBacktestEngine

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
