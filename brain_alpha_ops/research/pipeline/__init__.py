"""End-to-end alpha research, simulation, scoring, and optional submission.

Subpackage split (formerly ``pipeline.py`` monolith):
  - ``_init_mixin``: ``PipelineInitMixin`` with ``__init__``, ``services``,
    and the ``_Phase`` enum
  - ``_run_mixin``: ``PipelineRunMixin`` with the top-level ``run()`` method
  - ``_main_loop_mixin``: ``PipelineMainLoopMixin`` with ``_run_main_loop``
  - ``_post_processing_mixin``: ``PipelinePostProcessingMixin`` with
    per-cycle convergence/calibration/fusion logic
  - ``_cycle_mixin``: ``PipelineCycleMixin`` with dataset-selection,
    assistant-guidance, and simulation phase helpers
  - ``_class``: ``AlphaResearchPipeline`` class assembly + runtime-state
    property binding

Constants:
  - ``SUBMITTED_CLOUD_STATUSES``: cloud Alpha statuses considered submitted
  - ``CONVERGENCE_REPORT_INTERVAL``: cycles between convergence reports
  - ``CONTEXT_REFRESH_INTERVAL_SECONDS``: official-context refresh window
"""

from __future__ import annotations

from ._class import AlphaResearchPipeline
from ._post_processing_mixin import CONVERGENCE_REPORT_INTERVAL
from ._main_loop_mixin import CONTEXT_REFRESH_INTERVAL_SECONDS

# Re-export of observability helper so legacy imports
# ``from brain_alpha_ops.research.pipeline import build_research_observability_snapshot``
# continue to work and remain patchable by tests that monkeypatch
# ``brain_alpha_ops.research.pipeline.build_research_observability_snapshot``.
from ..observability import build_research_observability_snapshot  # noqa: F401

SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}

__all__ = [
    "AlphaResearchPipeline",
    "SUBMITTED_CLOUD_STATUSES",
    "CONVERGENCE_REPORT_INTERVAL",
    "CONTEXT_REFRESH_INTERVAL_SECONDS",
    "build_research_observability_snapshot",
]
