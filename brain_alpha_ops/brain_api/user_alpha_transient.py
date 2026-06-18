"""User-alpha transient retry constants (P2-4 centralisation).

Previously duplicated verbatim across ``brain_api/official_alphas.py`` and
``brain_api/official_context.py``.  Now defined once here and re-exported
from those modules for backwards compatibility.
"""

from __future__ import annotations

import http.client
import urllib.error

USER_ALPHA_TRANSIENT_RETRY_STATUSES: frozenset[int] = frozenset({408, 500, 502, 503, 504})
USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS = (
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    TimeoutError,
    urllib.error.URLError,
)
USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS: int = 3
USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS: float = 5.0
