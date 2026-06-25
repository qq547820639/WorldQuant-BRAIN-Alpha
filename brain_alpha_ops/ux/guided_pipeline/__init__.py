"""Guided user experience layer for progress, feedback, resume, and history.

GuidedPipeline — wraps AlphaResearchPipeline with:
  1. Step-by-step process guidance with progress indicators
  2. Real-time status feedback via callback mechanism
  3. Actionable error messages with fix suggestions
  4. Structured result presentation for the Web console
  5. Checkpoint/resume mechanism for long-running pipelines
  6. Historical run browser and replay capability

Subpackage split (formerly ``guided_pipeline.py`` monolith):
  - ``_state`` : ``classify_error`` and ``_pkg()`` accessor for monkeypatch
  - ``_base``  : ``GuidedPipelineBase`` lifecycle / progress / resume / display
  - ``_phases``: ``_PhasesMixin`` with the per-phase implementations
"""

from __future__ import annotations

# Package-level attributes that tests monkeypatch:
#   monkeypatch.setattr(guided_pipeline, "_unified_classify", ...)
#   monkeypatch.setattr(guided_pipeline, "run_pipeline_from_config", ...)
# Submodules read these via ``_pkg()`` so the patched value takes effect.
from brain_alpha_ops.error_knowledge import classify_ux_error as _unified_classify  # noqa: F401
from brain_alpha_ops.runner import run_pipeline_from_config  # noqa: F401

from ._state import classify_error, logger
from ._base import GuidedPipelineBase
from ._phases import _PhasesMixin


class GuidedPipeline(GuidedPipelineBase, _PhasesMixin):
    """Guided UX pipeline wrapper around the standard pipeline."""

    pass


# Backward-compat re-exports (original guided_pipeline.py trailing imports).
from ..guided_models import (  # noqa: F401,E402
    CheckpointData,
    PipelinePhase,
    RunRecord,
)
from ..guided_formatting import (  # noqa: F401,E402
    format_candidate_summary,
    format_error_for_user,
    format_pipeline_progress,
)

__all__ = [
    "GuidedPipeline",
    "CheckpointData",
    "PipelinePhase",
    "RunRecord",
    "classify_error",
    "format_candidate_summary",
    "format_error_for_user",
    "format_pipeline_progress",
    "run_pipeline_from_config",
]
