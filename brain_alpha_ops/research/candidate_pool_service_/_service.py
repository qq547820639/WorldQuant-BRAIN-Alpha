"""``CandidatePoolService_`` class assembly.

Extracted from the original ``candidate_pool_service_.py`` monolith. The
service orchestrates candidate scoring, pool management, and cloud-risk
checks for ``AlphaResearchPipeline``. The method bodies live in three
responsibility mixins (``_LocalPrefilterMixin``, ``_PoolOpsMixin``,
``_CloudRiskMixin``) which are mixed in here to keep this file under the
per-submodule line budget while preserving the public class API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_alpha_ops.research.candidate_pool_service_._cloud_risk import (
    _CloudRiskMixin,
)
from brain_alpha_ops.research.candidate_pool_service_._local_prefilter import (
    _LocalPrefilterMixin,
)
from brain_alpha_ops.research.candidate_pool_service_._pool_ops import (
    _PoolOpsMixin,
)

if TYPE_CHECKING:
    from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


class CandidatePoolService_(_LocalPrefilterMixin, _PoolOpsMixin, _CloudRiskMixin):
    """Standalone candidate pool service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline
