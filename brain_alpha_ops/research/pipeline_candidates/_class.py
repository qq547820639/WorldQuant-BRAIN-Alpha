"""``PipelineCandidatePoolMixin`` class definition.

Assembles the Mixin classes extracted from the original
``pipeline_candidates.py`` monolith into the final
``PipelineCandidatePoolMixin`` class.
"""

from __future__ import annotations

from ._cloud_risk_mixin import _CloudRiskMixin
from ._local_prefilter import _LocalPrefilterMixin
from ._official_context_mixin import _OfficialContextMixin
from ._pool_management import _CandidatePoolManagementMixin


class PipelineCandidatePoolMixin(
    _LocalPrefilterMixin,
    _CandidatePoolManagementMixin,
    _OfficialContextMixin,
    _CloudRiskMixin,
):
    """Candidate scoring, pool, and cloud-risk helpers for AlphaResearchPipeline."""
