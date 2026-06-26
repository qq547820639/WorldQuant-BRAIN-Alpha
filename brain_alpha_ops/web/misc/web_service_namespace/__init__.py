"""Re-export from the ``web_service_namespace`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.web.misc.web_service_namespace._imports_a import *  # noqa: F401,F403
from brain_alpha_ops.web.misc.web_service_namespace._imports_b import *  # noqa: F401,F403
from brain_alpha_ops.web.misc.web_service_namespace._builder import build_web_service_namespace  # noqa: F401

# ``__all__`` mirrors the dynamic pattern used by ``_imports_a`` and
# ``_imports_b``: every aliased name (all ``_``-prefixed) plus the single
# public callable ``build_web_service_namespace``.  The import-group
# sub-modules each define their own dynamic ``__all__`` enumerating every
# aliased name, so we follow the same convention here.
__all__ = [name for name in dir() if not name.startswith("__")]
