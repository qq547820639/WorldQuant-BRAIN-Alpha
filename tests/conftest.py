from __future__ import annotations

"""Pytest configuration for safe local test collection."""

import sys
import os
from pathlib import Path

# Add tests/ directory to Python path so test files can import from each other
tests_dir = str(Path(__file__).parent)
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)

def pytest_ignore_collect(collection_path, config):
    """Skip e2e tests when playwright is not installed (CI does not have browser deps)."""
    path_text = str(collection_path)
    if "/e2e/" in path_text or "tests/e2e" in path_text or "e2e_" in path_text:
        if os.environ.get("BRAIN_BROWSER_E2E_LIVE") != "1":
            return True
        try:
            import playwright  # noqa: F401
        except ImportError:
            return True
    return None
