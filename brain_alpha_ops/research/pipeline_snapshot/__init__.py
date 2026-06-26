"""Snapshot builders for pipeline runtime and result payloads.

Subpackage split (formerly ``pipeline_snapshot.py`` monolith):
  - ``_state``          : ``PipelineSnapshotServices`` and
    ``PipelineSnapshotState`` dataclass containers
  - ``_builder``        : ``PipelineSnapshotBuilder`` class assembling runtime
    and summary payloads
  - ``_backtest_slots`` : ``backtest_slot_snapshot`` renderer for slot progress
"""

from __future__ import annotations

from ._state import PipelineSnapshotServices, PipelineSnapshotState
from ._builder import PipelineSnapshotBuilder
from ._backtest_slots import backtest_slot_snapshot

__all__ = [
    "PipelineSnapshotBuilder",
    "PipelineSnapshotServices",
    "PipelineSnapshotState",
    "backtest_slot_snapshot",
]
