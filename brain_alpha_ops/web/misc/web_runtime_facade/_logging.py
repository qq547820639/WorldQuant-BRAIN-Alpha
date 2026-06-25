"""Shared logger for the ``web_runtime_facade`` subpackage.

The logger name matches the original module path so that ``caplog``-based
tests and ``monkeypatch`` of ``facade.logger`` continue to work after the
split.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("brain_alpha_ops.web.misc.web_runtime_facade")
