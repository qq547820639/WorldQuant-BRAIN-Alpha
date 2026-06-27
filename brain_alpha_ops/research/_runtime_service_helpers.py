"""Standalone helpers extracted from runtime_service.py.

Pure primitives used by ``RuntimeService`` for archive bookkeeping and
stop-aware sleeping. Kept here so ``runtime_service.py`` stays within the
project's 350-line module budget without changing the public surface of
``RuntimeService``.

Do not import these helpers directly — prefer ``RuntimeService`` methods.
"""

from __future__ import annotations

import time

from brain_alpha_ops.models import Candidate

_ARCHIVED_SKIP_STATUSES = frozenset({
    "LOCAL_PREFILTER_REJECTED",
    "LOCAL_STANDARD_REJECTED",
    "CANDIDATE_POOL_PRUNED",
    "DUPLICATE_EXPRESSION_SKIPPED",
    "PREVIOUSLY_REJECTED_EXPRESSION_SKIPPED",
})


def archive_candidates(
    archive_stats: dict[str, int],
    archive_samples: list[Candidate],
    candidates: list[Candidate],
) -> None:
    """Tally archive stats and collect up to 25 official-metric samples."""
    for candidate in candidates:
        status = candidate.gate.get("status") or candidate.lifecycle_status or "ARCHIVED"
        if status in _ARCHIVED_SKIP_STATUSES:
            continue
        archive_stats[status] = archive_stats.get(status, 0) + 1
        if len(archive_samples) < 25 and candidate.official_metrics:
            archive_samples.append(candidate)


def pipeline_should_stop(pipeline) -> bool:
    """Return True if the pipeline's stop_callback requests termination."""
    return bool(pipeline.stop_callback and pipeline.stop_callback())


def pipeline_sleep_with_stop(pipeline, seconds: float) -> bool:
    """Sleep for ``seconds`` while polling the stop callback.

    Returns False if a stop was requested during the sleep, True otherwise.
    """
    deadline = time.monotonic() + max(0.0, float(seconds or 0.0))
    while time.monotonic() < deadline:
        if pipeline_should_stop(pipeline):
            return False
        time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    return not pipeline_should_stop(pipeline)
