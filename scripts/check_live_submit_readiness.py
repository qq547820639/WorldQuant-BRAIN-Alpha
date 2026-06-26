"""Validate live submit readiness for the current candidate set.

Re-export shim. The implementation has been split into the
``scripts.check_live_submit_readiness`` subpackage (Task A1 of
deep-optimization-phase12). This file remains for backward compatibility so:

* ``python scripts/check_live_submit_readiness.py`` still works as a
  direct CLI invocation (this shim bootstraps ``sys.path`` for
  ``brain_alpha_ops`` and delegates to ``main()``).
* ``from scripts.check_live_submit_readiness import ...`` continues to
  work — Python resolves the import to the sibling package directory's
  ``__init__.py``, which re-exports the public API.

Note: when both ``check_live_submit_readiness.py`` and
``check_live_submit_readiness/__init__.py`` exist, Python resolves
``scripts.check_live_submit_readiness`` to the package directory. The
``__init__.py`` is the live module; this file is a safety net for direct
script execution only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_live_submit_readiness import main  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
