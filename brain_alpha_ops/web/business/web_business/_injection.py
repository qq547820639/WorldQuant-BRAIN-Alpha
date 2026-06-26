"""Dependency injection points for web business handlers."""

from __future__ import annotations

import sys

# ═══════════════════════════════════════════════════════════════════════
# B-07: Explicit dependency injection points (replaces globals().get())
# These module-level variables are set by web/__init__.py at application
# startup, making the dependency graph explicit and IDE-trackable.
# ═══════════════════════════════════════════════════════════════════════

_load_run_config_injected = None
_run_config_from_payload_injected = None
_web_error_injected = None
_submit_background_job_injected = None
_job_registry_injected = None


def _pkg():
    return sys.modules["brain_alpha_ops.web.business.web_business"]


def inject_dependencies(
    *,
    load_run_config=None,
    run_config_from_payload=None,
    web_error=None,
    submit_background_job=None,
    job_registry=None,
):
    """Inject web-module dependencies for production use.

    Called by web/__init__.py during application startup. Each kwarg maps
    to the function or object that the business layer needs.
    """
    pkg = _pkg()
    if load_run_config is not None:
        pkg._load_run_config_injected = load_run_config
    if run_config_from_payload is not None:
        pkg._run_config_from_payload_injected = run_config_from_payload
    if web_error is not None:
        pkg._web_error_injected = web_error
    if submit_background_job is not None:
        pkg._submit_background_job_injected = submit_background_job
    if job_registry is not None:
        pkg._job_registry_injected = job_registry
