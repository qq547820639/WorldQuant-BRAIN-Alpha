"""``AlphaResearchPipeline`` main class plus entry-point mixins.

Consolidated from the original ``pipeline.py`` monolith's split files
(``_class`` / ``_init_mixin`` / ``_run_mixin``). Holds the user-facing
shell: class assembly (binding all mixins together), ``__init__`` and
the top-level ``run()`` entry point that orchestrates
auth → context load → production context → main loop → persist.

The inner per-cycle mechanics live in ``pipeline_mixins.py`` and are
re-assembled onto ``AlphaResearchPipeline`` via multiple inheritance.
"""

from __future__ import annotations

import enum
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.audit_trail.anti_overfit import make_strategy_audit_sink
from brain_alpha_ops.brain_api.base import BrainAPI
from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.execution_backend import AlphaExecutionBackend
from brain_alpha_ops.models import PipelineResult, new_id
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from brain_alpha_ops.redaction import redact_error_message

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
from ..pipeline_helpers import rank_candidates
from ..pipeline_state import (
    CycleState,
    PipelineRuntimeState,
    bind_runtime_state_properties,
)
from ..production_context import build_production_context
from ..research_cycle_orchestrator import ResearchCycleOrchestrator
from ..repository import ResearchRepository
from ..safety import SubmissionLedger
from ..strategy_lifecycle import StrategyLifecycleTracker

# Existing mixins (sibling modules in ``research/``)
from ..pipeline_services import PipelineServiceFactoryMixin
from ..pipeline_snapshots import PipelineSnapshotMixin
from ..pipeline_candidates import PipelineCandidatePoolMixin
from ..pipeline_backtest_flow import PipelineBacktestMixin
from ..pipeline_context_sync import PipelineContextSyncMixin
from ..pipeline_submission_gate import PipelineSubmissionMixin

# Inner cycle machinery mixins (merged into this subpackage)
from .pipeline_mixins import (
    PipelineMainLoopMixin,
    PipelinePostProcessingMixin,
    PipelineCycleMixin,
)

# Preserve the original ``brain_alpha_ops.research.pipeline`` logger name so
# downstream log filters and test caplog assertions keep working after the
# monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline")


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
            strategy_lifecycle=StrategyLifecycleTracker(record_sink=make_strategy_audit_sink(lambda row: self.services.runtime._record_strategy_lifecycle(row))),
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


