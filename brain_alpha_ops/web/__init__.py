"""Local web console for BRAIN Alpha Ops.

Serves the React frontend and provides API endpoints for the complete
alpha research business loop.  See ``web_handler_dispatch.py`` (routes),
``web_handler_dispatch_core.py`` (dispatch loop), and
``web_facade_bindings.py`` (import-time facade surface) for the split.

The bulk of the legacy re-exports and bootstrap logic (``Handler`` class,
``serve`` / ``shutdown_server`` helpers, compat facade installers) live
in ``_reexports.py``.  This module keeps only the side effects that must
operate on ``brain_alpha_ops.web``'s own namespace: the facade bindings
install (which calls ``globals().update(...)``), the
``WEB_APPLICATION_CONTEXT`` singleton, the package-level ``__getattr__``,
and the explicit ``__all__``.
"""

from __future__ import annotations

import sys

# Private bootstrap symbols used by the side-effect code below.
from ._reexports import (  # noqa: F401
    _WebApplicationContext,
    _build_web_facade_bindings,
    _build_web_service_namespace,
    _get_snapshot_export_names,
    _load_run_config,
    _web_runtime_facade,
    logger,
)
# Public re-exports + compat facade wrappers installed by _reexports.
from ._reexports import *  # noqa: F401,F403

# Service namespace stored for lazy lookup via __getattr__ (Phase 2a refactoring).
# This avoids polluting the module globals with ~160 private names while keeping
# backward compatibility for ``web._xxx_service`` access patterns.
_SERVICE_NS: dict = _build_web_service_namespace()

# ``_web_submit_readiness`` is needed by the submit-readiness helpers below,
# which MUST live in this module so that ``monkeypatch.setattr(web,
# "_run_live_submit_readiness_check", ...)`` is observed by
# ``web._submit_readiness_payload()`` (the lookup goes through this module's
# globals, not ``_reexports``').
from brain_alpha_ops.web.submissions import web_submit_readiness as _web_submit_readiness

# Explicit binding required by the web facade contract check
# (``check_web_facade_contract`` looks for an ``ast.Assign`` target named
# ``WebApplicationContext`` in this file's AST).
WebApplicationContext = _WebApplicationContext


# ═══════════════════ Inlined from web_legacy_exports.py (Phase 3.3) ═══════
_LEGACY_EXPORT_SPECS = (
    ("RunConfig", "_RunConfig"),
    ("load_run_config", "_load_run_config"),
    ("runtime_project_root", "_runtime_project_root"),
    ("payload_truthy", "_payload_truthy"),
    ("public_config_schema", "_public_config_schema"),
    ("web_html", "_web_html"),
    ("DEFAULT_FIELDS", "_DEFAULT_FIELDS"),
    ("DEFAULT_OPERATORS", "_DEFAULT_OPERATORS"),
    ("tail_text_lines", "_tail_text_lines_service"),
    ("error_payload", "_error_payload"),
    ("ThreadTaskExecutor", "_ThreadTaskExecutor"),
    ("WebJobRegistry", "_WebJobRegistry"),
    ("build_research_observability_snapshot", "_build_research_observability_snapshot"),
    ("ResearchRepository", "_ResearchRepository"),
    ("SubmissionLedger", "_SubmissionLedger"),
    ("api_from_run_config", "_api_from_run_config"),
    ("run_pipeline_from_config", "_run_pipeline_from_config"),
    ("DurableJobStore", "_DurableJobStore"),
    ("run_check_batch_job_service", "_run_check_batch_job_service"),
    ("check_candidate_payload", "_check_candidate_payload"),
    ("candidate_official_metrics", "_candidate_official_metrics"),
    ("is_passed_candidate_for_check", "_is_passed_candidate_for_check"),
    ("official_alpha_id", "_official_alpha_id"),
    ("refresh_cloud_context_for_check_service", "_refresh_cloud_context_for_check_service"),
    ("active_job_payload", "_active_job_payload"),
    ("health_payload", "_health_payload"),
    ("job_status_payload", "_job_status_payload"),
    ("lifecycle_payload", "_lifecycle_payload"),
    ("presets_payload", "_presets_payload"),
    ("profile_payload", "_profile_payload"),
    ("assistant_response_guidance_post_payload", "_assistant_response_guidance_post_payload"),
    ("assistant_response_parse_post_payload", "_assistant_response_parse_post_payload"),
    ("background_job_start_payload", "_background_job_start_payload"),
    ("connection_test_post_payload", "_connection_test_post_payload"),
    ("save_assistant_guidance_post_payload", "_save_assistant_guidance_post_payload"),
    ("session_end_payload", "_session_end_payload"),
    ("stop_job_payload", "_stop_job_payload"),
    ("RequestRateLimiter", "_RequestRateLimiter"),
    ("WebDispatchActionContext", "_WebDispatchActionContext"),
    ("WebDispatchAssistantContext", "_WebDispatchAssistantContext"),
    ("WebDispatchConfigContext", "_WebDispatchConfigContext"),
    ("WebDispatchCoreContext", "_WebDispatchCoreContext"),
    ("WebDispatchJobContext", "_WebDispatchJobContext"),
    ("WebDispatchResearchContext", "_WebDispatchResearchContext"),
    ("WebDispatchSessionContext", "_WebDispatchSessionContext"),
    ("WebHandlerDispatchContext", "_WebHandlerDispatchContext"),
    ("dispatch_get", "_dispatch_get"),
    ("dispatch_post", "_dispatch_post"),
    ("create_handler_class", "_create_handler_class"),
    ("route_for", "_route_for"),
    ("progress_update", "_progress_update"),
    ("run_simple_async_job_service", "_run_simple_async_job_service"),
    ("run_guided_job_service", "_run_guided_job_service"),
    ("run_job_service", "_run_job_service"),
    ("web_session", "_web_session"),
    ("WebSnapshotFacade", "_WebSnapshotFacade"),
    ("WebSnapshotRuntime", "_WebSnapshotRuntime"),
    ("DEFAULT_SESSION_TTL_SECONDS", "_DEFAULT_SESSION_TTL_SECONDS"),
    ("LOOPBACK_BIND_HOSTS", "_LOOPBACK_BIND_HOSTS"),
    ("SESSION_COOKIE_NAME", "_SESSION_COOKIE_NAME"),
    ("submit_batch_payload", "_submit_batch_payload"),
    ("submit_candidate_payload", "_submit_candidate_payload"),
    ("run_sync_job_service", "_run_sync_job_service"),
    ("sync_cloud_alphas_payload", "_sync_cloud_alphas_payload"),
    ("CloudDefaults", "_CloudDefaults"),
    ("WebDefaults", "_WebDefaults"),
    ("SnapshotDefaults", "_SnapshotDefaults"),
)


