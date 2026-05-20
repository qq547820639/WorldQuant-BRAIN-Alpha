#!/usr/bin/env python
"""Quick launcher for the BRAIN Alpha scoring validation experiment.

This script checks credentials first, then launches the full experiment.

Usage:
    $env:BRAIN_USERNAME = "your@email.com"
    $env:BRAIN_PASSWORD = "your_password"
    python experiments/run.py
    python experiments/run.py --candidates 20  # quick test
"""

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))


def check_credentials() -> bool:
    """Verify BRAIN credentials are set."""
    username = os.getenv("BRAIN_USERNAME", "")
    password = os.getenv("BRAIN_PASSWORD", "")
    token = os.getenv("BRAIN_TOKEN", "")

    if token:
        print("[OK] BRAIN_TOKEN found")
        return True

    if username and password:
        print(f"[OK] BRAIN_USERNAME found: {username[:3]}***@***")
        print("[OK] BRAIN_PASSWORD found: ***")
        return True

    print("=" * 60)
    print("  ERROR: BRAIN credentials not found!")
    print("=" * 60)
    print()
    print("Please set environment variables before running:")
    print()
    print("  PowerShell:")
    print('    $env:BRAIN_USERNAME = "your@email.com"')
    print('    $env:BRAIN_PASSWORD = "your_password"')
    print()
    print("  or")
    print('    $env:BRAIN_TOKEN = "your_token"')
    print()
    print("Then re-run: python experiments/run.py")
    return False


def main() -> int:
    if not check_credentials():
        return 1

    # Launch the experiment
    from experiments.validate_scoring import main as experiment_main
    return experiment_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
