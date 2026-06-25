"""Dataclasses and shared logger for production diagnostics.

The diagnostic snapshot is structured around two small value types:
``GapRow`` (one row of the gap matrix) and ``PriorityItem`` (one entry in the
priority attack list).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

# Preserve the original logger name ``brain_alpha_ops.production_diagnostics``
# so log records stay attributable after the subpackage split.
logger = logging.getLogger("brain_alpha_ops.production_diagnostics")


@dataclass(frozen=True)
class GapRow:
    dimension: str
    current_state: str
    gap: str
    severity: str
    evidence: str
    upgrade: str


@dataclass(frozen=True)
class PriorityItem:
    priority: str
    area: str
    finding: str
    fix: str
    validation: str
