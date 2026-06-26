"""Web facade binding builder.

Phase 1-B: this delegates to the original flat web_*_bindings stub modules
which in turn re-export from the consolidated web/bindings.py.

Re-export subpackage. The implementation has been split from the former
``web_facade_bindings.py`` monolith (deep-optimization-phase12, Task B8)
into responsibility-focused submodules. The public API and the private
binding aliases are re-exported here so
``from brain_alpha_ops.web.misc.web_facade_bindings import ...`` continues
to resolve to this package directory.
"""

from __future__ import annotations

from ._candidate_imports import *  # noqa: F401, F403
from ._runtime_imports import *  # noqa: F401, F403
from ._snapshot_imports import *  # noqa: F401, F403
from ._builder import build_web_facade_bindings

__all__ = ["build_web_facade_bindings"]
