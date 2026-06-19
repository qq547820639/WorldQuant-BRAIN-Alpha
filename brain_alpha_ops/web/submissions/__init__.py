"""Submission safety, batch/single submission, and readiness checks."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _SUBMISSIONS_LAZY:
        module_name, attr = _SUBMISSIONS_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_SUBMISSIONS_LAZY: dict[str, tuple[str, str]] = {
    # web_submission_safety.py
    "submit_preflight_block": (".web_submission_safety", "submit_preflight_block"),
    "submission_preflight_error_message": (".web_submission_safety", "submission_preflight_error_message"),
    "submission_preflight_advisory": (".web_submission_safety", "submission_preflight_advisory"),
    "observability_submission_preflight": (".web_submission_safety", "observability_submission_preflight"),
    "record_submit_blocked_event": (".web_submission_safety", "record_submit_blocked_event"),
    # web_submit_readiness.py
    "run_live_submit_readiness_check": (".web_submit_readiness", "run_live_submit_readiness_check"),
    "submit_readiness_payload": (".web_submit_readiness", "submit_readiness_payload"),
    "compact_submit_readiness_payload": (".web_submit_readiness", "compact_submit_readiness_payload"),
    "counter_rows": (".web_submit_readiness", "counter_rows"),
    "submit_readiness_next_steps": (".web_submit_readiness", "submit_readiness_next_steps"),
    "safe_int": (".web_submit_readiness", "safe_int"),
}

__all__ = list(_SUBMISSIONS_LAZY.keys())
