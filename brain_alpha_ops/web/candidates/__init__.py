"""Candidate availability checks and batch context validation."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _CANDIDATES_LAZY:
        module_name, attr = _CANDIDATES_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_CANDIDATES_LAZY: dict[str, tuple[str, str]] = {
    # web_check_availability.py
    "check_candidate_availability": (".web_check_availability", "check_candidate_availability"),
    "build_state_navigation": (".web_check_availability", "build_state_navigation"),
    "build_cloud_self_correlation_explanation": (".web_check_availability", "build_cloud_self_correlation_explanation"),
    "build_context_health_explanation": (".web_check_availability", "build_context_health_explanation"),
    "cloud_status_for": (".web_check_availability", "cloud_status_for"),
    "cloud_similarity_risk": (".web_check_availability", "cloud_similarity_risk"),
    # web_check_batch_context.py
    "check_batch_official_context_payload": (".web_check_batch_context", "check_batch_official_context_payload"),
}

__all__ = list(_CANDIDATES_LAZY.keys())
