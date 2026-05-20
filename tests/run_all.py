"""Run all tests using pytest.

Usage: python tests/run_all.py [pytest args ...]
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    sys.path.insert(0, project_root)

    import pytest
    args = [
        "tests/",
        "-v",
        "--tb=short",
    ] + sys.argv[1:]
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
