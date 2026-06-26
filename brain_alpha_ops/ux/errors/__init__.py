"""User-facing error translation and status-code localization.

Re-export from the ``errors`` subpackage for backward compatibility.

Split from the former ``brain_alpha_ops/ux/errors.py`` monolith
(deep-optimization-phase13) into responsibility-focused submodules:
``_status_codes``, ``_error_messages``, ``_check_results``, and
``_phase_guidance``. Public API and any private symbols referenced by
tests are re-exported here so existing imports of
``brain_alpha_ops.ux.errors`` continue to resolve.

Usage::

    from brain_alpha_ops.ux.errors import translate_error, translate_status_code
    friendly = translate_error(raw_error_message)
    status_text = translate_status_code("SUBMISSION_READY")
"""
from __future__ import annotations

from brain_alpha_ops.ux.errors._check_results import (  # noqa: F401
    format_gate_failure,
    translate_check_result,
)
from brain_alpha_ops.ux.errors._error_messages import (  # noqa: F401
    _ERROR_PATTERNS,
    _extract_error_code,
    translate_error,
)
from brain_alpha_ops.ux.errors._phase_guidance import (  # noqa: F401
    PHASE_GUIDANCE,
    get_phase_guidance,
)
from brain_alpha_ops.ux.errors._status_codes import (  # noqa: F401
    STATUS_CODE_ZH,
    translate_status_code,
)

__all__ = [
    "PHASE_GUIDANCE",
    "STATUS_CODE_ZH",
    "format_gate_failure",
    "get_phase_guidance",
    "translate_check_result",
    "translate_error",
    "translate_status_code",
]
