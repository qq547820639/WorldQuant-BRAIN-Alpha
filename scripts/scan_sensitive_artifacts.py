"""Scan local logs/data for accidentally persisted credentials.

Re-export shim. The implementation has been split into the
``scripts.scan_sensitive_artifacts`` subpackage (Workstream F3.9). This file
remains for backward compatibility so:

* ``python scripts/scan_sensitive_artifacts.py`` still works as a direct
  CLI invocation (this shim bootstraps ``sys.path`` for ``brain_alpha_ops``
  and delegates to ``main()``).
* ``from scripts.scan_sensitive_artifacts import ...`` continues to work —
  Python resolves the import to the sibling package directory's
  ``__init__.py``, which re-exports the public API.

Note: when both ``scan_sensitive_artifacts.py`` and
``scan_sensitive_artifacts/__init__.py`` exist, Python resolves
``scripts.scan_sensitive_artifacts`` to the package directory. The
``__init__.py`` is the live module; this file is a safety net for direct
script execution only.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scan_sensitive_artifacts import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
