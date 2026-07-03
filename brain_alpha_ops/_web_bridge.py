"""Meta-path bridge: redirects brain_alpha_ops.web_* flat imports to web/<sub>/.

Installed from both brain_alpha_ops/__init__.py (early) and
brain_alpha_ops/web/__init__.py (per-web-package fallback). Idempotent.
"""
from __future__ import annotations

import sys
import importlib as _importlib
from importlib.abc import Loader
from importlib.machinery import ModuleSpec

_WEB_BRIDGE_MAP: dict[str, tuple[str, str]] = {
    "brain_alpha_ops.web_routes": ("brain_alpha_ops.web.dispatch", "web_routes"),
    "brain_alpha_ops.web_handler_dispatch": ("brain_alpha_ops.web.dispatch", "web_handler_dispatch"),
    "brain_alpha_ops.web_http_handler": ("brain_alpha_ops.web.dispatch", "web_http_handler"),
    "brain_alpha_ops.web_handler_dispatch_core": ("brain_alpha_ops.web.dispatch", "web_handler_dispatch_core"),
    "brain_alpha_ops.web_handler_candidate_routes": ("brain_alpha_ops.web.dispatch", "web_handler_candidate_routes"),
    "brain_alpha_ops.web_get_handlers": ("brain_alpha_ops.web.dispatch", "web_get_handlers"),
    "brain_alpha_ops.web_post_handlers": ("brain_alpha_ops.web.dispatch", "web_post_handlers"),
    "brain_alpha_ops.web_dispatch_context": ("brain_alpha_ops.web.dispatch", "web_dispatch_context"),
    "brain_alpha_ops.web_business": ("brain_alpha_ops.web.business", "web_business"),
    "brain_alpha_ops.web_async_jobs": ("brain_alpha_ops.web.business", "web_async_jobs"),
    "brain_alpha_ops.web_jobs": ("brain_alpha_ops.web.business", "web_jobs"),
    "brain_alpha_ops.web_run_job": ("brain_alpha_ops.web.business", "web_run_job"),
    "brain_alpha_ops.web_job_registry": ("brain_alpha_ops.web.business", "web_job_registry"),
    "brain_alpha_ops.web_config": ("brain_alpha_ops.web.config", "web_config"),
    "brain_alpha_ops.web_capability_registry": ("brain_alpha_ops.web.config", "web_capability_registry"),
    "brain_alpha_ops.web_config_schema": ("brain_alpha_ops.web.config", "web_config_schema"),
    "brain_alpha_ops.web_check_availability": ("brain_alpha_ops.web.candidates", "web_check_availability"),
    "brain_alpha_ops.web_check_batch_context": ("brain_alpha_ops.web.candidates", "web_check_batch_context"),
    "brain_alpha_ops.web_submission_safety": ("brain_alpha_ops.web.submissions", "web_submission_safety"),
    "brain_alpha_ops.web_submission_batch": ("brain_alpha_ops.web.submissions", "web_submission_batch"),
    "brain_alpha_ops.web_submission_single": ("brain_alpha_ops.web.submissions", "web_submission_single"),
    "brain_alpha_ops.web_submit_readiness": ("brain_alpha_ops.web.submissions", "web_submit_readiness"),
    "brain_alpha_ops.web_session": ("brain_alpha_ops.web.security", "web_session"),
    "brain_alpha_ops.web_csp": ("brain_alpha_ops.web.security", "web_csp"),
    "brain_alpha_ops.web_security": ("brain_alpha_ops.web.security", "web_security"),
    "brain_alpha_ops.web_state_contract": ("brain_alpha_ops.web.state", "web_state_contract"),
    "brain_alpha_ops.web_runtime_state": ("brain_alpha_ops.web.state", "web_runtime_state"),
    "brain_alpha_ops.web_cli": ("brain_alpha_ops.web.misc", "web_sse"),
    "brain_alpha_ops.web_html": ("brain_alpha_ops.web.misc", "web_errors"),
    "brain_alpha_ops.web_sse": ("brain_alpha_ops.web.misc", "web_sse"),
    "brain_alpha_ops.web_sse_compat": ("brain_alpha_ops.web.misc", "web_sse"),
    "brain_alpha_ops.web_errors": ("brain_alpha_ops.web.misc", "web_errors"),
    "brain_alpha_ops.web_rate_limit": ("brain_alpha_ops.web.misc", "web_errors"),
    "brain_alpha_ops.web_facade_bindings": ("brain_alpha_ops.web.misc", "web_facade_bindings"),
    "brain_alpha_ops.web_service_namespace": ("brain_alpha_ops.web.misc", "web_service_namespace"),
    "brain_alpha_ops.web_server_lifecycle": ("brain_alpha_ops.web.misc", "web_payload_validation"),
    "brain_alpha_ops.web_application_context": ("brain_alpha_ops.web.dispatch", "web_dispatch_context"),
    "brain_alpha_ops.web_runtime_facade": ("brain_alpha_ops.web.misc", "web_runtime_facade"),
    "brain_alpha_ops.web_payload_validation": ("brain_alpha_ops.web.misc", "web_payload_validation"),
    "brain_alpha_ops.web_progress": ("brain_alpha_ops.web.misc", "web_alpha_lifecycle"),
    "brain_alpha_ops.web_redline_scoring": ("brain_alpha_ops.web.misc", "web_scoring_interpreter"),
    "brain_alpha_ops.web_scoring_interpreter": ("brain_alpha_ops.web.misc", "web_scoring_interpreter"),
    "brain_alpha_ops.web_review": ("brain_alpha_ops.web.misc", "web_snapshot_facade"),
    "brain_alpha_ops.web_review_api": ("brain_alpha_ops.web.misc", "web_snapshot_facade"),
    "brain_alpha_ops.web_sqlite_indexes": ("brain_alpha_ops.web.misc", "web_payload_validation"),
    "brain_alpha_ops.web_simulation_job": ("brain_alpha_ops.web.misc", "web_alpha_lifecycle"),
    "brain_alpha_ops.web_snapshots": ("brain_alpha_ops.web.misc", "web_assistant_snapshots"),
    "brain_alpha_ops.web_snapshot_facade": ("brain_alpha_ops.web.misc", "web_snapshot_facade"),
    "brain_alpha_ops.web_snapshot_runtime": ("brain_alpha_ops.web.misc", "web_snapshot_facade"),
    "brain_alpha_ops.web_snapshot_bindings": ("brain_alpha_ops.web_candidates", "bindings"),
    "brain_alpha_ops.web_runtime_bindings": ("brain_alpha_ops.web.misc", "web_facade_bindings"),
    "brain_alpha_ops.web_job_bindings": ("brain_alpha_ops.web_candidates", "bindings"),
    "brain_alpha_ops.web_config_bindings": ("brain_alpha_ops.web_candidates", "bindings"),
    "brain_alpha_ops.web_session_bindings": ("brain_alpha_ops.web_candidates", "bindings"),
    "brain_alpha_ops.web_backtest_slots": ("brain_alpha_ops.web.misc", "web_backtest_slots"),
    "brain_alpha_ops.web_alpha_lifecycle": ("brain_alpha_ops.web.misc", "web_alpha_lifecycle"),
    "brain_alpha_ops.web_assistant_snapshots": ("brain_alpha_ops.web.misc", "web_assistant_snapshots"),
    "brain_alpha_ops.web_cloud_context_refresh": ("brain_alpha_ops.web_cloud", "snapshot"),
    "brain_alpha_ops.web_sync_status_payload": ("brain_alpha_ops.web.misc", "web_payload_validation"),
}