class PipelineRunMixin:
    """Top-level ``run()`` orchestration extracted from the monolith."""

    def run(self, *, auto_submit: bool = False) -> PipelineResult:
        """Orchestrate the full alpha research pipeline.

        Phases: auth → context load → production context → main loop → persist.
        """
        run_id = new_id("run")
        self.run_id = run_id
        submitted_this_run = 0
        state = CycleState()

        self.services.runtime._event("run_started", "Research pipeline started.")
        self.services.runtime._progress("startup", 0, 1, "准备认证并加载官方字段/算子上下文。")
        self.api.authenticate()
        self.services.runtime._recover_persisted_backtest_slots()

        # P1-8: Fetch user profile (tier, level, points) after authentication
        self.user_profile: dict = {}
        try:
            self.user_profile = self.api.get_user_profile()
            self.services.runtime._event("user_profile_loaded",
                f"User: {self.user_profile.get('tier', 'unknown')}, "
                f"Level: {self.user_profile.get('level', 'N/A')}, "
                f"Points: {self.user_profile.get('points', 'N/A')}", level="INFO")
        except Exception as exc:
            message = redact_error_message(exc, max_length=100)
            self.user_profile = {"tier": "error", "error": message}
            self.services.runtime._event("user_profile_failed",
                f"Could not fetch user profile: {message}", level="WARN")

        self.services.context_sync._sync_cloud_alphas()
        fields, operators = self.services.context_sync._load_official_context()

        # Build live-verified production context
        self.production_context: dict = build_production_context(
            user_profile=self.user_profile, official_fields=fields or [], config=self.config)
        self.services.runtime._event("production_context_ready",
            f"Tier: {self.production_context.get('account_tier')}, "
            f"Profiles: {self.production_context.get('eligible_profiles_count')}, "
            f"Safe fields: {self.production_context.get('safe_field_count')} (excl. VECTOR)",
            level="INFO")
        profile = self.services.strategy._current_strategy_profile()
        self.strategy_lifecycle.propose(profile, index=self.strategy_profile_index,
            cycle=0, reason="initial adaptive strategy profile")
        self.services.runtime._notify_strategy_plugins("propose", profile,
            cycle=0, reason="initial adaptive strategy profile")

        # Inject live-verified fields into the generator module
        try:
            from ..validated_generator import set_active_safe_fields
            set_active_safe_fields(self.production_context["safe_fields"])
        except Exception:
            logger.warning("Failed to inject live safe-fields into generator", exc_info=True)

        if self.progress_callback and self.user_profile:
            self.services.runtime._progress("startup", 0.5, 1,
                f"用户: {self.user_profile.get('tier', '-')} "
                f"Lv.{self.user_profile.get('level', '-')} "
                f"积分 {self.user_profile.get('points', '-')}",
                data={"user_profile": self.user_profile})

        # ── Enter main loop ──
        cycle_orchestrator = ResearchCycleOrchestrator(
            run_forever=self.config.budget.run_forever,
            max_cycles=self.config.budget.max_cycles,
            should_stop=self.services.runtime._should_stop)
        pipeline_start_time = time.time()
        max_cycle_runtime = int(getattr(self.config.budget, 'max_cycle_runtime_seconds', 0) or 600)
        max_pipeline_runtime = int(getattr(self.config.budget, 'max_pipeline_runtime_seconds', 0) or 3600)
        logger.info('pipeline entering main loop — max_cycle=%s, cycle_timeout=%ds, pipeline_timeout=%ds',
            self.config.budget.max_cycles, max_cycle_runtime, max_pipeline_runtime)

        submitted_this_run, fields, operators, state = self._run_main_loop(
            state=state, fields=fields, operators=operators, auto_submit=auto_submit,
            cycle_orchestrator=cycle_orchestrator, pipeline_start_time=pipeline_start_time,
            max_cycle_runtime=max_cycle_runtime, max_pipeline_runtime=max_pipeline_runtime,
            submitted_this_run=submitted_this_run)

        # ── Finalization ──
        archive_stats = state.archive_stats
        pool_by_expression = state.pool_by_expression
        accepted_candidates = state.accepted_candidates

        final_candidates = rank_candidates(accepted_candidates + list(pool_by_expression.values()))
        summary = self._summary(final_candidates, submitted_this_run, pool_by_expression, archive_stats)
        self.services.runtime._event("run_completed", "Research pipeline completed.", data=summary)
        run_status = "stopped" if self.services.runtime._should_stop() else "completed"
        if run_status == "stopped":
            self.services.runtime._progress("stopped", 0, 1, "用户已停止连续生产队列。", data=summary)
        else:
            self.services.runtime._progress("completed", 1, 1, "生产、评价、排序和回测等待流程完成。", data=summary)
        for candidate in final_candidates:
            self.repository.save_candidate(run_id, candidate)
            self.repository.save_family_record(candidate)
        for event in self.events:
            self.repository.save_event(run_id, event)
        result = PipelineResult(run_id=run_id, candidates=final_candidates, events=self.events, summary=summary)
        try:
            self.repository.save_run_history(run_id, result.to_dict(), status=run_status,
                parameter_audit=build_parameter_audit_snapshot(
                    self.config, auto_submit=auto_submit, source="pipeline_run"),
                experiment_id=self._experiment_id,
                experiment_version=self._experiment_version)
        except Exception as exc:
            message = redact_error_message(exc)
            logger.warning("failed to persist run history for %s: %s", run_id, message)
            logger.debug("run history persistence traceback for %s", run_id, exc_info=True)
            # Record the persistence failure as a pipeline event so it is
            # surfaced in the event stream instead of being silently logged.
            self.services.runtime._event(
                "run_history_persist_failed",
                f"Failed to persist run history: {message}",
                level="WARN",
            )

        # P1-2: Auto-record trend after pipeline run
        try:
            from brain_alpha_ops.web.api.trends import record_trend
            record_trend(
                candidates=len(final_candidates) if final_candidates else 0,
                submissions=submitted_this_run,
                completed_cycles=state.cycle if hasattr(state, 'cycle') else 0,
            )
        except (ValueError, TypeError, OSError):
            pass

        # Auto-calibration check (non-blocking)
        try:
            from ..calibration import auto_calibrate_if_stalled
            calib = auto_calibrate_if_stalled(self.config.storage_dir)
            if calib.get("triggered") and calib.get("advice"):
                reason = calib.get("reason")
                advice = calib.get("advice")
                logger.info("auto_calibration triggered: %s", reason)
                self.services.runtime._event(
                    "auto_calibration",
                    f"Auto-calibration triggered: {reason}",
                    data={"triggered": True, "reason": reason, "advice": advice},
                )
        except Exception as exc:
            logger.warning("auto_calibration skipped: %s", redact_error_message(exc))
            logger.debug("auto_calibration skipped traceback", exc_info=True)

        return result


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
