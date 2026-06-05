"""Job registry for the web console."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

from brain_alpha_ops.task_executor import ThreadTaskExecutor
from brain_alpha_ops.tasks import JobStore
from brain_alpha_ops.web_rate_limit import RequestRateLimiter


@dataclass
class WebJobRegistry:
    """Manages async jobs, sync jobs, check jobs, and submission state."""
    task_executor: ThreadTaskExecutor
    jobs: JobStore
    sync_jobs: JobStore
    check_jobs: JobStore
    async_jobs: JobStore
    submit_lock: threading.Lock
    rate_limiter: RequestRateLimiter

    @classmethod
    def create(cls, storage_dir: Path, *, max_workers: int = 4, rate_limit_window: float = 1.0, rate_limit_max: int = 10):
        """Create and return a new WebJobRegistry."""
        data_dir = storage_dir if storage_dir.name == "data" else storage_dir / "data"
        return cls(
            task_executor=ThreadTaskExecutor(max_workers=max_workers),
            jobs=JobStore(data_dir / "jobs_production.json", job_prefix="job"),
            sync_jobs=JobStore(data_dir / "jobs_sync.json", job_prefix="sync"),
            check_jobs=JobStore(data_dir / "jobs_check.json", job_prefix="check"),
            async_jobs=JobStore(data_dir / "jobs_async.json", job_prefix="task"),
            submit_lock=threading.Lock(),
            rate_limiter=RequestRateLimiter(window_seconds=rate_limit_window, max_requests=rate_limit_max),
        )

    def legacy_exports(self) -> dict[str, Any]:
        """Return legacy module-level names backed by this registry."""
        return {
            "JOBS": self.jobs,
            "SYNC_JOBS": self.sync_jobs,
            "CHECK_JOBS": self.check_jobs,
            "ASYNC_JOBS": self.async_jobs,
            "SUBMIT_LOCK": self.submit_lock,
            "RATE_LIMITER": self.rate_limiter,
            "TASK_EXECUTOR": self.task_executor,
        }


LEGACY_JOB_NAMES = {
    "sync": "sync_cloud_alphas",
    "generate": "generate_candidates_payload",
    "check": "run_check_batch_job",
    "submit": "submit_batch",
}


def legacy_job_export_names():
    return list(LEGACY_JOB_NAMES.keys())


def legacy_job_export(registry, name):
    """Map legacy job names to current job payloads."""
    return LEGACY_JOB_NAMES.get(name, name)


def resolve_web_job_registry(web):
    """Resolve the job registry from the web application context."""
    registry = getattr(web, "JOB_REGISTRY", None)
    if registry is None:
        return None
    try:
        namespace = vars(web)
    except TypeError:
        try:
            module = object.__getattribute__(web, "_module")
            namespace = vars(module)
        except (AttributeError, TypeError):
            namespace = {}

    def explicit_or_registry(name: str, registry_value: Any) -> Any:
        return namespace[name] if name in namespace else registry_value

    return WebJobRegistry(
        task_executor=explicit_or_registry("TASK_EXECUTOR", registry.task_executor),
        jobs=explicit_or_registry("JOBS", registry.jobs),
        sync_jobs=explicit_or_registry("SYNC_JOBS", registry.sync_jobs),
        check_jobs=explicit_or_registry("CHECK_JOBS", registry.check_jobs),
        async_jobs=explicit_or_registry("ASYNC_JOBS", registry.async_jobs),
        submit_lock=explicit_or_registry("SUBMIT_LOCK", registry.submit_lock),
        rate_limiter=explicit_or_registry("RATE_LIMITER", registry.rate_limiter),
    )
