"""Snapshot builders for pipeline runtime and result payloads.

Consolidated (formerly split across ``_state`` / ``_builder`` /
``_backtest_slots``) into a single ``pipeline_snapshot`` module that
holds the ``PipelineSnapshotServices`` and ``PipelineSnapshotState``
dataclass containers, the ``PipelineSnapshotBuilder`` class assembling
runtime and summary payloads, and the ``backtest_slot_snapshot`` renderer
for slot progress.
"""

from __future__ import annotations

from .pipeline_snapshot import (
    PipelineSnapshotBuilder,
    PipelineSnapshotServices,
    PipelineSnapshotState,
    backtest_slot_snapshot,
)

__all__ = [
    "PipelineSnapshotBuilder",
    "PipelineSnapshotServices",
    "PipelineSnapshotState",
    "backtest_slot_snapshot",
]
