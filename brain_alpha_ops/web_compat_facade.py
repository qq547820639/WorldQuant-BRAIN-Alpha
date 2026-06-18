"""Backward-compatible facade wrappers for legacy test modules.

These functions provide backward-compatible signatures for test modules
that were written against the original web.py monolithic interface.
They use lazy imports to avoid circular dependency issues.

Extracted from web/__init__.py to keep that module under the size limit.
"""

from __future__ import annotations

__all__ = ["install_compat_facades", "_snapshot_funcs", "_load_html"]


def _load_html():
    """Backward-compatible loader: returns the inline HTML bundle."""
    from brain_alpha_ops.web_html import load_html as _load
    return _load()


def _compat_facade(func_name: str):
    """Return a lazy wrapper that delegates to binding modules."""
    def wrapper(*args, **kwargs):
        from brain_alpha_ops import web_candidate_bindings as _cand
        from brain_alpha_ops import web_config_bindings as _cfg
        from brain_alpha_ops import web_job_bindings as _job
        from brain_alpha_ops import web_session_bindings as _snap
        for mod in (_snap, _cand, _cfg, _job):
            fn = getattr(mod, func_name, None)
            if fn is not None:
                return fn(*args, **kwargs)
        raise AttributeError(f"web compatibility: {func_name} not found in binding modules")
    wrapper.__name__ = func_name
    return wrapper


# Snapshot/candidate binding function names that need backward-compatible wrappers.
_snapshot_funcs: list[str] = [
    "anti_overfit_snapshot", "assistant_context_snapshot",
    "assistant_cross_review_payload", "assistant_guidance_snapshot",
    "assistant_request_snapshot", "assistant_response_guidance_payload",
    "assistant_response_parse_payload", "cloud_alpha_snapshot",
    "generate_candidates_payload", "passed_candidates_from_payload",
    "public_run_config", "research_memory_snapshot",
    "research_observability_snapshot", "rolling_validation_snapshot",
    "save_assistant_guidance_payload", "sqlite_expression_lookup_payload",
    "sqlite_index_snapshot", "sqlite_record_lookup_payload",
]


def install_compat_facades(module_globals: dict) -> None:
    """Install backward-compatible wrapper functions into the caller's module namespace."""
    for name in _snapshot_funcs:
        module_globals[name] = _compat_facade(name)


def get_snapshot_export_names() -> list[str]:
    """Return the list of snapshot function names for __all__ exports."""
    return [n for n in _snapshot_funcs if n != "_load_html"]
