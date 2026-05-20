"""Pure GET payload handlers for the local web console."""

from __future__ import annotations

from typing import Callable, Protocol


class JobStoreLike(Protocol):
    def get(self, job_id: str) -> dict | None:
        ...

    def latest_active(self):
        ...


ProgressEnricher = Callable[[dict], dict]


def job_status_payload(
    store: JobStoreLike,
    job_id: str,
    enrich_progress: ProgressEnricher,
    *,
    error_code: str = "JOB_NOT_FOUND",
    error: str = "unknown job",
) -> tuple[dict, int]:
    job = store.get(job_id)
    if job and "progress" in job:
        job["progress"] = enrich_progress(dict(job["progress"]))
    if not job:
        return {"ok": False, "error_code": error_code, "error": error}, 404
    return {"ok": True, **job}, 200


def active_job_payload(store: JobStoreLike, enrich_progress: ProgressEnricher) -> dict:
    active = store.latest_active()
    if not active:
        return {"ok": True, "job_id": "", "status": "idle"}
    job_id, job = active
    if "progress" in job:
        job["progress"] = enrich_progress(dict(job["progress"]))
    return {"ok": True, "job_id": job_id, **job}


def lifecycle_payload(store: JobStoreLike, job_id: str, lifecycle_from_job: Callable[[dict], list[dict]]) -> dict:
    job = store.get(job_id) or {}
    return {"ok": True, "records": lifecycle_from_job(job)}


def health_payload() -> dict:
    return {"ok": True, "status": "ready"}


def profile_payload(user_profile_snapshot: Callable[[], dict]) -> dict:
    return {"ok": True, "profile": user_profile_snapshot()}


def presets_payload(load_presets: Callable[[], dict]) -> dict:
    return {"ok": True, "presets": load_presets()}
