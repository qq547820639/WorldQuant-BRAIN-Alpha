from __future__ import annotations

"""Pytest configuration: ensure test environment enables controlled overrides for kill-switches.

Production code paths (REAL_SUBMIT_DISABLED_WEB_FLOW, etc.) are tested by
unit tests that need to bypass the safety gates.  This conftest sets the
required env vars at session start so the invariant-guard tests work without
each test having to set the var itself.
"""

import os
import sys
from pathlib import Path

# Add tests/ directory to Python path so test files can import from each other
tests_dir = str(Path(__file__).parent)
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

# Test-only override for the F-02/F-03 invariant guard on submit_alpha().
# Production web console never reaches submit_alpha() because the higher-level
# gate returns REAL_SUBMIT_DISABLED_WEB_FLOW first.
os.environ.setdefault("BRAIN_ALPHA_FORCE_REAL_SUBMIT", "1")


def pytest_ignore_collect(collection_path, path, config):
    """Skip e2e tests when playwright is not installed (CI does not have browser deps)."""
    if "e2e_" in str(collection_path):
        try:
            import playwright  # noqa: F401
        except ImportError:
            return True
    return None
