"""Audit-trail GET route handlers (Workstream D4.1).

Thin wrappers around ``web.misc.web_scoring_interpreter.handle_audit_export``
so the dispatch layer can serve ``/api/audit/export`` through the standard
GET pipeline.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext


def _get_audit_export(
    handler: Any,
    parsed: Any,
    _ctx: WebHandlerDispatchContext,
) -> None:
    from brain_alpha_ops.web_scoring_interpreter import handle_audit_export

    handler._json(handle_audit_export(parse_qs(parsed.query)))


__all__: list[str] = []
