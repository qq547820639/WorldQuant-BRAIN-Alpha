"""Candidate and submission binding imports for the web facade.

Re-export shim that pulls candidate/submission helpers from the consolidated
bindings modules so ``build_web_facade_bindings`` can wire them into the
namespace. Extracted from the former ``web_facade_bindings.py`` monolith
(deep-optimization-phase12, Task B8).
"""

from __future__ import annotations

from brain_alpha_ops.web_candidates.bindings import (  # noqa: F401
    candidate_from_payload as _candidate_from_payload,
)
from brain_alpha_ops.web_candidates.bindings import (
    check_candidate as _check_candidate,
)
from brain_alpha_ops.web_candidates.bindings import (
    check_candidate_availability as _check_candidate_availability,
)
from brain_alpha_ops.web_candidates.bindings import (
    cloud_similarity_risk as _cloud_similarity_risk,
)
from brain_alpha_ops.web_candidates.bindings import (
    cloud_status_for as _cloud_status_for,
)
from brain_alpha_ops.web_candidates.bindings import (
    datasets_from_fields as _datasets_from_fields,
)
from brain_alpha_ops.web_candidates.bindings import (
    generate_candidates_payload as _generate_candidates_payload,
)
from brain_alpha_ops.web_candidates.bindings import (
    load_check_results as _load_check_results,
)
from brain_alpha_ops.web_candidates.bindings import (
    observability_submission_preflight as _observability_submission_preflight,
)
from brain_alpha_ops.web_candidates.bindings import (
    passed_candidates_from_payload as _passed_candidates_from_payload,
)
from brain_alpha_ops.web_candidates.bindings import (
    persist_official_context as _persist_official_context,
)
from brain_alpha_ops.web_candidates.bindings import (
    record_submit_blocked as _record_submit_blocked,
)
from brain_alpha_ops.web_candidates.bindings import (
    refresh_cloud_context_for_check as _refresh_cloud_context_for_check,
)
from brain_alpha_ops.web_candidates.bindings import (
    run_check_batch_job as _run_check_batch_job,
)
from brain_alpha_ops.web_candidates.bindings import (
    run_generate_candidates_job as _run_generate_candidates_job,
)
from brain_alpha_ops.web_candidates.bindings import (
    run_scoring_evaluate_job as _run_scoring_evaluate_job,
)
from brain_alpha_ops.web_candidates.bindings import (
    run_submit_batch_job as _run_submit_batch_job,
)
from brain_alpha_ops.web_candidates.bindings import (
    run_sync_job as _run_sync_job,
)
from brain_alpha_ops.web_candidates.bindings import (
    save_official_context_json as _save_official_context_json,
)
from brain_alpha_ops.web_candidates.bindings import (
    submission_preflight_advisory as _submission_preflight_advisory,
)
from brain_alpha_ops.web_candidates.bindings import (
    submission_preflight_error_message as _submission_preflight_error,
)
from brain_alpha_ops.web_candidates.bindings import (
    submit_batch as _submit_batch,
)
from brain_alpha_ops.web_candidates.bindings import (
    submit_candidate as _submit_candidate,
)
from brain_alpha_ops.web_candidates.bindings import (
    sync_cloud_alphas as _sync_cloud_alphas,
)
from brain_alpha_ops.web_candidates.selection import (
    candidate_from_payload as _candidate_from_payload_service,
)
from brain_alpha_ops.web_candidates.selection import (
    passed_candidates_from_payload as _passed_candidates_from_payload_service,
)
from brain_alpha_ops.web_submission_safety import (
    observability_submission_preflight as _observability_submission_preflight_service,
)
from brain_alpha_ops.web_submission_safety import (
    record_submit_blocked_event as _record_submit_blocked_event_service,
)
from brain_alpha_ops.web_submission_safety import (
    submission_preflight_advisory as _submission_preflight_advisory_service,
)

__all__ = [
    "_candidate_from_payload",
    "_candidate_from_payload_service",
    "_check_candidate",
    "_check_candidate_availability",
    "_cloud_similarity_risk",
    "_cloud_status_for",
    "_datasets_from_fields",
    "_generate_candidates_payload",
    "_load_check_results",
    "_observability_submission_preflight",
    "_observability_submission_preflight_service",
    "_passed_candidates_from_payload",
    "_passed_candidates_from_payload_service",
    "_persist_official_context",
    "_record_submit_blocked",
    "_record_submit_blocked_event_service",
    "_refresh_cloud_context_for_check",
    "_run_check_batch_job",
    "_run_generate_candidates_job",
    "_run_scoring_evaluate_job",
    "_run_submit_batch_job",
    "_run_sync_job",
    "_save_official_context_json",
    "_submission_preflight_advisory",
    "_submission_preflight_advisory_service",
    "_submission_preflight_error",
    "_submit_batch",
    "_submit_candidate",
    "_sync_cloud_alphas",
]