def _build_legacy_imported_exports(namespace: dict) -> dict:
    """Build the legacy exports lookup from module namespace (inlined from web_legacy_exports.py)."""
    return {public_name: namespace[private_name] for public_name, private_name in _LEGACY_EXPORT_SPECS}


def _install_facade_bindings() -> None:
    """Install three distinct facade surfaces into this module's globals.

    Three surfaces coexist on purpose (P1-6 doc — do NOT consolidate):

    1. ``web_service_namespace.build_web_service_namespace`` (legacy
       import-time facade): provides backwards-compatible top-level symbols
       for tests and external scripts that historically did
       ``from brain_alpha_ops.web import X``.
       Now stored in ``_SERVICE_NS`` and resolved via ``__getattr__``.

    2. ``web_runtime_facade``: lazy runtime facade used by
       ``web_service_namespace`` for ``compute_run_stats`` and
       ``status_category``; not intended to be the production dispatch path.

    3. ``web_facade_bindings.build_web_facade_bindings``: extended facade
       used by the factory ``Handler`` defined in ``web_http_handler.py``
       for the (latent) alt-dispatch path.  Production dispatch is still
       the in-line ``Handler`` defined in this module (the factory is
       reserved for future enablement).

    See ``web_handler_dispatch.py`` for the route table and
    ``web_handler_dispatch_core.py`` for the dispatch loop.
    """
    try:
        # Build a merged namespace for facade bindings: globals + _SERVICE_NS.
        # This allows build_web_facade_bindings to access service namespace
        # values without polluting module globals.
        merged_ns = {**globals(), **_SERVICE_NS}
        from brain_alpha_ops.web.business import web_business as _business_handlers
        from brain_alpha_ops.web.business.web_business import (
            _has_valid_api_session as _business_has_valid_api_session,
            _has_valid_local_origin as _business_has_valid_local_origin,
            _persist_generated_candidates as _business_persist_generated_candidates,
            _production_job_store as _business_production_job_store,
            _real_attribution as _business_real_attribution,
            _real_check as _business_real_check,
            _real_check_batch as _business_real_check_batch,
            _real_connection as _business_real_connection,
            _real_run as _business_real_run,
            _real_score as _business_real_score,
            _real_session as _business_real_session,
            _real_stop as _business_real_stop,
            _real_submit as _business_real_submit,
            _real_submit_batch as _business_real_submit_batch,
            _real_sync as _business_real_sync,
            _safe_non_submit_run_payload as _business_safe_non_submit_run_payload,
        )

        def _legacy_real_generate(payload):
            _business_handlers.inject_dependencies(
                load_run_config=globals().get("load_run_config", _load_run_config),
            )
            return _business_handlers._real_generate(payload)

        # Inject all production dependencies so the ``_real_*`` legacy handlers
        # (``_real_run``, ``_real_check_batch``, ``_real_connection``, etc.)
        # resolve to the real services rather than ``None``.  Tests that
        # ``monkeypatch.setattr(web, "run_config_from_payload", ...)`` still
        # work because each handler falls back to ``brain_alpha_ops.web``
        # module globals when the injected callable is absent.
        _business_handlers.inject_dependencies(
            load_run_config=globals().get("load_run_config", _SERVICE_NS.get("_load_run_config", _load_run_config)),
            run_config_from_payload=globals().get("run_config_from_payload"),
            web_error=globals().get("web_error_payload") or _SERVICE_NS.get("_web_error"),
            submit_background_job=globals().get("_submit_background_job"),
            job_registry=globals().get("JOB_REGISTRY"),
        )

        globals()["_persist_generated_candidates"] = _business_persist_generated_candidates
        globals()["_real_attribution"] = _business_real_attribution
        globals()["_real_check"] = _business_real_check
        globals()["_real_check_batch"] = _business_real_check_batch
        globals()["_real_connection"] = _business_real_connection
        globals()["_real_generate"] = _legacy_real_generate
        globals()["_real_run"] = _business_real_run
        globals()["_real_score"] = _business_real_score
        globals()["_real_session"] = _business_real_session
        globals()["_real_stop"] = _business_real_stop
        globals()["_real_submit"] = _business_real_submit
        globals()["_real_submit_batch"] = _business_real_submit_batch
        globals()["_real_sync"] = _business_real_sync
        globals()["_safe_non_submit_run_payload"] = _business_safe_non_submit_run_payload
        globals()["_production_job_store"] = _business_production_job_store
        globals()["_has_valid_api_session"] = _business_has_valid_api_session
        globals()["_has_valid_local_origin"] = _business_has_valid_local_origin
        globals()["_runtime_facade"] = _web_runtime_facade
        globals().update(_build_web_facade_bindings(merged_ns))
        globals()["_LEGACY_IMPORTED_EXPORTS"] = _build_legacy_imported_exports(merged_ns)
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message; logger.error("Facade bindings install failed: %s", redact_error_message(e))


