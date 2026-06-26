"""Validate production defect tracking evidence for the 2026-06-02 report.

Re-export shim. The implementation has been split into the
``scripts.check_prod_defect_tracking`` subpackage (Task A6 of
deep-optimization-phase12). This file remains for backward compatibility so:
* ``python scripts/check_prod_defect_tracking.py`` still works as a direct CLI invocation.
* ``from scripts.check_prod_defect_tracking import ...`` continues to work.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.check_prod_defect_tracking import main  # noqa: E402,F401
if __name__ == "__main__":
    raise SystemExit(main())
