"""Batch check background job service helpers for the local web console."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger

logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


PassedCandidates = Callable[[dict[str, Any]], list[dict[str, Any]]]
RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
LedgerFactory = Callable[[str], SubmissionLedger]
PayloadTruthy = Callable[[object], bool]
RefreshCloudContext = Callable[..., tuple[list[dict[str, Any]], str]]
CheckAvailability = Callable[..., dict[str, Any]]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]
ErrorPayload = Callable[..., dict[str, Any]]


def _timing_payload(started_at: float, *, done: int = 0, total: int = 0) -> dict[str, Any]:
    current = time.time()
    elapsed = max(0.0, current - float(started_at or current))
    payload: dict[str, Any] = {
        "started_at_ms": int(float(started_at or current) * 1000),
        "updated_at_ms": int(current * 1000),
        "elapsed_seconds": round(elapsed, 1),
    }
    done = max(0, int(done or 0))
    total = max(0, int(total or 0))
    if done > 0 and total > done and elapsed > 0:
        rate = done / elapsed
        eta_seconds = max(1, int(round((total - done) / rate))) if rate > 0 else 0
        payload["eta_seconds"] = eta_seconds
        payload["eta_deadline_at_ms"] = int((current + eta_seconds) * 1000)
    elif total and done >= total:
        payload["eta_seconds"] = 0
    return payload


def _store_is_cancelled(store: JobStoreLike, job_id: str) -> bool:
    checker = getattr(store, "is_cancelled", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(job_id))
    except Exception:
        logger.warning(
            "job cancellation check failed; treating as not cancelled",
            exc_info=True,
        )
        return False


def _update_check_batch_cancelled(
    store: JobStoreLike,
    job_id: str,
    *,
    mode: str,
    sync_range: str,
    total: int,
    checked: int,
    submittable: int,
    blocked: int,
    failed: int,
    started_at: float,
    results: list[dict[str, Any]],
) -> None:
    store.update(
        job_id,
        status="stopped",
        progress={
            "task_id": job_id,
            "job_id": job_id,
            "operation": "check_batch",
            "phase": "stopped",
            "status_code": "CHECK_STOPPED",
            "mode": mode,
            "range": sync_range,
            "total": total,
            "percent": 100,
            "percent_complete": 100,
            "checked": checked,
            "submittable": submittable,
            "blocked": blocked,
            "failed": failed,
            "status_message": "批量质量检查已停止，未继续调用官方上下文或候选检查。",
            "message": "批量质量检查已停止，未继续调用官方上下文或候选检查。",
            **_timing_payload(started_at, done=checked, total=total),
            "items": results,
        },
    )
