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
    cloud_alpha_cache_probe: Any = None,  # callable returning lightweight cloud cache state
    official_context_file_counts: Any = None,  # callable returning context count payload
    candidate_summary_probe: Any = None,  # callable returning candidate ledger/pool summary
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
    official_context_cache: dict[str, Any] = {"ok": False}
    cloud_alpha_cache: dict[str, Any] = {"ok": False}
    has_cache_probe = (
        callable(official_context_file_counts)
        and (callable(cloud_alpha_cache_probe) or callable(cloud_alpha_snapshot))
    )
    if has_cache_probe:
        try:
            context_probe = _snapshot_and_context_cache_state(
                cloud_alpha_snapshot=cloud_alpha_snapshot,
                cloud_alpha_cache_probe=cloud_alpha_cache_probe,
                official_context_file_counts=official_context_file_counts,
            )
            official_context_cache = context_probe["official_context_cache"]
            cloud_alpha_cache = context_probe["cloud_alpha_cache"]
            context_fresh = bool(context_probe["fresh"])
            if context_fresh:
                context_fresh_source = "local_cache"
        except Exception:
            logger.debug("phase_state: snapshot/context freshness probe failed", exc_info=True)
    try:
        if not has_cache_probe and hasattr(sync_jobs, "list_all"):
            all_jobs = sync_jobs.list_all()
            context_fresh = any(
                j.get("status") in ("completed", "completed_with_warnings")
                for _, j in all_jobs if isinstance(j, dict)
            )
            if context_fresh:
                context_fresh_source = "sync_job"
    except Exception:
        logger.debug("phase_state: context probe failed", exc_info=True)

    # ── Candidates ─────────────────────────────────────────
    candidate_counts = _candidate_counts(candidate_repo, candidate_summary_probe)
    candidates_count = candidate_counts["count"]
    scored_count = candidate_counts["scored_count"]

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
    if not context_fresh:
        current_phase = "connect"
    elif readiness_passed:
        current_phase = "ready"
    elif candidates_count == 0:
        current_phase = "discover"
    else:
        current_phase = "evaluate"
    if connected and context_fresh:
        operation_mode = "connected"
    elif context_fresh:
        operation_mode = "cache_only"
    else:
        operation_mode = "needs_setup"

    return {
        "ok": True,
        "current_phase": current_phase,
        "operation_mode": operation_mode,
        "connected": connected,
        "context_fresh": context_fresh,
        "context_fresh_source": context_fresh_source,
        "candidates_count": candidates_count,
        "scored_count": scored_count,
        "candidate_count_source": candidate_counts["source"],
        "readiness_passed": readiness_passed,
        "sync": sync_data,
        "official_context_cache": official_context_cache,
        "cloud_alpha_cache": cloud_alpha_cache,
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


def _candidate_counts(candidate_repo: Any, candidate_summary_probe: Any = None) -> dict[str, Any]:
    repo_count = _safe_int(candidate_repo, "count")
    repo_scored_count = _safe_int(candidate_repo, "scored_count", default=0)
    if not callable(candidate_summary_probe):
        return {"count": repo_count, "scored_count": repo_scored_count, "source": "candidate_repo"}
    try:
        summary = candidate_summary_probe()
    except Exception:
        logger.debug("phase_state: candidate summary probe failed", exc_info=True)
        return {"count": repo_count, "scored_count": repo_scored_count, "source": "candidate_repo"}
    if not isinstance(summary, dict):
        return {"count": repo_count, "scored_count": repo_scored_count, "source": "candidate_repo"}
    summary_count = _candidate_pool_count(summary)
    if summary_count is None:
        return {"count": repo_count, "scored_count": repo_scored_count, "source": "candidate_repo"}
    return {
        "count": summary_count,
        "scored_count": _nonnegative_int(summary.get("scored_count"), repo_scored_count),
        "source": str(summary.get("source") or "candidate_summary"),
    }


def _candidate_pool_count(summary: dict[str, Any]) -> int | None:
    pool_summary = summary.get("pool_summary") if isinstance(summary.get("pool_summary"), dict) else {}
    for key in ("main_pool_count", "promotable_count"):
        value = pool_summary.get(key)
        count = _optional_nonnegative_int(value)
        if count is not None:
            return count
    main_pool_candidates = summary.get("main_pool_candidates")
    if isinstance(main_pool_candidates, list) and main_pool_candidates:
        return len(main_pool_candidates)
    for key in ("main_pool_count", "promotable_count", "candidates_count", "candidate_count", "total", "total_count"):
        count = _optional_nonnegative_int(summary.get(key))
        if count is not None:
            return count
    return None


def _optional_nonnegative_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _nonnegative_int(value: Any, default: int) -> int:
    number = _optional_nonnegative_int(value)
    return default if number is None else number


def _fresh_snapshot_and_context(
    *,
    cloud_alpha_snapshot: Any,
    official_context_file_counts: Any,
    cloud_alpha_cache_probe: Any = None,
) -> bool:
    return bool(_snapshot_and_context_cache_state(
        cloud_alpha_snapshot=cloud_alpha_snapshot,
        cloud_alpha_cache_probe=cloud_alpha_cache_probe,
        official_context_file_counts=official_context_file_counts,
    )["fresh"])


def _snapshot_and_context_cache_state(
    *,
    cloud_alpha_snapshot: Any,
    official_context_file_counts: Any,
    cloud_alpha_cache_probe: Any = None,
) -> dict[str, Any]:
    """Return true when local production inputs exist.

    Phase unlocking is intentionally cache-first: a first completed sync writes
    the cloud Alpha snapshot and official fields/operators/datasets locally, and
    later logins should use that cache by default. Staleness is still reported
    in the snapshot payload so the operator can trigger a manual refresh, but it
    must not force a full sync on every login.
    """
    empty = {
        "fresh": False,
        "official_context_cache": {"ok": False},
        "cloud_alpha_cache": {"ok": False},
    }
    if not callable(official_context_file_counts) or not (
        callable(cloud_alpha_cache_probe) or callable(cloud_alpha_snapshot)
    ):
        return empty
    cloud_cache = _cloud_alpha_cache_summary(
        cloud_alpha_cache_probe() if callable(cloud_alpha_cache_probe) else cloud_alpha_snapshot(limit=1)
    )
    cloud_ready = bool(cloud_cache.get("ok")) or int(cloud_cache.get("count") or cloud_cache.get("total") or 0) > 0
    if not cloud_ready:
        return {
            "fresh": False,
            "official_context_cache": {"ok": False},
            "cloud_alpha_cache": cloud_cache,
        }
    counts = official_context_file_counts()
    if not isinstance(counts, dict):
        return {
            "fresh": False,
            "official_context_cache": {"ok": False},
            "cloud_alpha_cache": cloud_cache,
        }
    context_cache = _official_context_cache_summary(counts)
    counts_present = (
        int(context_cache.get("fields_count") or 0) > 0
        and int(context_cache.get("operators_count") or 0) > 0
        and int(context_cache.get("datasets_count") or 0) > 0
    )
    manifest = context_cache.get("manifest")
    manifest_complete = not isinstance(manifest, dict) or bool(manifest.get("complete"))
    fresh = bool(cloud_ready and context_cache.get("ok") and counts_present and manifest_complete)
    return {
        "fresh": fresh,
        "official_context_cache": context_cache,
        "cloud_alpha_cache": cloud_cache,
    }


def _cloud_alpha_cache_summary(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        source = payload["summary"]
    if not isinstance(source, dict):
        return {"ok": False}

    raw_count = source.get("count")
    raw_total = source.get("total")
    if isinstance(payload, dict):
        if raw_count is None:
            raw_count = payload.get("count")
        if raw_total is None:
            raw_total = payload.get("total")
    count = _optional_int(raw_count)
    total = _optional_int(raw_total)
    ok = bool(source.get("ok")) or (count is not None and count > 0) or (total is not None and total > 0)
    cache: dict[str, Any] = {
        "ok": ok,
        "source": str(source.get("source") or ""),
        "is_stale": bool(source.get("is_stale")),
        "loaded_at": str(source.get("loaded_at") or ""),
        "age_seconds": int(source.get("age_seconds") or 0),
    }
    if count is not None:
        cache["count"] = count
    if total is not None:
        cache["total"] = total
    return cache


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _official_context_cache_summary(counts: dict[str, Any]) -> dict[str, Any]:
    cache: dict[str, Any] = {
        "ok": True,
        "fields_count": int(counts.get("fields_count") or 0),
        "operators_count": int(counts.get("operators_count") or 0),
        "datasets_count": int(counts.get("datasets_count") or 0),
    }
    manifest = counts.get("context_cache_manifest")
    if isinstance(manifest, dict):
        cache["manifest"] = {
            "complete": bool(manifest.get("complete")),
            "is_stale": bool(manifest.get("is_stale")),
            "missing_files": list(manifest.get("missing_files") or []),
            "stale_files": list(manifest.get("stale_files") or manifest.get("expired_files") or []),
            "invalid_files": list(manifest.get("invalid_files") or []),
            "record_counts": dict(manifest.get("record_counts") or {}),
        }
    return cache


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
