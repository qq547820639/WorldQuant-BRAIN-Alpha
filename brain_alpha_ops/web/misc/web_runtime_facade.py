"""Re-export from the ``web_runtime_facade`` subpackage for backward compatibility.

The implementation now lives in ``web_runtime_facade/`` submodules. This shim
keeps the original import path (``brain_alpha_ops.web.misc.web_runtime_facade``)
working for existing callers and tests that ``monkeypatch`` module-level
attributes such as ``logger``.
"""
from __future__ import annotations

from brain_alpha_ops.web.misc.web_runtime_facade import *  # noqa: F401,F403
from brain_alpha_ops.web.misc.web_runtime_facade import (  # noqa: F401
    _profile_status_code,
    _server_lock,
    logger,
)
