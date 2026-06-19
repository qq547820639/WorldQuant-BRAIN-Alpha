"""Candidate operations package for BRAIN Alpha Ops web layer.

Consolidates 17 web_candidate_*.py files into a single package.
"""

import brain_alpha_ops.web  # noqa: F401  ensure web bridge meta-path finder is installed

from .audit import (
    append_scientific_audit_event,
    scientific_audit_policy_reasons,
    scientific_audit_summary,
)
from .check_evidence import (
    persist_candidate_check_evidence,
    candidate_check_evidence_update,
)
from .decisions import (
    candidate_production_decision,
    annotate_candidate_decision,
    decision_action_counts,
    candidate_decision_action,
    candidate_decision_blocking,
    candidate_submission_ready,
    candidate_score,
    candidate_has_official_evidence,
    candidate_submit_only_reasons,
    candidate_hard_blocking_reasons,
    candidate_decision_evidence,
)
from .generation import generate_candidates_payload
from .generation_summary import candidate_generation_status_message
from .lifecycle_risk import (
    LIFECYCLE_RISK_SCHEMA_VERSION,
    existing_lifecycle_risk,
    lifecycle_history_requires_rework,
    lifecycle_history_should_archive,
    enrich_candidates_with_lifecycle_risk,
    lifecycle_risk_for_candidate,
)
from .optimization import optimize_candidates_payload
from .optimization_explainability import (
    OPTIMIZATION_EXPLANATION_SCHEMA_VERSION,
    optimization_explanation_summary,
)
from .payloads import (
    candidate_payload,
    candidate_summary,
    candidate_summary_from_iter,
    candidate_main_pool,
    candidate_pool_summary,
    compact_job_result,
    DEFAULT_MAIN_POOL_SIZE,
)
from .simulation import (
    simulation_candidates_payload,
    simulate_candidates_job,
)
from .simulation_failures import (
    simulation_failure_evidence,
    append_official_simulation_audit,
)
from .simulation_selection import (
    candidate_matches_requested_ids,
    requested_candidate_ids_from_payload,
    simulation_candidates_payload as simulation_candidates_payload_from_selection,
)
from .simulation_state import (
    save_candidate_update,
    load_candidates,
    save_candidates,
)
from .workflow import candidate_workflow_plan
