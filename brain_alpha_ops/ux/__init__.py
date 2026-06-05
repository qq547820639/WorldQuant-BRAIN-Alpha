"""User experience (UX) package for BRAIN Alpha Ops.

Provides user-friendly error translation, status code localization,
and workflow guidance components for the web console and CLI.
"""

from __future__ import annotations

# Lazy imports to avoid circular dependencies and keep the package light.
# Individual modules can be imported directly:
#   from brain_alpha_ops.ux.errors import translate_error

__all__ = [
    "translate_error",
    "translate_status_code",
    "translate_check_result",
    "get_phase_guidance",
    "format_gate_failure",
]


def __getattr__(name: str):
    if name in __all__:
        from brain_alpha_ops.ux import errors as _errors
        return getattr(_errors, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
