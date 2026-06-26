"""Automated BRAIN canonical compliance verification.

Re-export shim. The implementation has been split into the
``scripts.verify_canonical_compliance`` subpackage (Task A8 of
deep-optimization-phase12).
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.verify_canonical_compliance import main, verify_all  # noqa: E402,F401
if __name__ == "__main__":
    raise SystemExit(main())
