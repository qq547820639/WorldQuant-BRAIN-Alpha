"""Auth, session, CSP, and secure credentials modules."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _SECURITY_LAZY:
        module_name, attr = _SECURITY_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_SECURITY_LAZY: dict[str, tuple[str, str]] = {
    # web_session.py
    "DEFAULT_SESSION_TTL_SECONDS": (".web_session", "DEFAULT_SESSION_TTL_SECONDS"),
    "csrf_for_session": (".web_session", "csrf_for_session"),
    "new_session_id": (".web_session", "new_session_id"),
    "has_valid_request_session": (".web_session", "has_valid_request_session"),
    "validate_replay_request": (".web_session", "validate_replay_request"),
    "is_allowed_request": (".web_session", "is_allowed_request"),
    "session_id_from_cookie": (".web_session", "session_id_from_cookie"),
    "mark_brain_connection_verified": (".web_session", "mark_brain_connection_verified"),
    # web_csp.py
    "content_security_policy_for_html": (".web_csp", "content_security_policy_for_html"),
    # web_security.py
    "_is_allowed_local_request": (".web_security", "_is_allowed_local_request"),
}

__all__ = list(_SECURITY_LAZY.keys())
