"""Re-export from the ``decoupled_pipeline`` subpackage for backward compatibility.

The original monolithic ``decoupled_pipeline.py`` was split into the
``brain_alpha_ops.research.decoupled_pipeline`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.
"""
from __future__ import annotations

# Re-export everything from sub-modules
from brain_alpha_ops.research.decoupled_pipeline._pipeline import *  # noqa: F401,F403
from brain_alpha_ops.research.decoupled_pipeline._state import *  # noqa: F401,F403
from brain_alpha_ops.research.decoupled_pipeline._workers import *  # noqa: F401,F403
from brain_alpha_ops.research.decoupled_pipeline._workers_ext import *  # noqa: F401,F403

# Explicitly re-export all worker classes, coordinator, pipeline, and state.
from brain_alpha_ops.research.decoupled_pipeline._pipeline import (  # noqa: F401
    DecoupledCoordinator,
    DecoupledPipeline,
)
from brain_alpha_ops.research.decoupled_pipeline._state import (  # noqa: F401
    SharedState,
    WorkerState,
)
from brain_alpha_ops.research.decoupled_pipeline._workers import (  # noqa: F401
    FilterWorker,
    ProductionWorker,
)
from brain_alpha_ops.research.decoupled_pipeline._workers_ext import (  # noqa: F401
    OptimizationWorker,
    ValidationWorker,
)
