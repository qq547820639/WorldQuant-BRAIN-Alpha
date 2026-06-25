"""Top-level Alpha candidate diagnosis and quality summary.

Extracted from the original ``alpha_quality.py`` monolith. Provides the
public ``diagnose_alpha_candidate`` and ``summarize_quality_diagnostics``
entry points that aggregate the reason builders into a single report.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.config_models import OpsConfig, RunConfig
from brain_alpha_ops.models import Candidate

from .output_config import build_alpha_output_config
from .reasons_format import (
    _add_expression_reasons,
    _add_missing_candidate_reasons,
    _add_missing_config_reasons,
)
from .reasons_quality import (
    _add_gate_reasons,
    _add_local_quality_reasons,
    _add_official_evidence_reasons,
    _add_scorecard_reasons,
)
from .utils import (
    _expression_profile,
    _has_only_submission_blockers,
    _numeric_bounds,
    _ops_from_config,
    _status_label,
)


def diagnose_alpha_candidate(
    candidate: Candidate,
    *,
    run_config: RunConfig | OpsConfig,
    output_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify why a generated Alpha is or is not qualified."""

    ops_config = _ops_from_config(run_config)
    reasons: list[dict[str, Any]] = []
    output_config = output_config or build_alpha_output_config(
        ops_config,
        dataset_id=candidate.dataset_id or ops_config.settings.dataset,
    )
    _add_missing_candidate_reasons(candidate, reasons)
    _add_missing_config_reasons(output_config, reasons)
    _add_expression_reasons(candidate, reasons)
    _add_local_quality_reasons(candidate, reasons)
    _add_scorecard_reasons(candidate, reasons)
    _add_official_evidence_reasons(candidate, ops_config, reasons)
    _add_gate_reasons(candidate, reasons)

    blocking = [row for row in reasons if row.get("severity") == "blocking"]
    local_blocking_categories = {
        "missing",
        "format_error",
        "numeric_out_of_bounds",
        "local_quality_failed",
    }
    local_blocking = [
        row for row in blocking
        if row.get("category") in local_blocking_categories
    ]
    submission_ready = not blocking
    local_candidate_valid = not local_blocking
    categories = Counter(str(row.get("category") or "other") for row in reasons)
    status = "submission_ready" if submission_ready else (
        "local_only_needs_official_evidence"
        if local_candidate_valid and _has_only_submission_blockers(blocking)
        else "blocked"
    )
    return {
        "schema_version": "alpha-quality-diagnosis-v1",
        "qualified": submission_ready,
        "submission_ready": submission_ready,
        "local_candidate_valid": local_candidate_valid,
        "status": status,
        "status_label": _status_label(status),
        "primary_reason": blocking[0] if blocking else None,
        "blocking_reasons": [str(row.get("code")) for row in blocking],
        "warning_reasons": [str(row.get("code")) for row in reasons if row.get("severity") != "blocking"],
        "reason_counts": dict(Counter(str(row.get("code")) for row in reasons)),
        "category_counts": dict(categories),
        "reasons": reasons,
        "missing_fields": [
            str(row.get("field")) for row in reasons
            if row.get("category") == "missing" and row.get("field")
        ],
        "format_checks": _expression_profile(candidate.expression),
        "numeric_bounds": _numeric_bounds(run_config, output_config),
    }


def summarize_quality_diagnostics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize generated-candidate quality diagnosis for the Web preview."""

    reason_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    qualified_count = 0
    local_valid_count = 0
    invalid_count = 0
    for row in candidates:
        diagnosis = row.get("quality_diagnosis") if isinstance(row, dict) else {}
        if not isinstance(diagnosis, dict):
            continue
        if diagnosis.get("qualified"):
            qualified_count += 1
        else:
            invalid_count += 1
        if diagnosis.get("local_candidate_valid"):
            local_valid_count += 1
        status_counts[str(diagnosis.get("status") or "unknown")] += 1
        for code, count in (diagnosis.get("reason_counts") or {}).items():
            reason_counts[str(code)] += int(count or 0)
        for category, count in (diagnosis.get("category_counts") or {}).items():
            category_counts[str(category)] += int(count or 0)
    return {
        "schema_version": "alpha-quality-summary-v1",
        "candidate_count": len(candidates),
        "qualified_count": qualified_count,
        "invalid_count": invalid_count,
        "local_valid_count": local_valid_count,
        "local_only_count": status_counts.get("local_only_needs_official_evidence", 0),
        "status_counts": dict(status_counts),
        "reason_counts": dict(reason_counts),
        "category_counts": dict(category_counts),
    }
