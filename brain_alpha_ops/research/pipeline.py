"""End-to-end alpha research, simulation, scoring, and optional submission."""

from __future__ import annotations

import enum
import logging
from pathlib import Path
import time
from typing import Callable

logger = logging.getLogger(__name__)

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.config import OpsConfig, RunConfig, runtime_project_root
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult, new_id
from brain_alpha_ops.observability import context_payload, error_payload
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from brain_alpha_ops.redaction import redact_error_message

from .generator import CandidateGenerator, extract_fields, extract_operators, local_quality, mutate_expression
from .guidance import assistant_guidance_candidate_metadata, ensure_assistant_guidance_digest
from .memory import ResearchMemory
from .knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
from .local_backtest_engine import LocalBacktestEngine
from .llm_review import CrossReviewService
from .assistant import build_assistant_request_pack
from .context import build_assistant_context_pack
from .observability import build_research_observability_snapshot
from .repository import ResearchRepository
from .safety import SubmissionLedger
from .scoring import build_scorecard, evaluate_quality_gate
from .alpha_checks import AlphaCheckRegistry
from .anti_overfit import AntiOverfitService
from .convergence import ConvergenceTracker
from .backtest_finalization import BacktestFinalizationService
from .backtest_polling import BacktestPollingService
from .backtest_slots import BacktestSlotManager
from .backtest_submission import BacktestSubmissionService
from .batch_backtest_coordinator import BatchBacktestCoordinator
from .candidate_pool import CandidatePoolService, is_active_backtest_candidate, pending_simulation_targets
from .dataset_selection import DatasetSelectionService
from .experience_feedback import ExperienceFeedbackService
from .fusion_candidates import FusionCandidateService
from .official_call_guard import OfficialCallGuard
from .official_validation import OfficialValidationService
from .official_workflow import OfficialWorkflowService
from .generation_phase import GenerationPhaseService
from .pipeline_snapshot import (
    PipelineSnapshotBuilder,
    PipelineSnapshotServices,
    PipelineSnapshotState,
    backtest_slot_snapshot,
)
from .pipeline_state import CycleState, record_strategy_reward
from .pipeline_helpers import (
    assistant_guidance_for_generator as _assistant_guidance_for_generator,
    blocked_gate as _blocked_gate,
    expr_key as _expr_key,
    rank_candidates,
)
from .pipeline_official_context import (
    OfficialContextLoadService,
    active_dataset_field_names,
    configured_official_context_files_exist,
    official_context_reasons,
    refresh_context_validation_cache,
)
from .pipeline_observability import (
    apply_observability_generation_guidance,
    refresh_observability_throttle,
)
from .pipeline_cloud import (
    build_cloud_similarity_rows,
    cloud_correlation_risk,
    cloud_status_for_candidate,
    remember_accepted,
    smart_rank_candidates,
    smart_ranking_score,
)
from .secondary_fusion import SecondaryFusionService
from .strategy_plugins import StrategyPluginRegistry
from .strategy_lifecycle import StrategyLifecycleTracker
from .strategy_switch import StrategySwitchService
from .auto_calibrator import AutoCalibrator
from .iterative_optimizer import IterativeOptimizer
from .production_context import build_production_context, eligible_strategy_profiles
from .research_cycle_orchestrator import ResearchCycleOrchestrator
from .rolling_validation import RollingValidationService
from .robustness_policy import RobustnessPolicy

from .pipeline_context_sync import PipelineContextSyncMixin
from .pipeline_services import PipelineServiceFactoryMixin
from .pipeline_strategy import PipelineStrategyMixin
from .pipeline_candidates import PipelineCandidatePoolMixin
from .pipeline_official_validation_flow import PipelineOfficialValidationMixin
from .pipeline_backtest_flow import PipelineBacktestMixin
from .pipeline_legacy_simulation import PipelineLegacySimulationMixin
from .pipeline_submission_gate import PipelineSubmissionMixin
from .pipeline_snapshots import PipelineSnapshotMixin
from .pipeline_runtime import PipelineRuntimeMixin

SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}


class AlphaResearchPipeline(
    PipelineRuntimeMixin,
    PipelineContextSyncMixin,
    PipelineServiceFactoryMixin,
    PipelineStrategyMixin,
    PipelineCandidatePoolMixin,
    PipelineOfficialValidationMixin,
    PipelineBacktestMixin,
    PipelineLegacySimulationMixin,
    PipelineSubmissionMixin,
    PipelineSnapshotMixin,
):
    """End-to-end alpha research, simulation, scoring, and optional submission.

    The main entry point is ``run()``, which orchestrates the full pipeline.
    Individual phases are extracted into private methods for testability.
    """

    class _Phase(enum.Enum):
        CONTINUE = "continue"
        SKIP = "skip"
        BREAK = "break"

    def __init__(
        self,
        *,
        config: OpsConfig,
        api: BrainAPI,
        repository: ResearchRepository | None = None,
        ledger: SubmissionLedger | None = None,
        progress_callback: Callable[[dict], None] | None = None,
        stop_callback: Callable[[], bool] | None = None,
    ):
        self.config = config
        self.api = api
        self._local_data_dir_existed_at_start = Path(config.storage_dir).exists()
        self.repository = repository or ResearchRepository(config.storage_dir)
        self.ledger = ledger or SubmissionLedger(config.storage_dir)
        self.generator = CandidateGenerator()
        self.events: list[PipelineEvent] = []
        self.progress_callback = progress_callback
        self.stop_callback = stop_callback
        self.official_calls_halted = False
        self.official_halt_reason = ""
        self.observability_throttle: dict = {}
        self.observability_generation_guidance: dict = {}
        self.official_call_guard = OfficialCallGuard()
        self.backtests_submitted = 0
        self.officially_simulated_count = 0
        self.official_validation_attempted_count = 0
        self.official_validation_passed_count = 0
        self.produced_count = 0
        self.context_summary: dict[str, object] = {}
        self.last_backtests: list[dict] = []
        self.last_runtime_data: dict = {}
        self._knowledge_base = StructuredKnowledgeBase(config.storage_dir)
        self._local_backtest_engine = LocalBacktestEngine()
        self._cross_review_service = CrossReviewService()
        self.backtest_slot_manager = BacktestSlotManager()
        self.backtest_slots: dict[int, Candidate] = self.backtest_slot_manager.slots
        self.official_resume_at = 0.0
        self.strategy_profile_index = self._initial_strategy_profile_index()
        self.strategy_switch_count = 0
        self.cycles_since_strategy_switch = 0
        self.official_results_since_strategy_switch = 0
        self.ready_since_strategy_switch = 0
        self.official_rejections_since_strategy_switch = 0
        self.run_id = ""
        # P3-1: Multi-armed bandit for adaptive strategy selection
        self._bandit_rewards: dict[int, list[float]] = {}  # profile_idx → [reward, ...]
        self._bandit_counts: dict[int, int] = {}           # profile_idx → selections
        self.strategy_lifecycle = StrategyLifecycleTracker(record_sink=self._record_strategy_lifecycle)
        self.strategy_plugins = self._load_strategy_plugins()
        self.cloud_alphas: list[dict] = []
        self.cloud_sync: dict = {"status": "not_started", "range": config.budget.cloud_sync_range, "count": 0, "warning": ""}
        self.lifecycle_records: list[dict] = []
        self.backtest_records: list[dict] = []
        self.recovered_backtest_slot_count = 0
        # Optional advanced components — wired in _load_official_context when available
        self._loader = None
        self._mapper = None
        self._theme_engine = None
        self._selector = None
        self._active_dataset_id: str = ""
        self._context_field_names: set[str] = set()
        self._context_operator_names: set[str] = set()
        self._dataset_field_names_cache: dict[str, set[str]] = {}
        self._cloud_similarity_rows: list[dict[str, object]] = []
        self._cloud_risk_cache: dict[tuple[str, str, int], dict] = {}
        # ── P1-2: AlphaCheckRegistry for BRAIN-standard quality checks ──
        self.check_registry = AlphaCheckRegistry()
        self.check_registry.build_default_checks()
        # P1-5: Register type-specific checks (POWER_POOL / ATOM / PYRAMID)
        alpha_type = str(getattr(config.settings, 'type', 'REGULAR') or 'REGULAR').upper()
        if alpha_type != "REGULAR":
            self.check_registry.build_type_checks(alpha_type)
            self._event("type_checks_registered",
                f"Alpha type '{alpha_type}': registered type-specific checks.",
                level="INFO")
        # ── P2-5: Context refresh tracking ──
        self._last_context_refresh: float = 0.0
        # ── P2-2: Convergence tracker ──
        self.convergence = ConvergenceTracker(window_size=10, stall_threshold=5)
        # ── P0-1: Auto-calibrator for scoring parameters ──
        self.auto_calibrator = AutoCalibrator(storage_dir=getattr(config, 'storage_dir', 'data'))
        # ── P0-2: Iterative optimizer (lazy-init with loader/mapper after context load) ──
        self.optimizer: IterativeOptimizer | None = None

    def run(self, *, auto_submit: bool = False) -> PipelineResult:
        run_id = new_id("run")
        self.run_id = run_id
        submitted_this_run = 0
        state = CycleState()
        # Local aliases for backward-compat with existing code
        archive_stats = state.archive_stats
        archive_samples = state.archive_samples
        accepted_candidates = state.accepted_candidates
        pool_by_expression = state.pool_by_expression
        blocked_expressions = state.blocked_expressions

        self._event("run_started", "Research pipeline started.")
        self._progress("startup", 0, 1, "准备认证并加载官方字段/算子上下文。")
        self.api.authenticate()
        self._recover_persisted_backtest_slots()

        # P1-8: Fetch user profile (tier, level, points) after authentication
        self.user_profile: dict = {}
        try:
            self.user_profile = self.api.get_user_profile()
            self._event("user_profile_loaded",
                f"User: {self.user_profile.get('tier', 'unknown')}, "
                f"Level: {self.user_profile.get('level', 'N/A')}, "
                f"Points: {self.user_profile.get('points', 'N/A')}",
                level="INFO")
        except Exception as exc:
            message = redact_error_message(exc, max_length=100)
            self.user_profile = {"tier": "error", "error": message}
            self._event("user_profile_failed",
                f"Could not fetch user profile: {message}", level="WARN")

        self._sync_cloud_alphas()
        fields, operators = self._load_official_context()

        # ── Build live-verified production context ──
        self.production_context: dict = build_production_context(
            user_profile=self.user_profile,
            official_fields=fields or [],
            config=self.config,
        )
        self._event("production_context_ready",
            f"Tier: {self.production_context.get('account_tier')}, "
            f"Profiles: {self.production_context.get('eligible_profiles_count')}, "
            f"Safe fields: {self.production_context.get('safe_field_count')} (excl. VECTOR)",
            level="INFO")
        self.strategy_lifecycle.propose(
            self._current_strategy_profile(),
            index=self.strategy_profile_index,
            cycle=0,
            reason="initial adaptive strategy profile",
        )
        self._notify_strategy_plugins(
            "propose",
            self._current_strategy_profile(),
            cycle=0,
            reason="initial adaptive strategy profile",
        )

        # Inject live-verified fields into the generator module
        try:
            from .validated_generator import set_active_safe_fields
            set_active_safe_fields(self.production_context["safe_fields"])
        except Exception:
            logger.warning("Failed to inject live safe-fields into generator", exc_info=True)

        if self.progress_callback and self.user_profile:
            self._progress("startup", 0.5, 1,
                f"用户: {self.user_profile.get('tier', '-')} "
                f"Lv.{self.user_profile.get('level', '-')} "
                f"积分 {self.user_profile.get('points', '-')}",
                data={"user_profile": self.user_profile})

        cycle_orchestrator = ResearchCycleOrchestrator(
            run_forever=self.config.budget.run_forever,
            max_cycles=self.config.budget.max_cycles,
            should_stop=self._should_stop,
        )
        while True:
            cycle_decision = cycle_orchestrator.next_cycle()
            if not cycle_decision.should_run:
                break
            cycle = cycle_decision.cycle
            self.cycles_since_strategy_switch += 1

            # ── Phase 1: Dataset selection (P1 refactor) ──
            ds_phase = self._cycle_select_dataset(cycle)
            if ds_phase is self._Phase.SKIP:
                continue
            if ds_phase is self._Phase.BREAK:
                break

            # ── P2-2: Experience feedback — every 5 cycles ──
            self._experience_feedback_service().apply(cycle)

            assistant_guidance = self._apply_assistant_guidance(cycle)
            assistant_guidance_applied = bool(assistant_guidance)
            self._refresh_observability_throttle(cycle)

            # ── P2-5: Periodic context refresh (every ~24h / 50 cycles) ──
            import time as _time
            if self._loader and (cycle == 1 or (cycle % 50 == 0) or
                                (_time.time() - self._last_context_refresh > 86400)):
                try:
                    refresh_result = self._loader.refresh()
                    self._last_context_refresh = _time.time()
                    if refresh_result.get("status") == "refreshed":
                        f_delta = refresh_result.get("fields_delta", 0)
                        o_delta = refresh_result.get("operators_delta", 0)
                        if f_delta or o_delta:
                            self._event("context_refreshed",
                                f"Cycle {cycle}: Context refreshed — fields {f_delta:+d}, "
                                f"operators {o_delta:+d}")
                            # Update generator context with refreshed data
                            fields, operators = self._load_official_context()
                    elif refresh_result.get("status") == "refresh_failed":
                        # P1-4: Alert on context refresh failure
                        error_detail = refresh_result.get("error", "unknown")
                        self._event("context_refresh_failed",
                            f"Cycle {cycle}: Context refresh FAILED — {error_detail}",
                            level="ERROR")
                except Exception as exc:
                    self._event("context_refresh_error",
                        f"Cycle {cycle}: Context refresh exception — {exc}",
                        level="ERROR")
            generated = self._generation_phase_service().generate(
                assistant_guidance=assistant_guidance if assistant_guidance_applied else None,
            )
            self.produced_count += len(generated)
            for candidate in generated:
                self._record_lifecycle(candidate, "generated", "本地生成")
            self._event("candidates_generated", f"Cycle {cycle}: generated {len(generated)} candidates.")
            self._progress(
                "production_loop",
                0 if self.config.budget.run_forever else cycle - 1,
                1 if self.config.budget.run_forever else self.config.budget.max_cycles,
                f"第 {cycle} 轮：生产 {len(generated)} 个 Alpha，进入本地评分与排序。",
                data={"cycle": cycle, "produced_count": self.produced_count},
            )

            locally_passed = self._local_prefilter(generated, cycle, fields, operators)
            self._archive(
                archive_stats,
                archive_samples,
                [
                    candidate
                    for candidate in generated
                    if candidate.lifecycle_status == "local_prefilter_rejected"
                ],
            )

            self._archive(archive_stats, archive_samples, self._merge_into_pool(pool_by_expression, locally_passed, blocked_expressions))
            self._archive(archive_stats, archive_samples, self._remove_below_local_standard(pool_by_expression))
            self._archive(archive_stats, archive_samples, self._prune_pool(pool_by_expression))
            pool = rank_candidates(list(pool_by_expression.values()))
            self._progress(
                "candidate_pool",
                len(pool),
                self.config.budget.retained_alpha_pool_size,
                f"候选池已按本地分排序，保留 {len(pool)}/{self.config.budget.retained_alpha_pool_size} 个 Alpha。",
                data=self._runtime_data(cycle, pool, accepted_candidates, archive_stats),
            )

            if self.official_calls_halted:
                self._maybe_resume_official_calls()
            self._refresh_observability_throttle(cycle)
            if self.official_calls_halted:
                if not self._defer_official_cycle(cycle, pool, accepted_candidates, archive_stats):
                    break
                continue

            validation_targets = self._filter_observability_duplicate_targets(
                self._validation_targets(pool),
                phase="official_validation",
            )
            self._archive(
                archive_stats,
                archive_samples,
                self._archive_validation_failures(pool_by_expression, pool, blocked_expressions),
            )
            pool = rank_candidates(list(pool_by_expression.values()))
            validation_quota = self._validation_quota(pool)
            self._validate(validation_targets[:validation_quota])
            self._archive(
                archive_stats,
                archive_samples,
                self._archive_validation_failures(pool_by_expression, validation_targets, blocked_expressions),
            )

            pool = rank_candidates(list(pool_by_expression.values()))
            self._top_up_candidate_pool(
                cycle,
                pool_by_expression,
                blocked_expressions,
                archive_stats,
                archive_samples,
                fields,
                operators,
                accepted_candidates,
            )
            pool = rank_candidates(list(pool_by_expression.values()))
            # ── Phase 3: Simulation + Backtest + Strategy (P1 refactor) ──
            if self.official_calls_halted:
                self._maybe_resume_official_calls()
            if self.official_calls_halted:
                if not self._defer_official_cycle(cycle, pool, accepted_candidates, archive_stats):
                    break
                continue
            submitted_this_run = self._cycle_simulate_and_submit(
                cycle, pool_by_expression, blocked_expressions,
                archive_stats, archive_samples, accepted_candidates,
                submitted_this_run, auto_submit,
            )
            # Top-up pool after simulation
            self._top_up_candidate_pool(
                cycle,
                pool_by_expression,
                blocked_expressions,
                archive_stats,
                archive_samples,
                fields,
                operators,
                accepted_candidates,
            )
            fields, operators = self._maybe_switch_strategy(
                cycle,
                fields,
                operators,
                pool_by_expression,
                accepted_candidates,
                archive_stats,
            )

            self._event(
                "cycle_completed",
                f"Cycle {cycle} completed with {len(pool_by_expression)} retained candidates.",
                data={"cycle": cycle, "pool_size": len(pool_by_expression)},
            )

            # ── P2-2: Record convergence metrics ──
            pool_values = list(pool_by_expression.values())
            self.convergence.record_cycle(
                cycle=cycle,
                produced=len(generated),
                passed_local=len(locally_passed),
                simulated=self.officially_simulated_count,
                passed_gate=sum(1 for c in pool_values if c.gate.get("submission_ready")),
                submitted=submitted_this_run,
                candidates=pool_values,
                fusion_created=sum(1 for c in pool_values if c.mutation_type == "secondary_fusion"),
            )

            # ── P3-1: Record bandit reward for current strategy profile ──
            idx = self.strategy_profile_index
            reward_snapshot = record_strategy_reward(idx, pool_values, self._bandit_rewards, self._bandit_counts)
            self.strategy_lifecycle.record_reward(
                self._current_strategy_profile(),
                index=idx,
                cycle=cycle,
                reward=reward_snapshot.reward,
                metrics=reward_snapshot.metrics,
            )

            # ── P2-2: Output convergence report every 10 cycles ──
            if cycle > 0 and cycle % 10 == 0:
                conv = self.convergence.summary()
                self._event(
                    "convergence_report",
                    f"Cycle {cycle} convergence: {conv['sharpe_trend']}, "
                    f"avg Sharpe={conv['recent_avg_sharpe']:.3f}, "
                    f"stalled={conv['stalled']}",
                    data={"convergence": conv},
                )
                if conv["stalled"]:
                    self._event(
                        "convergence_stalled",
                        conv["recommendation"],
                        level="WARN",
                    )

            # ── P0-1: Auto-calibrate scoring params when enough samples accumulated ──
            if cycle > 0 and self.auto_calibrator.needs_calibration():
                try:
                    calib_report = self.auto_calibrator.calibrate()
                    if calib_report.get("calibrated"):
                        self.config.scoring = self.auto_calibrator.apply(self.config.scoring)
                        self._event(
                            "scoring_calibrated",
                            calib_report.get("summary", "Scoring parameters calibrated."),
                            data=calib_report,
                        )
                except Exception as exc:
                    self._event(
                        "scoring_calibration_failed",
                        f"Auto-calibration failed: {exc}",
                        level="WARN",
                    )

            # ── P0-3: Fusion trigger when convergence stalls ──
            if (
                cycle > 0
                and self.config.budget.enable_secondary_fusion
                and self.convergence.summary().get("stalled")
                and self.convergence.summary().get("stall_cycles", 0) >= 3
            ):
                conv = self.convergence.summary()
                try:
                    self._try_fusion_top_candidates(pool_by_expression, blocked_expressions, cycle)
                except Exception as exc:
                    self._event(
                        "fusion_attempt_failed",
                        f"Fusion attempt during convergence stall failed: {exc}",
                        level="WARN",
                    )

            self._progress(
                "production_loop",
                0 if self.config.budget.run_forever else cycle,
                1 if self.config.budget.run_forever else self.config.budget.max_cycles,
                f"第 {cycle} 轮完成，继续生产、评价和排序。",
                data=self._runtime_data(
                    cycle,
                    rank_candidates(list(pool_by_expression.values())),
                    accepted_candidates,
                    archive_stats,
                ),
            )
            if self.config.budget.run_forever and not self._sleep_with_stop(self.config.budget.cycle_pause_seconds):
                break

        final_candidates = rank_candidates(accepted_candidates + list(pool_by_expression.values()))
        summary = self._summary(final_candidates, submitted_this_run, pool_by_expression, archive_stats)
        self._event("run_completed", "Research pipeline completed.", data=summary)
        run_status = "stopped" if self._should_stop() else "completed"
        if run_status == "stopped":
            self._progress("stopped", 0, 1, "用户已停止连续生产队列。", data=summary)
        else:
            self._progress("completed", 1, 1, "生产、评价、排序和回测等待流程完成。", data=summary)
        for candidate in final_candidates:
            self.repository.save_candidate(run_id, candidate)
            self.repository.save_family_record(candidate)
        for event in self.events:
            self.repository.save_event(run_id, event)
        result = PipelineResult(run_id=run_id, candidates=final_candidates, events=self.events, summary=summary)
        try:
            self.repository.save_run_history(
                run_id,
                result.to_dict(),
                status=run_status,
                parameter_audit=build_parameter_audit_snapshot(
                    self.config,
                    auto_submit=auto_submit,
                    source="pipeline_run",
                ),
            )
        except Exception:
            logger.warning("failed to persist run history for %s", run_id, exc_info=True)

        # Auto-calibration check (non-blocking)
        try:
            from calibrate_weights import auto_calibrate_if_stalled
            calib = auto_calibrate_if_stalled(self.ops_config.storage_dir)
            if calib.get("triggered") and calib.get("advice"):
                logger.info("auto_calibration triggered: %s", calib.get("reason"))
                self.events.append(PipelineEvent(
                    event="auto_calibration",
                    data={"triggered": True, "reason": calib.get("reason"), "advice": calib.get("advice")},
                ))
        except Exception:
            logger.debug("auto_calibration skipped", exc_info=True)

        return result

    # ═══════════════════════════════════════════════════════════════════
    # P1 refactor: extracted phase methods from run()
    # ═══════════════════════════════════════════════════════════════════

    def _cycle_select_dataset(self, cycle: int) -> "_Phase":
        """Select dataset for this cycle. Returns _Phase.SKIP or _Phase.BREAK on failure."""
        result = self._dataset_selection_service().select()
        if result.dataset_id:
            self._active_dataset_id = result.dataset_id
        if result.should_continue:
            return self._Phase.CONTINUE
        if result.should_skip:
            return self._Phase.SKIP
        return self._Phase.BREAK

    def _apply_assistant_guidance(self, cycle: int) -> dict | None:
        if not getattr(self.config.budget, "use_assistant_guidance", True):
            return None
        try:
            min_confidence = float(getattr(self.config.budget, "assistant_guidance_min_confidence", 0.6) or 0.0)
            guidance = ResearchMemory(self.config.storage_dir).latest_assistant_guidance(
                min_confidence=min_confidence,
            )
            if not guidance.get("usable"):
                return None
            guidance = ensure_assistant_guidance_digest(guidance)
            generator_guidance = _assistant_guidance_for_generator(guidance)
            if not generator_guidance:
                return None
            self.generator.set_experience_guidance(generator_guidance)
            self._event(
            "assistant_guidance_applied",
            f"Cycle {cycle}: Applied persisted assistant guidance "
            f"(confidence={guidance.get('confidence', 0.0)}; "
            f"operators={generator_guidance.get('top_operators', [])[:5]}; "
            f"windows={generator_guidance.get('preferred_windows', [])[:5]}).",
                level="INFO",
                data={
                    "guidance_source": guidance.get("source", ""),
                    "guidance_digest": guidance.get("guidance_digest", ""),
                    "persisted_at": guidance.get("persisted_at", ""),
                    "confidence": guidance.get("confidence", 0.0),
                    "historical_outcome_status": guidance.get("historical_outcome_status", "unknown"),
                    "historical_outcome": guidance.get("historical_outcome", {}),
                    "top_fields": guidance.get("top_fields", [])[:10],
                    "top_operators": guidance.get("top_operators", [])[:10],
                    "preferred_windows": guidance.get("preferred_windows", [])[:10],
                },
            )
            return guidance
        except Exception:
            logger.warning("Assistant guidance unavailable in cycle %s", cycle, exc_info=True)
        return None

    def _cycle_simulate_and_submit(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        accepted_candidates: list[Candidate],
        submitted_this_run: int,
        auto_submit: bool,
    ) -> int:
        """Execute the simulation+backtest+strategy phase for one cycle.

        Returns updated submitted_this_run count.
        """
        # Poll existing backtests
        submitted_this_run = self._poll_due_backtests(
            cycle, pool_by_expression, accepted_candidates,
            archive_stats, archive_samples, blocked_expressions,
            submitted_this_run, auto_submit,
        )

        # Validate candidates for open backtest slots
        official_workflow = self._official_workflow_service()
        official_workflow.validate_slots(
            cycle, pool_by_expression, accepted_candidates,
            archive_stats, blocked_expressions,
        )

        # Fill backtest slots
        cyc_state = CycleState(
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
        )
        official_workflow.fill_slots(cycle, cyc_state)
        submitted_this_run = official_workflow.poll_due(
            cycle, pool_by_expression, accepted_candidates,
            archive_stats, archive_samples, blocked_expressions,
            submitted_this_run, auto_submit, force_initial=True,
        )

        if not self.official_calls_halted:
            official_workflow.fill_slots(cycle, cyc_state)

        self._archive(archive_stats, archive_samples, self._prune_pool(pool_by_expression))
        return submitted_this_run

    # ═══════════════════════════════════════════════════════════════════
    # Helper methods (original)
    # ═══════════════════════════════════════════════════════════════════


    # Backtest result checks ──


