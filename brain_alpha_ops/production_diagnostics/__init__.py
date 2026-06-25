"""Production diagnosis and gap analysis for the BRAIN alpha system.

Subpackage split (formerly ``production_diagnostics.py`` monolith):
  - ``__init__``: public API re-export shim
  - ``_models``: ``GapRow`` / ``PriorityItem`` dataclasses + shared logger
  - ``_probes``: scoring / frontend / history / official-refresh probes
  - ``_analysis``: contract comparison, gap matrix, priority items
  - ``_snapshot``: ``build_diagnostic_snapshot`` orchestrator
  - ``_render``: Markdown rendering and JSON serialization
"""
from __future__ import annotations

from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS  # noqa: F401
from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier  # noqa: F401
from brain_alpha_ops.config import RunConfig, load_run_config  # noqa: F401

from ._analysis import (  # noqa: F401
    _completed_items,
    _contract_comparison,
    _gap_matrix,
    _priority_items,
    _unfinished_items,
    _upgrade_plan,
)
from ._models import GapRow, PriorityItem, logger  # noqa: F401
from ._probes import (  # noqa: F401
    _frontend_inline_status,
    _history_replay_status,
    _official_context_counts,
    _official_refresh_status,
    _read_refresh_attempt_status,
    _scoring_probe,
)
from ._render import (  # noqa: F401
    _md_cell,
    _report_verdict,
    render_one_page_markdown,
    snapshot_to_json,
    write_diagnostic_report,
)
from ._snapshot import build_diagnostic_snapshot  # noqa: F401

__all__ = [
    "CANONICAL_THRESHOLDS",
    "GapRow",
    "PriorityItem",
    "RedLineVerifier",
    "RunConfig",
    "build_diagnostic_snapshot",
    "load_run_config",
    "logger",
    "render_one_page_markdown",
    "snapshot_to_json",
    "write_diagnostic_report",
]