class _AliasLoader(Loader):
    """Loader that returns a pre-resolved target module without re-executing it.

    This prevents the import system from creating a duplicate module object
    when the bridge finder aliases a flat name (e.g. ``brain_alpha_ops.web_sse``)
    to its canonical subpackage path (e.g. ``brain_alpha_ops.web.misc.web_sse``).
    """

    def __init__(self, target_module):
        self._target = target_module

    def create_module(self, spec):
        return self._target

    def exec_module(self, module):
        pass  # Target module is already fully initialised.


class _WebBridgeFinder:
    """Meta-path finder: redirects brain_alpha_ops.web_* to web/<sub>/."""

    def __init__(self):
        # P3-7: precompute bridge prefix set to avoid dict scan on every import.
        self._bridge_names = frozenset(_WEB_BRIDGE_MAP)

    def find_spec(self, fullname: str, path=None, target=None):
        if fullname not in self._bridge_names:
            return None
        if fullname in sys.modules:
            return None
        package, name = _WEB_BRIDGE_MAP[fullname]
        target_fullname = f"{package}.{name}"
        if target_fullname in sys.modules:
            # Do NOT set sys.modules[fullname] here: _find_spec() checks
            # ``name in sys.modules`` after find_spec() returns and, if true,
            # returns ``sys.modules[name].__spec__`` (the target's original
            # spec) instead of the alias spec we just built. That would make
            # _load_unlocked re-execute the target module under its original
            # name, creating a duplicate module object. Let _load_unlocked
            # populate sys.modules via the alias spec instead.
            target_module = sys.modules[target_fullname]
            return ModuleSpec(fullname, _AliasLoader(target_module))
        mod = _importlib.import_module(f".{name}", package=package)
        return ModuleSpec(fullname, _AliasLoader(mod))


def install_web_bridge() -> None:
    """Install meta-path finder if not already present (idempotent)."""
    if not any(isinstance(f, _WebBridgeFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _WebBridgeFinder())
