"""Validate the defect/implementation tracking document contract.

Re-export shim. The implementation has been split into the
``scripts.check_review_gap_closure_tracker`` subpackage (Task A3 of
deep-optimization-phase12). The public API is re-exported here so
``from scripts.check_review_gap_closure_tracker import ...`` continues to
resolve to the package directory (Python prefers the package ``__init__.py``
over the sibling ``scripts/check_review_gap_closure_tracker.py`` shim when
both exist). The thin ``scripts/check_review_gap_closure_tracker.py`` shim
remains only to preserve ``python scripts/check_review_gap_closure_tracker.py``
direct CLI invocation, including the ``sys.path`` bootstrap for
``brain_alpha_ops``.
"""

from __future__ import annotations

from ._cli import main
from ._constants import (
    BASE_QUEUE_ITEMS,
    BASELINE_CHECKS,
    BASELINE_SNIPPETS,
    DEFAULT_CONFIG,
    DEFAULT_DELIVERY_AUDIT,
    DEFAULT_JOBS,
    DEFAULT_REACT_APP_DIR,
    DEFAULT_REFRESH_STATUS,
    DEFAULT_TRACKER,
    DELIVERY_AUDIT_SNIPPETS,
    FRONTEND_SURFACE_QUEUE_ITEM,
    NOT_YET_SNIPPETS,
    OFFICIAL_CONTEXT_QUEUE_ITEM,
    REQUIRED_SECTIONS,
    ROOT,
    SCHEMA_VERSION,
    STALE_DELIVERY_AUDIT_SNIPPETS,
    STATUS_MATRIX_ITEMS,
    TRACKER_STALE_SNIPPETS,
    TRIAGE_ITEMS,
    TRIAGE_SNIPPETS,
)
from ._core import check_review_gap_closure_tracker

__all__ = [
    "ROOT",
    "OFFICIAL_CONTEXT_QUEUE_ITEM",
    "DEFAULT_TRACKER",
    "DEFAULT_DELIVERY_AUDIT",
    "DEFAULT_CONFIG",
    "DEFAULT_JOBS",
    "DEFAULT_REFRESH_STATUS",
    "DEFAULT_REACT_APP_DIR",
    "SCHEMA_VERSION",
    "REQUIRED_SECTIONS",
    "BASELINE_SNIPPETS",
    "BASELINE_CHECKS",
    "TRIAGE_SNIPPETS",
    "TRIAGE_ITEMS",
    "STATUS_MATRIX_ITEMS",
    "BASE_QUEUE_ITEMS",
    "FRONTEND_SURFACE_QUEUE_ITEM",
    "NOT_YET_SNIPPETS",
    "DELIVERY_AUDIT_SNIPPETS",
    "STALE_DELIVERY_AUDIT_SNIPPETS",
    "TRACKER_STALE_SNIPPETS",
    "check_review_gap_closure_tracker",
    "main",
]
