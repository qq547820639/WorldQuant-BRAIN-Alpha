"""Web job registry bindings."""

from __future__ import annotations

from brain_alpha_ops.web_job_registry import resolve_web_job_registry

from ._helpers import _app_context, _web


def job_registry():
    return _web().JOB_REGISTRY


def job_registry_view():
    return resolve_web_job_registry(_app_context())


def active_auxiliary_operation(exclude="", allow_production=False):
    web = _web()
    registry = job_registry_view()
    return web._active_auxiliary_operation_service(
        production_store=registry.jobs,
        sync_store=registry.sync_jobs,
        check_store=registry.check_jobs,
        submit_lock=registry.submit_lock,
        exclude=exclude,
        allow_production=allow_production,
    )


def rate_limit_request(key, method, path):
    return job_registry_view().rate_limiter.check(key=key, method=method, path=path)


def submit_background_job(target, *args) -> None:
    job_registry_view().task_executor.submit(target, *args)
