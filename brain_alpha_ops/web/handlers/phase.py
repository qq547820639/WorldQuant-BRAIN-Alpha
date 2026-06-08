"""Phase state endpoint — provides real-time phase progression for frontend PhaseShell.

GET /api/phase_state
  Returns current workflow phase, connection status, sync progress,
  candidate counts, and readiness state.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def phase_state_payload(
    *,
    sync_jobs: Any,             # JobStore-like with latest_active() and list_all()
    candidate_repo: Any,        # CandidateRepository-like with count()
    connection_tracker: Any,    # has is_connected(), status, last_tested_at
    readiness_service: Any,     # has get_readiness() -> dict
) -> dict[str, Any]:
    """Build the full phase state snapshot."""

    connected = _safe_bool(connection_tracker, "is_connected")
    connection_status = getattr(connection_tracker, "status", "disconnected")
    last_tested_at = getattr(connection_tracker, "last_tested_at", None)
    uses_page_credentials = getattr(connection_tracker, "uses_page_credentials", False)

    # ── Sync progress ──────────────────────────────────────
    sync_data: dict[str, Any] = {
        "in_progress": False,
        "scanned": 0,
        "total": 0,
        "elapsed_seconds": 0,
        "stalled": False,
    }
    try:
        active = sync_jobs.latest_active() if hasattr(sync_jobs, "latest_active") else None
        if active:
            _, job = active
            progress = job.get("progress", {}) if isinstance(job, dict) else {}
            scanned = int(progress.get("scanned", 0) or 0)
            total = int(progress.get("total", 0) or 0)
            elapsed = float(progress.get("elapsed_seconds", 0) or 0)
            phase = str(progress.get("phase", ""))
            sync_data = {
                "in_progress": True,
                "scanned": scanned,
                "total": total,
                "elapsed_seconds": elapsed,
                "stalled": (phase == "scan" and scanned == 0 and elapsed > 10),
            }
    except Exception:
        logger.debug("phase_state: sync probe failed", exc_info=True)

    # ── Context freshness ──────────────────────────────────
    context_fresh = False
    try:
        if hasattr(sync_jobs, "list_all"):
            all_jobs = sync_jobs.list_all()
            context_fresh = any(
                j.get("status") in ("completed", "completed_with_warnings")
                for _, j in all_jobs if isinstance(j, dict)
            )
    except Exception:
        logger.debug("phase_state: context probe failed", exc_info=True)

    # ── Candidates ─────────────────────────────────────────
    candidates_count = _safe_int(candidate_repo, "count")
    scored_count = _safe_int(candidate_repo, "scored_count", default=0)

    # ── Readiness ──────────────────────────────────────────
    readiness_passed = False
    eligible_count = 0
    try:
        if hasattr(readiness_service, "get_readiness"):
            readiness = readiness_service.get_readiness()
            if isinstance(readiness, dict):
                readiness_passed = bool(readiness.get("ready_to_submit"))
                eligible_count = int(readiness.get("eligible_count", 0) or 0)
    except Exception:
        logger.debug("phase_state: readiness probe failed", exc_info=True)

    # ── Determine current phase ────────────────────────────
    if not connected or not context_fresh:
        current_phase = "connect"
    elif candidates_count == 0:
        current_phase = "discover"
    elif not readiness_passed:
        current_phase = "evaluate"
    else:
        current_phase = "ready"

    return {
        "ok": True,
        "current_phase": current_phase,
        "connected": connected,
        "context_fresh": context_fresh,
        "candidates_count": candidates_count,
        "scored_count": scored_count,
        "readiness_passed": readiness_passed,
        "sync": sync_data,
        "connection": {
            "status": connection_status,
            "last_tested_at": last_tested_at.isoformat() if last_tested_at else None,
            "credential_source": "page" if uses_page_credentials else "managed",
        },
        "readiness": {
            "eligible_count": eligible_count,
            "ready": readiness_passed,
        },
    }


def _safe_bool(obj: Any, method_name: str) -> bool:
    try:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            return bool(fn())
    except (AttributeError, TypeError, ValueError):
        pass
    return False


def _safe_int(obj: Any, method_name: str, *, default: int = 0) -> int:
    try:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            result = fn()
            return int(result) if result is not None else default
    except (AttributeError, TypeError, ValueError):
        pass
    return default
