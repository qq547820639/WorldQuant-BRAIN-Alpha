"""Audit the production inline console and React mirror navigation surfaces.

Re-export shim. The implementation has been split into the
``scripts.check_frontend_surface_parity`` subpackage (Task A10 of
deep-optimization-phase12).
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.check_frontend_surface_parity import main  # noqa: E402,F401
if __name__ == "__main__":
    raise SystemExit(main())