def web_application_context():
    return WEB_APPLICATION_CONTEXT


def _app_context():
    return WEB_APPLICATION_CONTEXT


# ═══════════════════════ Submit-readiness helpers ═════════════════════════
# These wrappers MUST live in this module (not in ``_reexports``) so that
# ``monkeypatch.setattr(web, "_run_live_submit_readiness_check", ...)`` is
# observed by ``web._submit_readiness_payload()`` — the name lookup goes
# through ``brain_alpha_ops.web``'s globals.
def _run_live_submit_readiness_check() -> dict:
    return _web_submit_readiness.run_live_submit_readiness_check()


def _submit_readiness_payload() -> dict:
    return _web_submit_readiness.submit_readiness_payload(_run_live_submit_readiness_check)


def _compact_submit_readiness_payload(result: dict) -> dict:
    return _web_submit_readiness.compact_submit_readiness_payload(result)


# Pre-declared for mypy — populated by _install_facade_bindings() below.
JOB_REGISTRY: object = None  # type: ignore[assignment]
_LEGACY_IMPORTED_EXPORTS: object = {}  # type: ignore[assignment]

def __getattr__(name: str):
    if name == "JOBS":
        return JOB_REGISTRY.jobs
    if name == "SYNC_JOBS":
        return JOB_REGISTRY.sync_jobs
    if name == "CHECK_JOBS":
        return JOB_REGISTRY.check_jobs
    if name == "ASYNC_JOBS":
        return JOB_REGISTRY.async_jobs
    if name == "SUBMIT_LOCK":
        return JOB_REGISTRY.submit_lock
    if name == "RATE_LIMITER":
        return JOB_REGISTRY.rate_limiter
    if name == "TASK_EXECUTOR":
        return JOB_REGISTRY.task_executor
    if name == "_backtest_slots_payload":
        from brain_alpha_ops.web_backtest_slots import backtest_slots_payload
        return backtest_slots_payload
    legacy = _LEGACY_IMPORTED_EXPORTS.get(name)
    if legacy is not None:
        return legacy
    # Service namespace lookup (Phase 2a: lazy resolution via __getattr__)
    service_val = _SERVICE_NS.get(name)
    if service_val is not None:
        return service_val
    raise AttributeError(name)

# ``main`` is re-exported from ``._reexports`` (legacy implementation) and
# then overwritten by ``_install_facade_bindings`` below with the facade
# version.  The legacy definition stays in ``_reexports`` so its free
# variables (``_main_cli``, ``serve``, ``HOST``, ``SERVER_STOP``) resolve
# against the module where it was defined.

_install_facade_bindings()
WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])

_snapshot_exports = _get_snapshot_export_names()
__all__ = ["Handler", "main", "serve", "shutdown_server", "smoke_test_server",
           "find_free_port",
           "HOST", "DEFAULT_PORT", "SERVER", "SERVER_STOP", "SERVER_LOCK",
           "SESSION_TTL_SECONDS", "SESSION_ALLOW_MULTIPLE",
           "load_run_config_provider", "config_from_payload", "_load_html",
           *_snapshot_exports]
