"""Cloud snapshots, state contracts, runtime state, and sync payloads."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _STATE_LAZY:
        module_name, attr = _STATE_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_STATE_LAZY: dict[str, tuple[str, str]] = {
    # web_state_contract.py
    "enrich_error_payload": (".web_state_contract", "enrich_error_payload"),
    # web_runtime_state.py
    "WebRuntimeState": (".web_runtime_state", "WebRuntimeState"),
}

__all__ = list(_STATE_LAZY.keys())
