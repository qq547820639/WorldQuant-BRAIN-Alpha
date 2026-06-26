"""Tracked-data file classifier.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Maps a tracked data file's relative
path to one of the canonical categories (``runtime_generated``,
``official_snapshot``, ``qualification_snapshot``, ``review_artifact``, or
``unclassified``) using the prefix/path tables defined in ``_constants``.
"""

from __future__ import annotations

from ._constants import (
    QUALIFICATION_SNAPSHOT_PATHS,
    REVIEW_ARTIFACT_PREFIXES,
    RUNTIME_GENERATED_PATHS,
    RUNTIME_GENERATED_PREFIXES,
    SNAPSHOT_PREFIXES,
)


def _classify(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized in RUNTIME_GENERATED_PATHS:
        return "runtime_generated"
    if normalized.startswith(RUNTIME_GENERATED_PREFIXES):
        return "runtime_generated"
    if normalized.startswith(SNAPSHOT_PREFIXES):
        return "official_snapshot"
    if normalized in QUALIFICATION_SNAPSHOT_PATHS:
        return "qualification_snapshot"
    if normalized.startswith(REVIEW_ARTIFACT_PREFIXES):
        return "review_artifact"
    return "unclassified"
