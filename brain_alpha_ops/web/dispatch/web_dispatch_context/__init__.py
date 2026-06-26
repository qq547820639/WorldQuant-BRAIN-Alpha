"""Web application context and dispatch context types.

Subpackage split (formerly ``web_dispatch_context.py``):
  ``__init__`` re-export shim; ``_allowed_names`` the
  ``WEB_CONTEXT_ALLOWED_NAMES`` whitelist; ``_app_context`` the
  ``WebApplicationContext`` facade; ``_handler`` the ``WebHandler`` Protocol;
  ``_groups`` the seven ``WebDispatch*Context`` frozen dataclasses plus the
  group registry; ``_dispatch_context`` the composite
  ``WebHandlerDispatchContext`` and its builder helper.
"""
from __future__ import annotations

from ._allowed_names import WEB_CONTEXT_ALLOWED_NAMES  # noqa: F401
from ._app_context import WebApplicationContext  # noqa: F401
from ._dispatch_context import WebHandlerDispatchContext  # noqa: F401
from ._groups import (  # noqa: F401
    WebDispatchActionContext,
    WebDispatchAssistantContext,
    WebDispatchConfigContext,
    WebDispatchCoreContext,
    WebDispatchJobContext,
    WebDispatchResearchContext,
    WebDispatchSessionContext,
)
from ._handler import WebHandler  # noqa: F401

__all__ = [
    "WEB_CONTEXT_ALLOWED_NAMES",
    "WebApplicationContext",
    "WebDispatchActionContext",
    "WebDispatchAssistantContext",
    "WebDispatchConfigContext",
    "WebDispatchCoreContext",
    "WebDispatchJobContext",
    "WebDispatchResearchContext",
    "WebDispatchSessionContext",
    "WebHandler",
    "WebHandlerDispatchContext",
]
