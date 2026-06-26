"""Fail-closed release readiness gate for final BRAIN Alpha delivery.

Re-export shim. The implementation has been split into the
``scripts.final_release_gate`` subpackage (deep-optimization-phase12,
Task A4). This file remains for backward compatibility so:

* ``python scripts/final_release_gate.py`` still works as a direct CLI
  invocation (this shim bootstraps ``sys.path`` for ``brain_alpha_ops`` and
  delegates to ``main()``).
* ``from scripts.final_release_gate import ...`` continues to work — Python
  resolves the import to the sibling package directory's ``__init__.py``,
  which re-exports the public API.

Note: when both ``final_release_gate.py`` and
``final_release_gate/__init__.py`` exist, Python resolves
``scripts.final_release_gate`` to the package directory. The ``__init__.py``
is the live module; this file is a safety net for direct script execution
only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.final_release_gate import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
