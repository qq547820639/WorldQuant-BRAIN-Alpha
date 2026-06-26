"""Shared state for the execution_adapter package.

Holds the module logger (hardcoded to the original module path so log
records continue to attribute to ``brain_alpha_ops.browser.execution_adapter``
after the split) and the navigation timeout constant shared across the
adapter submodules.

Extracted from the former ``execution_adapter.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("brain_alpha_ops.browser.execution_adapter")

_DEFAULT_NAV_TIMEOUT_MS = 30000
