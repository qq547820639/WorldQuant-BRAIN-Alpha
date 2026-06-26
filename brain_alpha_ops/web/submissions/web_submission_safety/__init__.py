"""Submission safety preflight services for the local web console.

Re-export subpackage. The implementation has been split from the former
``web_submission_safety.py`` monolith (deep-optimization-phase13) into
responsibility-focused submodules. The public API, the transitive
re-export aliases, and the private helpers are re-exported here so
``from brain_alpha_ops.web.submissions.web_submission_safety import ...``
(and the bridged ``brain_alpha_ops.web_submission_safety`` flat alias)
continue to resolve to this package directory.
"""

from __future__ import annotations

from brain_alpha_ops.web_candidates.payloads import (  # noqa: F401
    save_assistant_guidance_post_payload,
)
from brain_alpha_ops.web_candidates.selection import (  # noqa: F401
    candidate_official_metrics,
    official_alpha_id,
)
from brain_alpha_ops.web_cloud.snapshot import dedupe_cloud_alpha_rows  # noqa: F401
from brain_alpha_ops.web_cloud.snapshot import extract_alpha_rows  # noqa: F401

from ._blocks import (
    CloudAlphaSnapshot,
    CloudStatusFor,
    LedgerFactory,
    ObservabilityBuilder,
    RepositoryFactory,
    SafeErrorMessage,
    logger,
    submit_preflight_block,
    submission_preflight_block,
)
from ._events import record_submit_blocked_event
from ._observability import observability_submission_preflight
from ._preflight_advisory import (
    _cloud_self_correlation_submit_block,
    _latest_check_result_for_candidate,
    submission_preflight_advisory,
)
from ._preflight_message import submission_preflight_error_message

__all__ = [
    "CloudAlphaSnapshot",
    "CloudStatusFor",
    "LedgerFactory",
    "ObservabilityBuilder",
    "RepositoryFactory",
    "SafeErrorMessage",
    "candidate_official_metrics",
    "dedupe_cloud_alpha_rows",
    "extract_alpha_rows",
    "logger",
    "observability_submission_preflight",
    "official_alpha_id",
    "record_submit_blocked_event",
    "save_assistant_guidance_post_payload",
    "submit_preflight_block",
    "submission_preflight_advisory",
    "submission_preflight_block",
    "submission_preflight_error_message",
    "_cloud_self_correlation_submit_block",
    "_latest_check_result_for_candidate",
]
