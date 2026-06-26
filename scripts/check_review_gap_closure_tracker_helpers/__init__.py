"""Helper utilities for the review gap closure tracker validator.

Re-export shim. The implementation has been split into the
``scripts.check_review_gap_closure_tracker_helpers`` subpackage (Task A9 of
deep-optimization-phase12). The public API is re-exported here so
``from scripts.check_review_gap_closure_tracker_helpers import ...`` continues
to resolve to the package directory (Python prefers the package ``__init__.py``
over the sibling ``scripts/check_review_gap_closure_tracker_helpers.py`` shim
when both exist). The thin ``scripts/check_review_gap_closure_tracker_helpers.py``
shim remains only to preserve ``python scripts/check_review_gap_closure_tracker_helpers.py``
direct execution, including the ``sys.path`` bootstrap for ``brain_alpha_ops``.
"""

from __future__ import annotations

from ._constants import (
    ADDITIONAL_TRIAGE_ITEMS,
    ADDITIONAL_TRIAGE_SNIPPETS,
    OFFICIAL_CONTEXT_QUEUE_ITEM,
)
from ._frontend import (
    frontend_mirror_only_decision,
    frontend_surface_requires_queue,
)
from ._queue_checks import (
    check_official_context_baseline_facts,
    check_official_context_queue,
    check_official_context_refresh_baseline,
    check_official_context_refresh_queue,
    check_real_submit_queue,
)
from ._status import (
    _load_official_context_validation,
    _optional_int,
    _record_count,
    live_submit_readiness_status,
    official_context_refresh_status,
    official_context_status,
)
from ._text_helpers import (
    _check_baseline_row_values,
    expect_all,
    finding,
    has_fact,
    reject_any,
    section,
    table_cells,
    table_row,
)

__all__ = [
    "OFFICIAL_CONTEXT_QUEUE_ITEM",
    "ADDITIONAL_TRIAGE_SNIPPETS",
    "ADDITIONAL_TRIAGE_ITEMS",
    "section",
    "expect_all",
    "has_fact",
    "reject_any",
    "check_real_submit_queue",
    "live_submit_readiness_status",
    "official_context_refresh_status",
    "check_official_context_refresh_baseline",
    "check_official_context_baseline_facts",
    "check_official_context_refresh_queue",
    "official_context_status",
    "check_official_context_queue",
    "frontend_mirror_only_decision",
    "frontend_surface_requires_queue",
    "table_row",
    "table_cells",
    "finding",
    "_check_baseline_row_values",
    "_record_count",
    "_optional_int",
    "_load_official_context_validation",
]
