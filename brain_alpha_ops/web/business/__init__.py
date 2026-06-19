"""Business logic, job execution, and job registry modules."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _BUSINESS_LAZY:
        module_name, attr = _BUSINESS_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_BUSINESS_LAZY: dict[str, tuple[str, str]] = {
    # web_business.py
    "inject_dependencies": (".web_business", "inject_dependencies"),
    # web_async_jobs.py
    "JobStoreLike": (".web_async_jobs", "JobStoreLike"),
    "run_simple_async_job_service": (".web_async_jobs", "run_simple_async_job_service"),
    "progress_update": (".web_async_jobs", "progress_update"),
    # web_jobs.py
    "job_get": (".web_jobs", "job_get"),
    "job_update": (".web_jobs", "job_update"),
    "job_list": (".web_jobs", "job_list"),
    "job_delete": (".web_jobs", "job_delete"),
    "job_start": (".web_jobs", "job_start"),
    "new_job_id": (".web_jobs", "new_job_id"),
    "utc_timestamp": (".web_jobs", "utc_timestamp"),
    "set_jobs_storage_dir": (".web_jobs", "set_jobs_storage_dir"),
    "get_web_job_store": (".web_jobs", "get_web_job_store"),
    "init_job_persistence": (".web_jobs", "init_job_persistence"),
    "load_jobs_from_jsonl": (".web_jobs", "load_jobs_from_jsonl"),
    # web_run_job.py
    "run_job_service": (".web_run_job", "run_job_service"),
    "run_guided_job_service": (".web_run_job", "run_guided_job_service"),
    # web_job_registry.py
    "WebJobRegistry": (".web_job_registry", "WebJobRegistry"),
    "resolve_web_job_registry": (".web_job_registry", "resolve_web_job_registry"),
    "legacy_job_export_names": (".web_job_registry", "legacy_job_export_names"),
    "legacy_job_export": (".web_job_registry", "legacy_job_export"),
}

__all__ = list(_BUSINESS_LAZY.keys())
