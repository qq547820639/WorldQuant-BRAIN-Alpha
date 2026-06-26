"""BrowserExecutionAdapter — bridges BrainBrowserRunner → AlphaExecutionBackend Protocol.

Wraps Playwright-driven browser interactions behind the execution_backend.AlphaExecutionBackend
Protocol, so the production pipeline can transparently switch between browser-first and API
execution paths.

Usage::

    from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter
    from brain_alpha_ops.execution_backend import AlphaExecutionBackend

    backend: AlphaExecutionBackend = BrowserExecutionAdapter(
        username="user@example.com",
        password="secret",
    )
    with backend:
        backend.authenticate({"username": "...", "password": "..."})
        result = backend.simulate_alpha("rank(returns)", {})

Re-export subpackage. The implementation has been split from the former
``execution_adapter.py`` monolith (deep-optimization-phase13) into
responsibility-focused submodules:

- ``_state``    : module logger (hardcoded name) + navigation timeout constant
- ``_base``     : ``BrowserExecutionAdapterBase`` dataclass — fields, context
                  manager, ``authenticate``, ``get_evidence``, ``_submit_failure``
- ``_simulate`` : ``_SimulateMixin`` — ``simulate_alpha`` and ``check_alpha``
- ``_submit``   : ``_SubmitMixin`` — ``submit_alpha``

The public API, the module logger, and the private navigation-timeout constant
are re-exported here so ``from brain_alpha_ops.browser.execution_adapter import ...``
continues to resolve to this package directory.
"""

from __future__ import annotations

from ._state import _DEFAULT_NAV_TIMEOUT_MS, logger
from ._base import BrowserExecutionAdapterBase
from ._simulate import _SimulateMixin
from ._submit import _SubmitMixin


class BrowserExecutionAdapter(BrowserExecutionAdapterBase, _SimulateMixin, _SubmitMixin):
    """Production adapter: browser-first executor implementing AlphaExecutionBackend.

    Combines the lifecycle/auth/evidence base with the simulate/check and
    submit operation mixins. Field definitions and the ``@dataclass``
    decorator live on :class:`BrowserExecutionAdapterBase`; this class
    inherits them unchanged.
    """

    pass


__all__ = [
    "BrowserExecutionAdapter",
    "BrowserExecutionAdapterBase",
    "_DEFAULT_NAV_TIMEOUT_MS",
    "logger",
]
