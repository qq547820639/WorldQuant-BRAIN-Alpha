"""End-to-end alpha research, simulation, scoring, and optional submission.

Re-export shim. The implementation has been split into the
``brain_alpha_ops.research.pipeline`` subpackage. This module remains
for backward compatibility so existing imports
``from brain_alpha_ops.research.pipeline import ...`` continue to work.

Note: when both ``pipeline.py`` and ``pipeline/__init__.py`` exist, Python
resolves ``brain_alpha_ops.research.pipeline`` to the package directory.
The ``pipeline/__init__.py`` is the live module; this file mirrors its
public API for documentation and as a safety net.
"""
from __future__ import annotations

from .pipeline.pipeline import AlphaResearchPipeline
from .pipeline.pipeline_mixins import CONVERGENCE_REPORT_INTERVAL, CONTEXT_REFRESH_INTERVAL_SECONDS
from .observability import build_research_observability_snapshot  # noqa: F401

SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}

__all__ = [
    "AlphaResearchPipeline",
    "SUBMITTED_CLOUD_STATUSES",
    "CONVERGENCE_REPORT_INTERVAL",
    "CONTEXT_REFRESH_INTERVAL_SECONDS",
    "build_research_observability_snapshot",
]
