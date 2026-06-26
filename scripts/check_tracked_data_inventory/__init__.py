"""Inventory tracked data files so runtime artifacts stay visible.

Re-export shim. The implementation has been split into the
``scripts.check_tracked_data_inventory`` subpackage (Task A7 of
deep-optimization-phase12). The public API is re-exported here so
``from scripts.check_tracked_data_inventory import ...`` continues to
resolve to the package directory (Python prefers the package ``__init__.py``
over the sibling ``scripts/check_tracked_data_inventory.py`` shim when
both exist). The thin ``scripts/check_tracked_data_inventory.py`` shim
remains only to preserve ``python scripts/check_tracked_data_inventory.py``
direct CLI invocation, including the ``sys.path`` bootstrap.

This script is read-only. It reports tracked files under ``data/`` and
classifies them so callers can separate intentional snapshots from runtime
artifacts that still need a human boundary decision.

The original module had no loggers (only ``print``-based CLI output), so no
hardcoded logger name is required by Task A7.2.
"""

from __future__ import annotations

import subprocess  # noqa: F401  -- exposed for monkeypatch compatibility in tests

from ._boundary import (
    _boundary_decision_todo,
    _boundary_plan_summary,
    _boundary_recommendations,
    _empty_boundary_plan,
)
from ._classify import _classify
from ._cli import main
from ._constants import (
    BOUNDARY_STATUSES,
    DEFAULT_BOUNDARY_PLAN,
    QUALIFICATION_SNAPSHOT_PATHS,
    REFERENCE_EXCLUDED_PATHS,
    REFERENCE_EXCLUDED_PREFIXES,
    REVIEW_ARTIFACT_PREFIXES,
    ROOT,
    RUNTIME_GENERATED_PATHS,
    RUNTIME_GENERATED_PREFIXES,
    SNAPSHOT_PREFIXES,
)
from ._core import inventory_tracked_data
from ._git import (
    _changed_tracked_data_files,
    _is_reference_excluded,
    _runtime_generated_references,
    _tracked_data_files,
)
from ._summary import _count_summary, _human_summary_lines

__all__ = [
    "ROOT",
    "DEFAULT_BOUNDARY_PLAN",
    "BOUNDARY_STATUSES",
    "RUNTIME_GENERATED_PREFIXES",
    "RUNTIME_GENERATED_PATHS",
    "SNAPSHOT_PREFIXES",
    "QUALIFICATION_SNAPSHOT_PATHS",
    "REVIEW_ARTIFACT_PREFIXES",
    "REFERENCE_EXCLUDED_PREFIXES",
    "REFERENCE_EXCLUDED_PATHS",
    "inventory_tracked_data",
    "main",
]
