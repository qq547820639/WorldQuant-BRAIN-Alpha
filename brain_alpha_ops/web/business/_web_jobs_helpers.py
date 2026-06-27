"""Pure helper functions extracted from web_jobs.py to satisfy the
project's 350-line module budget. Kept private to the web.business package.

These helpers are stateless (no dependence on ``ASYNC_JOBS`` or the JSONL
persistence globals) so they can be moved without affecting the module-level
mutables that tests observe via ``from brain_alpha_ops.web_jobs import _JOBS_JSONL_PATH``.
Mirrors the established helper-extraction convention (see
``brain_alpha_ops/web/business/_async_jobs_helpers.py``)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def new_job_id(prefix: str = "job") -> str:
    """Generate a new unique job ID."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()
