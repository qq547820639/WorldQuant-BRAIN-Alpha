"""End-to-end alpha research, simulation, scoring, and optional submission.

Subpackage consolidation (formerly split across ``_class.py`` /
``_init_mixin.py`` / ``_run_mixin.py`` / ``_main_loop_mixin.py`` /
``_post_processing_mixin.py`` / ``_cycle_mixin.py``):
  - ``pipeline``: ``AlphaResearchPipeline`` class assembly +
    ``PipelineInitMixin`` (``__init__``, ``services``, ``_Phase`` enum) and
    ``PipelineRunMixin`` (top-level ``run()`` method)
  - ``pipeline_mixins``: ``PipelineMainLoopMixin`` (``_run_main_loop``),
    ``PipelinePostProcessingMixin`` (per-cycle convergence/calibration/fusion
    logic), ``PipelineCycleMixin`` (dataset-selection, assistant-guidance,
    and simulation phase helpers)

Constants:
  - ``SUBMITTED_CLOUD_STATUSES``: cloud Alpha statuses considered submitted
  - ``CONVERGENCE_REPORT_INTERVAL``: cycles between convergence reports
  - ``CONTEXT_REFRESH_INTERVAL_SECONDS``: official-context refresh window
"""

from __future__ import annotations

from .pipeline import AlphaResearchPipeline
from .pipeline_mixins import CONVERGENCE_REPORT_INTERVAL, CONTEXT_REFRESH_INTERVAL_SECONDS
from ..pipeline_services_container import PipelineServices

# Re-export of observability helper so legacy imports
# ``from brain_alpha_ops.research.pipeline import build_research_observability_snapshot``
# continue to work and remain patchable by tests that monkeypatch
# ``brain_alpha_ops.research.pipeline.build_research_observability_snapshot``.
from ..observability import build_research_observability_snapshot  # noqa: F401

SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}

__all__ = [
    "AlphaResearchPipeline",
    "PipelineServices",
    "SUBMITTED_CLOUD_STATUSES",
    "CONVERGENCE_REPORT_INTERVAL",
    "CONTEXT_REFRESH_INTERVAL_SECONDS",
    "build_research_observability_snapshot",
]
