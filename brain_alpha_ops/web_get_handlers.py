"""Pure GET payload handlers for the local web console."""

from __future__ import annotations

from typing import Callable, Protocol

from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.runtime_constants import CloudDefaults
from brain_alpha_ops.web_progress import normalize_progress
from brain_alpha_ops.web_state_contract import enrich_error_payload, enrich_job_response


class JobStoreLike(Protocol):
    def get(self, job_id: str) -> dict | None:
        ...

    def latest_active(self):
        ...


ProgressEnricher = Callable[[dict], dict]


def _job_payload(job_id: str, job: dict, enrich_progress: ProgressEnricher) -> dict:
    payload = dict(job or {})
    status = str(payload.get("status") or "unknown")
    progress = enrich_progress(dict(payload.get("progress") or {}))
    progress = normalize_progress(progress, task_id=job_id, status=status)
    payload["progress"] = progress
    payload.setdefault("job_id", job_id)
    payload["task_id"] = job_id
    payload["phase"] = progress.get("phase", payload.get("phase", ""))
    payload["percent_complete"] = progress.get("percent_complete")
    payload["eta_seconds"] = progress.get("eta_seconds", 0)
    payload["status_message"] = progress.get("status_message", "")
    return enrich_job_response(redact_data(payload, key_fragments=("account_id", "user_id")))


def job_status_payload(
    store: JobStoreLike,
    job_id: str,
    enrich_progress: ProgressEnricher,
    *,
    error_code: str = "JOB_NOT_FOUND",
    error: str = "unknown job",
) -> tuple[dict, int]:
    job = store.get(job_id)
    if not job:
        return enrich_error_payload({"ok": False, "error_code": error_code, "error": error}), 404
    return {"ok": True, **_job_payload(job_id, job, enrich_progress)}, 200


def active_job_payload(store: JobStoreLike, enrich_progress: ProgressEnricher) -> dict:
    active = store.latest_active()
    if not active:
        return enrich_job_response({"ok": True, "job_id": "", "status": "idle"})
    job_id, job = active
    return {"ok": True, **_job_payload(job_id, job, enrich_progress)}


def lifecycle_payload(store: JobStoreLike, job_id: str, lifecycle_from_job: Callable[[dict], list[dict]]) -> dict:
    job = store.get(job_id) or {}
    records = redact_data(lifecycle_from_job(job), key_fragments=("account_id", "user_id"))
    return {
        "ok": True,
        "records": records,
        "items": records,
        "count": len(records),
        "returned_count": len(records),
        "total_count": len(records),
        "total": len(records),
        "complete": True,
        "display_limit": None,
    }


def health_payload() -> dict:
    return {
        "ok": True,
        "status": "ready",
        "cloud_sync_stale_seconds": CloudDefaults.CLOUD_SYNC_STALE_SECONDS,
    }


def profile_payload(user_profile_snapshot: Callable[[], dict]) -> dict:
    return {"ok": True, "profile": redact_data(user_profile_snapshot(), key_fragments=("account_id", "user_id"))}


def presets_payload(load_presets: Callable[[], dict]) -> dict:
    return {"ok": True, "presets": load_presets()}
