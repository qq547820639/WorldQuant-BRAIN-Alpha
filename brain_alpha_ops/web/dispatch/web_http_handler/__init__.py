"""HTTP handler factory for the local web console.

Re-export subpackage (deep-optimization-phase13, Task A4). The former
``web_http_handler.py`` monolith (382 lines) has been split into two
responsibility-focused submodules:

  - ``_helpers``: ``logger`` + ``_json_default`` + CORS allowlist helpers
    (``_is_origin_allowed`` / ``_get_cors_allowed_origins`` /
    ``_CORS_ALLOWED_ORIGINS_CACHE``) + SSE status classification helpers
    (``_is_terminal_status`` / ``_sse_event_type``)
  - ``_handler``: the ``create_handler_class`` factory that builds a
    ``BaseHTTPRequestHandler`` subclass bound to the supplied dispatch
    callbacks and resolvers.

The public API and the private symbols referenced by tests are re-exported
here so the legacy import paths continue to resolve unchanged:

  - ``from brain_alpha_ops.web.dispatch.web_http_handler import create_handler_class``
  - ``from brain_alpha_ops.web_http_handler import create_handler_class, _is_terminal_status, _sse_event_type``
    (the flat path is redirected by ``brain_alpha_ops._web_bridge``)

``time`` is imported at package scope so that
``monkeypatch.setattr("brain_alpha_ops.web_http_handler.time.monotonic", ...)``
continues to resolve: the package attribute ``time`` is the same module
object the ``_handler`` submodule uses, and patching its ``monotonic``
attribute is therefore observed by the SSE stream loop.
"""

from __future__ import annotations

import time  # noqa: F401  re-exported for monkeypatch.setattr("...time.monotonic", ...)

from ._helpers import (
    _CORS_ALLOWED_ORIGINS_CACHE,
    _get_cors_allowed_origins,
    _is_origin_allowed,
    _is_terminal_status,
    _json_default,
    _sse_event_type,
    logger,
)
from ._handler import create_handler_class

__all__ = [
    "create_handler_class",
    "logger",
    # Private helpers re-exported for monkeypatch / direct-import compatibility
    "_CORS_ALLOWED_ORIGINS_CACHE",
    "_get_cors_allowed_origins",
    "_is_origin_allowed",
    "_is_terminal_status",
    "_json_default",
    "_sse_event_type",
]
