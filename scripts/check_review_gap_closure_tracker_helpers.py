"""Helper utilities for the review gap closure tracker validator.

Re-export shim. The implementation has been split into the
``scripts.check_review_gap_closure_tracker_helpers`` subpackage (Task A9 of
deep-optimization-phase12). This file remains for backward compatibility so:

* ``python scripts/check_review_gap_closure_tracker_helpers.py`` still works
  as a direct execution entry point (this shim bootstraps ``sys.path`` for
  ``brain_alpha_ops`` and re-exports the public API).
* ``from scripts.check_review_gap_closure_tracker_helpers import ...``
  continues to work — Python resolves the import to the sibling package
  directory's ``__init__.py``, which re-exports the public API.

Note: when both ``check_review_gap_closure_tracker_helpers.py`` and
``check_review_gap_closure_tracker_helpers/__init__.py`` exist, Python resolves
``scripts.check_review_gap_closure_tracker_helpers`` to the package directory.
The ``__init__.py`` is the live module; this file is a safety net for direct
script execution only. The original module never exposed a ``main()`` entry
point — it is a pure helper library — so direct execution simply re-exports
the API and exits cleanly.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_review_gap_closure_tracker_helpers import (  # noqa: E402,F401
    ADDITIONAL_TRIAGE_ITEMS,
    ADDITIONAL_TRIAGE_SNIPPETS,
    OFFICIAL_CONTEXT_QUEUE_ITEM,
    check_official_context_baseline_facts,
    check_official_context_queue,
    check_official_context_refresh_baseline,
    check_official_context_refresh_queue,
    check_real_submit_queue,
    expect_all,
    finding,
    frontend_mirror_only_decision,
    frontend_surface_requires_queue,
    has_fact,
    live_submit_readiness_status,
    official_context_refresh_status,
    official_context_status,
    reject_any,
    section,
    table_cells,
    table_row,
)


if __name__ == "__main__":
    # Helper library: no standalone CLI. Re-export succeeds; exit cleanly.
    raise SystemExit(0)
