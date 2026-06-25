"""Summary builders for candidate optimization results."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.jsonl import iter_jsonl_records
from brain_alpha_ops.research.alpha_quality import summarize_quality_diagnostics
from brain_alpha_ops.web_candidates.audit import scientific_audit_summary
from brain_alpha_ops.web_candidates.optimization_explainability import (
    optimization_explanation_summary,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_main_pool,
    candidate_pool_summary,
)
from brain_alpha_ops.web_config import bounded_query_int

from ._helpers import _rejected_reason_counts


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
    from ._payload import candidates_ledger_path

    rows = [row for row in iter_jsonl_records(candidates_ledger_path(run_config.ops.storage_dir)) if isinstance(row, dict)]
    rows.extend(extra_rows)
    return rows


def _target_pool_size(payload: dict[str, Any], run_config: RunConfig) -> int:
    return bounded_query_int(
        payload.get("target_pool_size", payload.get("targetPoolSize", run_config.ops.budget.retained_alpha_pool_size)),
        1,
        100,
    )
