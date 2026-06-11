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
    connection_tracker: Any = None,    # has is_connected(), status, last_tested_at
    readiness_service: Any = None,     # has get_readiness() -> dict
    session_status: dict[str, Any] | None = None,
    cloud_alpha_snapshot: Any = None,  # callable returning cloud snapshot payload
    official_context_file_counts: Any = None,  # callable returning context count payload
) -> dict[str, Any]:
    """Build the full phase state snapshot."""

    session_status = session_status if isinstance(session_status, dict) else None
    if session_status and session_status.get("authenticated"):
        connected = bool(session_status.get("brain_connection_verified") or session_status.get("connected"))
        connection_status = "connected" if connected else "disconnected"
        last_tested_at = session_status.get("last_verified_at") or session_status.get("verified_at")
        credential_source = str(session_status.get("credential_source") or ("managed" if connected else "none"))
    else:
        connected = _safe_bool(connection_tracker, "is_connected")
        connection_status = getattr(connection_tracker, "status", "disconnected")
        last_tested_at = getattr(connection_tracker, "last_tested_at", None)
        uses_page_credentials = getattr(connection_tracker, "uses_page_credentials", False)
        credential_source = "page" if uses_page_credentials else "managed"

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
    context_fresh_source = ""
    try:
        if hasattr(sync_jobs, "list_all"):
            all_jobs = sync_jobs.list_all()
            context_fresh = any(
                j.get("status") in ("completed", "completed_with_warnings")
                for _, j in all_jobs if isinstance(j, dict)
            )
            if context_fresh:
                context_fresh_source = "sync_job"
    except Exception:
        logger.debug("phase_state: context probe failed", exc_info=True)
    if not context_fresh:
        try:
            context_fresh = _fresh_snapshot_and_context(
                cloud_alpha_snapshot=cloud_alpha_snapshot,
                official_context_file_counts=official_context_file_counts,
            )
            if context_fresh:
                context_fresh_source = "local_cache"
        except Exception:
            logger.debug("phase_state: snapshot/context freshness probe failed", exc_info=True)

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
        "context_fresh_source": context_fresh_source,
        "candidates_count": candidates_count,
        "scored_count": scored_count,
        "readiness_passed": readiness_passed,
        "sync": sync_data,
        "connection": {
            "status": connection_status,
            "last_tested_at": _format_timestamp(last_tested_at),
            "credential_source": credential_source,
        },
        "readiness": {
            "eligible_count": eligible_count,
            "ready": readiness_passed,
        },
    }


def _fresh_snapshot_and_context(*, cloud_alpha_snapshot: Any, official_context_file_counts: Any) -> bool:
    """Return true when local production inputs exist.

    Phase unlocking is intentionally cache-first: a first completed sync writes
    the cloud Alpha snapshot and official fields/operators/datasets locally, and
    later logins should use that cache by default. Staleness is still reported
    in the snapshot payload so the operator can trigger a manual refresh, but it
    must not force a full sync on every login.
    """
    if not callable(cloud_alpha_snapshot) or not callable(official_context_file_counts):
        return False
    cloud = cloud_alpha_snapshot(limit=1)
    if not isinstance(cloud, dict):
        return False
    cloud_summary = cloud.get("summary")
    if not isinstance(cloud_summary, dict):
        return False
    cloud_count = int(cloud_summary.get("count") or cloud.get("count") or 0)
    if cloud_count <= 0:
        return False
    counts = official_context_file_counts()
    if not isinstance(counts, dict):
        return False
    if int(counts.get("fields_count") or 0) <= 0:
        return False
    if int(counts.get("operators_count") or 0) <= 0:
        return False
    if int(counts.get("datasets_count") or 0) <= 0:
        return False
    manifest = counts.get("context_cache_manifest")
    if isinstance(manifest, dict):
        if not bool(manifest.get("complete")):
            return False
    return True


def _safe_bool(obj: Any, method_name: str) -> bool:
    try:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            return bool(fn())
    except (AttributeError, TypeError, ValueError):
        pass
    return False


def _format_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    formatter = getattr(value, "isoformat", None)
    if callable(formatter):
        return str(formatter())
    text = str(value).strip()
    return text or None


def _safe_int(obj: Any, method_name: str, *, default: int = 0) -> int:
    try:
        fn = getattr(obj, method_name, None)
        if callable(fn):
            result = fn()
            return int(result) if result is not None else default
    except (AttributeError, TypeError, ValueError):
        pass
    return default
