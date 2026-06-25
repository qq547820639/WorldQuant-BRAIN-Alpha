"""Initialization mixin for ``AlphaResearchPipeline``.

Extracted from the original ``pipeline.py`` monolith. Holds the
``__init__``, ``services`` accessor, and the ``_Phase`` enum used to
signal phase-control flow inside the main loop.
"""

from __future__ import annotations

import enum
import random
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPI
from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.execution_backend import AlphaExecutionBackend

from ..alpha_checks import AlphaCheckRegistry
from ..auto_calibrator import AutoCalibrator
from ..backtest_slots import BacktestSlotManager
from ..convergence import ConvergenceTracker
from ..generator import CandidateGenerator
from ..knowledge_base import StructuredKnowledgeBase
from ..llm_review import CrossReviewService
from ..local_backtest_config import PREFILTER_BACKTEST_DATES, PREFILTER_BACKTEST_SYMBOLS
from ..local_backtest_engine import LocalBacktestEngine
from ..official_call_guard import OfficialCallGuard
from ..pipeline_state import PipelineRuntimeState
from ..repository import ResearchRepository
from ..safety import SubmissionLedger
from ..strategy_lifecycle import StrategyLifecycleTracker


class PipelineInitMixin:
    """Initialization and service-accessor methods."""

    class _Phase(enum.Enum):
        CONTINUE = "continue"
        SKIP = "skip"
        BREAK = "break"

    def __init__(
        self,
        *,
        config: OpsConfig,
        api: BrainAPI | None = None,
        execution_backend: AlphaExecutionBackend | None = None,
        repository: ResearchRepository | None = None,
        ledger: SubmissionLedger | None = None,
        progress_callback: Callable[[dict], None] | None = None,
        stop_callback: Callable[[], bool] | None = None,
        experiment_id: str = "",
        experiment_version: str = "",
    ) -> None:
        if api is None and execution_backend is None:
            raise ValueError(
                "Either 'api' or 'execution_backend' must be provided. "
                "Use 'api' for direct BrainAPI usage, or 'execution_backend' "
                "for browser/API backend selection via AlphaExecutionBackend."
            )
        if execution_backend is not None and api is None:
            from brain_alpha_ops.brain_api.brain_api_bridge import BrainAPIBridge
            # Pass underlying API if backend has one (for data queries)
            underlying_api = getattr(execution_backend, '_api', None)
            api = BrainAPIBridge(execution_backend, api=underlying_api)
        backtest_slot_manager = BacktestSlotManager()
        self._experiment_id = experiment_id
        self._experiment_version = experiment_version
        self._runtime_state = PipelineRuntimeState(
            config=config,
            api=api,
            repository=repository or ResearchRepository(config.storage_dir),
            ledger=ledger or SubmissionLedger(config.storage_dir),
            generator=CandidateGenerator(),
            progress_callback=progress_callback,
            stop_callback=stop_callback,
            _local_data_dir_existed_at_start=Path(config.storage_dir).exists(),
            official_call_guard=OfficialCallGuard(),
            _knowledge_base=StructuredKnowledgeBase(config.storage_dir),
            _local_backtest_engine=LocalBacktestEngine(
                seed=config.budget.random_seed,
                n_dates=PREFILTER_BACKTEST_DATES,
                n_symbols=PREFILTER_BACKTEST_SYMBOLS,
            ),
            _cross_review_service=CrossReviewService(),
            backtest_slot_manager=backtest_slot_manager,
            backtest_slots=backtest_slot_manager.slots,
            strategy_lifecycle=StrategyLifecycleTracker(record_sink=lambda row: self.services.runtime._record_strategy_lifecycle(row)),
            cloud_sync={
                "status": "not_started",
                "range": config.budget.cloud_sync_range,
                "count": 0,
                "warning": "",
            },
            check_registry=AlphaCheckRegistry(),
            convergence=ConvergenceTracker(window_size=10, stall_threshold=5, rng=random.Random(config.budget.random_seed)),
            auto_calibrator=AutoCalibrator(storage_dir=getattr(config, "storage_dir", "data")),
        )
        # ── Composition-based service container ──
        self._services_container = None
        self.strategy_profile_index = self.services.strategy._initial_strategy_profile_index()
        # ── P1-2: AlphaCheckRegistry for BRAIN-standard quality checks ──
        self.check_registry.build_default_checks()

        # P1-5: Register type-specific checks (POWER_POOL / ATOM / PYRAMID)
        alpha_type = str(getattr(config.settings, 'type', 'REGULAR') or 'REGULAR').upper()
        if alpha_type != "REGULAR":
            self.check_registry.build_type_checks(alpha_type)
            self.services.runtime._event("type_checks_registered",
                f"Alpha type '{alpha_type}': registered type-specific checks.",
                level="INFO")

        self.strategy_plugins = self.services.runtime._load_strategy_plugins()
        # ── P0-2: Iterative optimizer (lazy-init with loader/mapper after context load) ──

    @property
    def services(self):
        """Composition-based service accessor (recommended for new code).

        This provides access to all pipeline services through a single
        object, avoiding the need to inherit from Mixin classes.
        Services are created on first access and cached.
        """
        if self._services_container is None:
            from ..pipeline_services_container import PipelineServices
            self._services_container = PipelineServices(self)
        return self._services_container
