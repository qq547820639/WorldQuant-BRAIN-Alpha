"""Recording of submission-blocked lifecycle events.

Extracted from the former ``web_submission_safety.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_candidates.selection import official_alpha_id

from ._blocks import RepositoryFactory, logger


def record_submit_blocked_event(
    payload: dict[str, Any],
    candidate: dict[str, Any],
    run_config: RunConfig,
    failure_reason: str,
    *,
    repository_factory: RepositoryFactory = ResearchRepository,
    log: logging.Logger = logger,
) -> None:
    try:
        repository_factory(run_config.ops.storage_dir).save_lifecycle_record(
            str(payload.get("job_id", "")) or "manual_submit",
            {
                "timestamp": utc_now(),
                "alpha_id": candidate.get("alpha_id", ""),
                "official_alpha_id": official_alpha_id(candidate),
                "simulation_id": candidate.get("simulation_id", ""),
                "stage": "submission_blocked",
                "status": "BLOCKED",
                "family": candidate.get("family", ""),
                "score": (candidate.get("scorecard") or {}).get("total_score", 0.0),
                "expression": candidate.get("expression", ""),
                "submit_trigger": str(payload.get("submit_mode", "manual")),
                "environment": str(run_config.environment),
                "failure_reason": failure_reason,
                "note": failure_reason,
            },
        )
    except OSError as exc:
        log.error(
            "I/O error recording submission blocked for alpha_id=%s reason=%s: %s",
            redact_text(candidate.get("alpha_id", "?"), max_length=64),
            redact_text(failure_reason, max_length=160),
            redact_error_message(exc),
        )
    except Exception as exc:
        log.warning(
            "failed to record submission blocked for alpha_id=%s reason=%s: %s",
            redact_text(candidate.get("alpha_id", "?"), max_length=64),
            redact_text(failure_reason, max_length=160),
            redact_error_message(exc),
        )
