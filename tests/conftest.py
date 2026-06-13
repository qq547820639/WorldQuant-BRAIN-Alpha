from __future__ import annotations

"""Pytest configuration: ensure test environment enables controlled overrides for kill-switches.

Production code paths (REAL_SUBMIT_DISABLED_WEB_FLOW, etc.) are tested by
unit tests that need to bypass the safety gates.  This conftest sets the
required env vars at session start so the invariant-guard tests work without
each test having to set the var itself.
"""

import os

# Test-only override for the F-02/F-03 invariant guard on submit_alpha().
# Production web console never reaches submit_alpha() because the higher-level
# gate returns REAL_SUBMIT_DISABLED_WEB_FLOW first.
os.environ.setdefault("BRAIN_ALPHA_FORCE_REAL_SUBMIT", "1")
