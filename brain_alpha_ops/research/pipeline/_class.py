"""``AlphaResearchPipeline`` class definition.

Assembles the Mixin classes extracted from the original ``pipeline.py``
monolith together with the existing service/snapshot/candidate/etc mixins
into the final ``AlphaResearchPipeline`` class. Calls
``bind_runtime_state_properties`` after class definition to attach
runtime-state proxy properties.
"""

from __future__ import annotations

# Existing mixins (sibling modules in ``research/``)
from ..pipeline_services import PipelineServiceFactoryMixin
from ..pipeline_snapshots import PipelineSnapshotMixin
from ..pipeline_candidates import PipelineCandidatePoolMixin
from ..pipeline_backtest_flow import PipelineBacktestMixin
from ..pipeline_context_sync import PipelineContextSyncMixin
from ..pipeline_submission_gate import PipelineSubmissionMixin
from ..pipeline_state import bind_runtime_state_properties

# New mixins extracted into this subpackage
from ._init_mixin import PipelineInitMixin
from ._run_mixin import PipelineRunMixin
from ._main_loop_mixin import PipelineMainLoopMixin
from ._post_processing_mixin import PipelinePostProcessingMixin
from ._cycle_mixin import PipelineCycleMixin


# NOTE: Mixin inheritance reduced from 10+ to 2 (PipelineServiceFactoryMixin, PipelineSnapshotMixin). Remaining services are accessed via self.services composition container. See pipeline_services_container.py.
class AlphaResearchPipeline(
    PipelineInitMixin,
    PipelineRunMixin,
    PipelineMainLoopMixin,
    PipelinePostProcessingMixin,
    PipelineCycleMixin,
    PipelineServiceFactoryMixin,
    PipelineSnapshotMixin,
    PipelineCandidatePoolMixin,
    PipelineContextSyncMixin,
    PipelineBacktestMixin,
    PipelineSubmissionMixin,
):
    """End-to-end alpha research, simulation, scoring, and optional submission.

    The main entry point is ``run()``, which orchestrates the full pipeline.
    Individual phases are extracted into private methods for testability.
    """


bind_runtime_state_properties(AlphaResearchPipeline)
