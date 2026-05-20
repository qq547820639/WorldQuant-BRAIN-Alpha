"""End-to-end alpha research, simulation, scoring, and optional submission."""

from __future__ import annotations

import dataclasses
import enum
import logging
from pathlib import Path
import time
from typing import Callable

logger = logging.getLogger(__name__)

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS
from brain_alpha_ops.config import OpsConfig, runtime_project_root
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult, new_id
from brain_alpha_ops.observability import context_payload, error_payload
from brain_alpha_ops.redaction import redact_error_message

from .generator import CandidateGenerator, extract_fields, extract_operators, local_quality, mutate_expression
from .guidance import assistant_guidance_candidate_metadata, ensure_assistant_guidance_digest
from .expression_ast import expression_key, expression_similarity
from .memory import ResearchMemory
from .observability import (
    actionable_duplicate_expression_buckets,
    build_research_observability_snapshot,
    observability_context,
)
from .repository import ResearchRepository
from .safety import SubmissionLedger, mock_source_reasons, normalize
from .scoring import build_scorecard, evaluate_quality_gate
from .alpha_checks import AlphaCheckRegistry
from .anti_overfit import AntiOverfitService
from .convergence import ConvergenceTracker
from .backtest_finalization import BacktestFinalizationService
from .backtest_polling import BacktestPollingService
from .backtest_slots import BacktestSlotManager
from .backtest_submission import BacktestSubmissionService
from .batch_backtest_coordinator import BatchBacktestCoordinator
from .candidate_pool import CandidatePoolService
from .dataset_selection import DatasetSelectionService
from .experience_feedback import ExperienceFeedbackService
from .fusion_candidates import FusionCandidateService
from .official_call_guard import OfficialCallGuard
from .official_validation import OfficialValidationService
from .official_workflow import OfficialWorkflowService
from .generation_phase import GenerationPhaseService
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

# Lazy imports for optional components (wired in _load_official_context)
_DS_SELECTOR_IMPORTED = False
_THEME_ENGINE_IMPORTED = False
_MAPPER_IMPORTED = False


SUBMITTED_CLOUD_STATUSES = {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}


@dataclasses.dataclass
class _CycleState:
    """P3 refactor: mutable state shared across pipeline helper methods.

    Encapsulates the 5 mutable containers that were historically passed as
    individual parameters to _fill_backtest_slots, _poll_due_backtests,
    _top_up_candidate_pool, _validate_for_open_backtest_slots, etc.
    """
    pool_by_expression: dict[str, Candidate] = dataclasses.field(default_factory=dict)
    accepted_candidates: list[Candidate] = dataclasses.field(default_factory=list)
    archive_stats: dict[str, int] = dataclasses.field(default_factory=dict)
    archive_samples: list[Candidate] = dataclasses.field(default_factory=list)
    blocked_expressions: set[str] = dataclasses.field(default_factory=set)


class AlphaResearchPipeline:
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
        state = _CycleState()  # P3 refactor: shared mutable state
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
            sharpe_vals = [c.official_metrics.get("sharpe", 0) for c in pool_values if c.official_metrics]
            avg_sharpe = sum(sharpe_vals) / max(len(sharpe_vals), 1)
            pass_rate = sum(1 for c in pool_values if c.gate.get("submission_ready")) / max(len(pool_values), 1)
            reward = avg_sharpe * (0.5 + 0.5 * pass_rate)
            self._bandit_rewards.setdefault(idx, []).append(reward)
            self._bandit_counts[idx] = self._bandit_counts.get(idx, 0) + 1
            self.strategy_lifecycle.record_reward(
                self._current_strategy_profile(),
                index=idx,
                cycle=cycle,
                reward=reward,
                metrics={
                    "avg_sharpe": round(avg_sharpe, 6),
                    "pass_rate": round(pass_rate, 6),
                    "pool_size": len(pool_values),
                },
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
            self.repository.save_run_history(run_id, result.to_dict(), status=run_status)
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
        cyc_state = _CycleState(
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

    def _sync_cloud_alphas(self):
        sync_range = self.config.budget.cloud_sync_range
        cached_rows = self.repository.latest_cloud_alphas()
        if self._local_data_dir_existed_at_start and cached_rows:
            if cached_rows:
                self.cloud_alphas = cached_rows
                self._refresh_cloud_similarity_index()
                self.cloud_sync = {
                    "status": "loaded",
                    "status_code": "CACHE_LOADED",
                    "range": sync_range,
                    "count": len(cached_rows),
                    "scanned": len(cached_rows),
                    "total": len(cached_rows),
                    "added": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "cached": True,
                    "stale": False,
                    "warning": "",
                    "run_status": "skipped",
                }
                self._event("cloud_sync_skipped_cache_loaded", f"Loaded {len(cached_rows)} cached cloud alphas from local data; per-run sync is manual.")
            else:
                self.cloud_alphas = []
                self._refresh_cloud_similarity_index()
                self.cloud_sync = {
                    "status": "skipped",
                    "status_code": "CACHE_EMPTY_MANUAL_SYNC",
                    "range": sync_range,
                    "count": 0,
                    "scanned": 0,
                    "total": 0,
                    "added": 0,
                    "updated": 0,
                    "skipped": 0,
                    "failed": 0,
                    "cached": False,
                    "stale": False,
                    "warning": "Local data directory exists; cloud sync is manual for this run.",
                    "run_status": "skipped",
                }
                self._event("cloud_sync_skipped_manual", "Local data directory exists; skipped automatic cloud alpha sync.")
            self._progress(
                "cloud_sync",
                1,
                1,
                f"已加载本地云端缓存：{len(cached_rows)} 条；本轮未自动同步。",
                data={"cloud_sync": self.cloud_sync, "cloud_alphas": self.cloud_alphas},
            )
            return

        if not self.config.budget.require_cloud_sync:
            self._event("cloud_sync_initial_required", "No local cloud alpha cache found; running first-login sync.")
        self._progress(
            "cloud_sync",
            0,
            1,
            f"同步云端 Alpha：{sync_range}",
            data={"cloud_sync": {"status": "running", "status_code": "RUNNING", "range": sync_range, "scanned": 0, "added": 0, "skipped": 0, "failed": 0}},
        )
        sync_meta = {"cached": False, "stale": False, "warning": ""}

        def on_cloud_progress(progress: dict):
            sync_meta["cached"] = sync_meta["cached"] or bool(progress.get("cached"))
            sync_meta["stale"] = sync_meta["stale"] or bool(progress.get("stale"))
            sync_meta["warning"] = str(progress.get("warning") or sync_meta["warning"] or "")
            self._progress(
                "cloud_sync",
                int(progress.get("scanned", 0)) if int(progress.get("total", 0) or 0) else 0,
                max(1, int(progress.get("total", 0) or 1)),
                f"云端 Alpha 扫描中：{progress.get('scanned', 0)} / {progress.get('total') or '总量确认中'}。",
                data={
                    "cloud_sync": {
                        "status": "running",
                        "status_code": "RUNNING",
                        "range": sync_range,
                        "scanned": int(progress.get("scanned", 0)),
                        "total": int(progress.get("total", 0) or 0),
                        "page_size": int(progress.get("page_size", 0) or 0),
                        "offset": int(progress.get("offset", 0) or 0),
                        "added": 0,
                        "skipped": 0,
                        "failed": 0,
                        "cached": bool(progress.get("cached")),
                        "stale": bool(progress.get("stale")),
                        "warning": str(progress.get("warning") or ""),
                    }
                },
            )

        try:
            rows = self.api.list_user_alphas(sync_range, progress_callback=on_cloud_progress)
        except BrainAPIError as exc:
            self.cloud_alphas = []
            self._refresh_cloud_similarity_index()
            self.cloud_sync = {
                "status": "failed",
                "status_code": f"HTTP_{exc.status_code}" if exc.status_code else "FAILED",
                "range": sync_range,
                "count": 0,
                "scanned": 0,
                "added": 0,
                "skipped": 0,
                "failed": 1,
                "warning": redact_error_message(exc),
            }
            self._event("cloud_sync_failed", self.cloud_sync["warning"], level="WARN")
        else:
            self.cloud_alphas = rows
            self._refresh_cloud_similarity_index()
            merge_stats = self.repository.merge_cloud_alphas(rows, sync_range=sync_range)
            self.cloud_sync = {
                "status": "synced",
                "status_code": "SYNCED",
                "range": sync_range,
                "count": len(rows),
                "scanned": len(rows),
                "total": len(rows),
                "added": merge_stats["added"],
                "updated": merge_stats["updated"],
                "skipped": merge_stats["skipped"],
                "failed": 0,
                "cached": bool(sync_meta["cached"]),
                "stale": bool(sync_meta["stale"]),
                "warning": str(sync_meta["warning"]),
            }
            self._event("cloud_alphas_synced", f"Synced {len(rows)} cloud alphas for range {sync_range}.")
        self._progress(
            "cloud_sync",
            1,
            1,
            f"云端 Alpha 同步完成：{self.cloud_sync['count']} 条。",
            data={"cloud_sync": self.cloud_sync, "cloud_alphas": self.cloud_alphas},
        )

    def _load_official_context(self) -> tuple[list[dict], list[dict]]:
        fields: list[dict] = []
        operators: list[dict] = []
        context_warning = ""

        # ── P0: JSON-first loading from OfficialDataLoader ──
        try:
            from brain_alpha_ops.data import OfficialDataLoader
            loader = OfficialDataLoader.instance()
            loader.refresh(self.config.storage_dir, max_retries=1)
            fields = [
                {
                    "id": f.id,
                    "name": f.id,
                    "category": f.category,
                    "delay": f.delay,
                    "coverage": f.coverage,
                    "type": f.type,
                    "dataset": f.dataset.id if f.dataset else "",
                }
                for f in loader.get_fields()
            ]
            operators = [
                {"name": op.name, "category": op.category, "definition": op.definition, "description": op.description}
                for op in loader.get_operators()
            ]
            if not fields and not operators:
                if self._local_data_dir_existed_at_start:
                    context_warning = "Local data directory exists but official context files are empty; using built-in context until manual sync."
                    fields = list(DEFAULT_FIELDS)
                    operators = list(DEFAULT_OPERATORS)
                    self.generator.update_context(fields, operators)
                    self._refresh_context_validation_cache(fields, operators)
                    self.context_summary = {
                        "fields_count": len(fields),
                        "operators_count": len(operators),
                        "source": "builtin_context_manual_sync_required",
                        "warning": context_warning,
                    }
                    self._event("context_manual_sync_required", context_warning, level="WARN")
                    return fields, operators
                raise RuntimeError("official context JSON files are missing or empty")
            self._event("context_loaded_from_json", f"Loaded {len(fields)} fields, {len(operators)} operators from official_*.json")
            self.generator.update_context(fields, operators)
            self.context_summary = {
                "fields_count": len(fields), "operators_count": len(operators),
                "source": "official_json_files", "warning": "",
            }

            # ── Wire advanced components (DatasetSelector, FieldDatasetMapper, DynamicThemeEngine) ──
            try:
                from brain_alpha_ops.data import FieldDatasetMapper
                from brain_alpha_ops.research.theme_engine import DynamicThemeEngine
                from brain_alpha_ops.research.dataset_selector import DatasetSelector

                self._mapper = FieldDatasetMapper()
                self._mapper.build(loader)
                self._theme_engine = DynamicThemeEngine(loader)
                self._theme_engine.build_categories()
                self._selector = DatasetSelector()
                self._selector.initialize(loader)

                # ── P0-3 guard: verify datasets are available ──
                if not self._selector.available_datasets:
                    self._event("dataset_unavailable",
                        "DatasetSelector initialized but no datasets available. "
                        "Check data/official_datasets.json or BRAIN API connectivity.",
                        level="WARN")

                # ── Initialize HypothesisLibrary ──
                hypothesis_dir = getattr(
                    self.config.budget, 'hypothesis_library_dir',
                    'brain_alpha_ops/research/hypotheses',
                )
                from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
                self._hypothesis_library = HypothesisLibrary(hypothesis_dir).load_all()

                # ── Rebuild generator with hypothesis-driven capabilities ──
                from brain_alpha_ops.research.hypothesis_driven_generator import (
                    HypothesisDrivenGenerator,
                )
                ratio = getattr(self.config.budget, 'generation_mode_ratio', '70/20/10')
                self.generator = HypothesisDrivenGenerator(
                    loader=loader,
                    mapper=self._mapper,
                    theme_engine=self._theme_engine,
                    selector=self._selector,
                    library=self._hypothesis_library,
                    ratio_str=ratio,
                )
                self.generator.update_context(fields, operators)

                # Set initial dataset
                strategy = getattr(self.config.budget, 'dataset_strategy', 'rotate')
                ds_ids = self._selector.select(strategy)
                if ds_ids:
                    self._active_dataset_id = ds_ids[0]
                    self.generator.set_dataset(self._active_dataset_id)
                    if hasattr(self.config.settings, 'dataset'):
                        self.config.settings.dataset = self._active_dataset_id

                # ── P0-2: Wire IterativeOptimizer ──
                self.optimizer = IterativeOptimizer(loader=loader, mapper=self._mapper)

                self._event("advanced_components_wired",
                    f"DatasetSelector(strategy={strategy}), DynamicThemeEngine, FieldDatasetMapper ready. "
                    f"Active dataset: {self._active_dataset_id or '(none)'}")
            except Exception as exc:
                self._event("advanced_components_fallback",
                    f"Could not wire advanced components: {exc}. "
                    f"DatasetSelector/DynamicThemeEngine/FieldDatasetMapper unavailable "
                    f"— generator will use full field pool from OfficialDataLoader.",
                    level="ERROR")

            self._event("context_loaded", f"Loaded {len(fields)} fields and {len(operators)} operators.")
            self._refresh_context_validation_cache(fields, operators)
            return fields, operators
        except Exception as exc:
            context_warning = f"Official JSON load failed ({exc}), falling back to API..."

        # ── Fallback: API ──
        self._progress(
            "context",
            0,
            3,
            "加载官方字段列表。",
            data={"context_load": {"status": "running", "status_code": "CONTEXT_FIELDS", "current": 0, "total": 3, "fields_count": 0, "operators_count": 0}},
        )
        try:
            fields = self.api.list_fields(
                "all",
                self.config.settings.region,
                dataset=self.config.settings.dataset,
                progress_callback=lambda progress: self._progress(
                    "context",
                    1,
                    3,
                    f"加载官方字段列表：{progress.get('scanned', 0)} / {progress.get('total') or '总量确认中'}。",
                    data={
                        "context_load": {
                            "status": "running",
                            "status_code": "CONTEXT_FIELDS",
                            "current": 1,
                            "total": 3,
                            "fields_count": int(progress.get("scanned", 0) or 0),
                            "fields_total": int(progress.get("total", 0) or 0),
                            "operators_count": 0,
                            "cached": bool(progress.get("cached")),
                        }
                    },
                ),
            )
            self._progress(
                "context",
                2,
                3,
                "加载官方算子列表。",
                data={"context_load": {"status": "running", "status_code": "CONTEXT_OPERATORS", "current": 2, "total": 3, "fields_count": len(fields), "operators_count": 0}},
            )
            operators = self.api.list_operators(
                "all",
                progress_callback=lambda progress: self._progress(
                    "context",
                    2,
                    3,
                    f"加载官方算子列表：{progress.get('scanned', 0)} / {progress.get('total') or '总量确认中'}。",
                    data={
                        "context_load": {
                            "status": "running",
                            "status_code": "CONTEXT_OPERATORS",
                            "current": 2,
                            "total": 3,
                            "fields_count": len(fields),
                            "operators_count": int(progress.get("scanned", 0) or 0),
                            "operators_total": int(progress.get("total", 0) or 0),
                            "cached": bool(progress.get("cached")),
                        }
                    },
                ),
            )
        except BrainAPIError as exc:
            if exc.status_code == 429:
                context_warning = "官方上下文接口触发限流，本轮先继续本地生产与排序，稍后再恢复官方调用。"
                self._halt_official_calls(f"{context_warning} {exc}")
                self._event("official_context_deferred", self.official_halt_reason, level="WARN")
                self._progress(
                    "official_deferred",
                    0,
                    1,
                    context_warning,
                    data={"retry_seconds": self.config.budget.official_retry_pause_seconds},
                )
            else:
                raise
        if not fields:
            fields = list(DEFAULT_FIELDS)
            context_warning = (context_warning + " " if context_warning else "") + "使用内置字段基础上下文，登录成功后会自动更新官方字段缓存。"
        if not operators:
            operators = list(DEFAULT_OPERATORS)
            context_warning = (context_warning + " " if context_warning else "") + "使用内置算子基础上下文，登录成功后会自动更新官方算子缓存。"
        fields = _merge_context_defaults(fields, DEFAULT_FIELDS)
        operators = _merge_context_defaults(operators, DEFAULT_OPERATORS)
        self.generator.update_context(fields, operators)
        self._refresh_context_validation_cache(fields, operators)
        from brain_alpha_ops.research.generator import update_known_fields
        update_known_fields(fields)

        self.context_summary = {
            "fields_count": len(fields),
            "operators_count": len(operators),
            "source": "official_api_or_cache",
            "warning": context_warning,
            "operator_usage_note": "系统通过官方 /operators 接口校验可用算子；完整 Learn 页面说明不在本地硬编码，仍以官网当前文档为准。",
        }
        self._event("context_loaded", f"Loaded {len(fields)} fields and {len(operators)} operators.")
        self._progress(
            "context",
            3,
            3,
            f"上下文已加载：{len(fields)} 个字段，{len(operators)} 个算子。",
            data={
                "official_context": self.context_summary,
                "context_load": {
                    "status": "synced",
                    "status_code": "CONTEXT_READY",
                    "current": 3,
                    "total": 3,
                    "fields_count": len(fields),
                    "operators_count": len(operators),
                },
            },
        )
        return fields, operators

    def _record_lifecycle(self, candidate: Candidate, stage: str, note: str = ""):
        row = {
            "timestamp": time.time(),
            "alpha_id": candidate.alpha_id,
            "official_alpha_id": candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
            "stage": stage,
            "status": candidate.lifecycle_status,
            "family": candidate.family,
            "hypothesis": candidate.hypothesis,
            "score": candidate.scorecard.get("total_score", 0.0),
            "scorecard": candidate.scorecard,
            "local_quality": candidate.local_quality,
            "validation": candidate.validation,
            "official_metrics": candidate.official_metrics,
            "gate": candidate.gate,
            "simulation_id": candidate.simulation_id,
            "expression": candidate.expression,
            "note": note,
        }
        event_key = (
            row.get("alpha_id", ""),
            row.get("official_alpha_id", ""),
            row.get("stage", ""),
            row.get("status", ""),
            row.get("simulation_id", ""),
            row.get("note", ""),
        )
        for existing in reversed(self.lifecycle_records[-50:]):
            existing_key = (
                existing.get("alpha_id", ""),
                existing.get("official_alpha_id", ""),
                existing.get("stage", ""),
                existing.get("status", ""),
                existing.get("simulation_id", ""),
                existing.get("note", ""),
            )
            if existing_key == event_key:
                return
        self.lifecycle_records.append(row)
        if self.run_id:
            self.repository.save_lifecycle_record(self.run_id, row)

    def _record_backtest(
        self,
        candidate: Candidate,
        action: str,
        *,
        slot: int = 0,
        status: str = "",
        note: str = "",
        error_context: dict | None = None,
    ) -> None:
        row = {
            "action": action,
            "slot": slot or candidate.submission.get("backtest_slot", 0),
            "alpha_id": candidate.alpha_id,
            "official_alpha_id": candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
            "simulation_id": candidate.simulation_id,
            "status": status or candidate.submission.get("simulation_status") or candidate.lifecycle_status,
            "lifecycle_status": candidate.lifecycle_status,
            "family": candidate.family,
            "hypothesis": candidate.hypothesis,
            "score": candidate.scorecard.get("total_score", 0.0),
            "poll_count": int(candidate.submission.get("poll_count", 0) or 0),
            "expression": candidate.expression,
            "official_metrics": candidate.official_metrics,
            "gate": candidate.gate,
            "note": note,
        }
        if error_context:
            row["error_context"] = dict(error_context)
            row["retryable"] = bool(error_context.get("retryable"))
            if error_context.get("retry_after") is not None:
                row["retry_after"] = error_context.get("retry_after")
        self.backtest_records.append(row)
        self.backtest_records = self.backtest_records[-200:]
        if self.run_id:
            self.repository.save_backtest_record(self.run_id, row)

    def _record_strategy_lifecycle(self, row: dict) -> None:
        if self.run_id:
            self.repository.save_strategy_lifecycle_record(self.run_id, row)

    def _load_strategy_plugins(self) -> StrategyPluginRegistry:
        if not getattr(self.config.budget, "strategy_plugins_enabled", False):
            return StrategyPluginRegistry()
        registry = StrategyPluginRegistry.from_specs(list(self.config.budget.strategy_plugin_specs or []))
        if registry.plugins:
            self._event(
                "strategy_plugins_loaded",
                f"Loaded strategy plugins: {', '.join(registry.names())}",
                data={"strategy_plugins": registry.summary()},
                level="INFO",
            )
        if registry.load_errors:
            self._event(
                "strategy_plugins_load_error",
                f"Strategy plugin load errors: {len(registry.load_errors)}",
                data={"strategy_plugins": registry.summary()},
                level="WARN",
            )
        return registry

    def _strategy_plugin_summary(self) -> dict:
        summary = self.strategy_plugins.summary()
        summary.update(
            {
                "enabled": bool(getattr(self.config.budget, "strategy_plugins_enabled", False)),
                "configured_specs": list(getattr(self.config.budget, "strategy_plugin_specs", []) or []),
            }
        )
        return summary

    def _notify_strategy_plugins(
        self,
        action: str,
        profile: dict,
        *,
        cycle: int,
        reason: str = "",
        **context: object,
    ) -> list[dict]:
        if not self.strategy_plugins.plugins:
            return []
        payload = {
            "cycle": int(cycle or 0),
            "reason": str(reason or ""),
            "active_profile": self._current_strategy_profile(),
            "active_profile_index": self.strategy_profile_index,
            "strategy_switch_count": self.strategy_switch_count,
            "official_results_since_strategy_switch": self.official_results_since_strategy_switch,
            "ready_since_strategy_switch": self.ready_since_strategy_switch,
            "official_rejections_since_strategy_switch": self.official_rejections_since_strategy_switch,
            "settings": self.config.settings.to_platform_dict()["settings"],
            **context,
        }
        rows = self.strategy_plugins.notify(action, profile=dict(profile or {}), context=payload)
        for row in rows:
            if row.get("status") == "error":
                self._event(
                    "strategy_plugin_error",
                    f"{row.get('plugin')} {action} failed: {row.get('error')}",
                    data={"strategy_plugin": row},
                    level="WARN",
                )
        return rows

    def _recover_persisted_backtest_slots(self) -> None:
        if self._using_mock_api() or not getattr(self.config.budget, "resume_persisted_backtests", True):
            return
        try:
            rows = self.repository.latest_backtest_records(limit=1000)
            recovered = self.backtest_slot_manager.recover_from_records(
                rows,
                max_slots=self._active_backtest_limit(),
            )
        except Exception as exc:
            message = redact_error_message(exc, max_length=160)
            self._event("backtest_recovery_failed", message, level="WARN")
            return
        self.recovered_backtest_slot_count = self.backtest_slot_manager.recovered_slot_count
        if self.recovered_backtest_slot_count:
            recovered_rows = [
                {
                    "slot": slot,
                    "alpha_id": candidate.alpha_id,
                    "simulation_id": candidate.simulation_id,
                    "status": candidate.submission.get("simulation_status") or candidate.lifecycle_status,
                    "correlation_id": candidate.submission.get("recovered_correlation_id", ""),
                }
                for slot, candidate in sorted(recovered)
            ]
            self._event(
                "backtest_slots_recovered",
                f"Recovered {self.recovered_backtest_slot_count} persisted backtest slot(s) for polling.",
                data={"backtests": recovered_rows},
            )

    def _official_error_context(
        self,
        exc: BrainAPIError,
        error_code: str,
        *,
        phase: str,
        candidate: Candidate,
    ) -> dict:
        return error_payload(
            exc,
            error_code=error_code,
            max_length=240,
            phase=phase,
            alpha_id=candidate.alpha_id,
            simulation_id=candidate.simulation_id,
            official_alpha_id=candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
        )

    def _defer_official_cycle(
        self,
        cycle: int,
        pool: list[Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
    ) -> bool:
        self._progress(
            "official_deferred",
            0,
            1,
            f"官方调用已暂停：{self.official_halt_reason}",
            data=self._runtime_data(
                cycle,
                pool,
                accepted_candidates,
                archive_stats,
                {
                    "retry_seconds": self.config.budget.official_retry_pause_seconds,
                    "retry_remaining_seconds": self._official_retry_remaining_seconds(),
                },
            ),
        )
        remaining = self._official_retry_remaining_seconds()
        pause = min(max(0.1, float(self.config.budget.cycle_pause_seconds or 0.1)), self._poll_interval_seconds())
        if remaining:
            pause = min(pause, max(0.1, remaining))
        if not self._sleep_with_stop(pause):
            return False
        return not self._should_stop()

    def _refresh_observability_throttle(self, cycle: int) -> dict:
        try:
            snapshot = build_research_observability_snapshot(
                self.config.storage_dir,
                limit=5000,
                top_n=5,
                include_cloud=True,
            )
            context = observability_context(snapshot, top_n=5)
            self._apply_observability_generation_guidance(snapshot, context, cycle)
        except Exception as exc:
            message = redact_error_message(exc, max_length=180)
            self.observability_generation_guidance = {
                "schema_version": "observability_generation_guidance_summary.v1",
                "active": False,
                "cycle": cycle,
                "source": "research_observability",
                "status": "refresh_failed",
                "risk_level": "unknown",
                "health_flags": [],
                "duplicate_ratio": 0.0,
                "avoid_expression_count": 0,
                "top_duplicate_expressions": [],
                "top_duplicate_fingerprints": [],
                "applied_to_generator": False,
                "generator_type": type(self.generator).__name__,
                "error": message,
            }
            self.observability_throttle = {
                "ok": False,
                "status": "refresh_failed",
                "risk_level": "unknown",
                "health_flags": [],
                "blocking_flags": [],
                "warning_flags": [],
                "recommended_actions": [],
                "error": message,
                "generation_guidance": dict(self.observability_generation_guidance),
                "official_call_guard": self._observability_official_call_guard_snapshot(),
            }
            logger.warning("observability refresh failed in cycle %s: %s", cycle, message, exc_info=True)
            self._event(
                "observability_refresh_failed",
                f"Cycle {cycle}: observability refresh failed; local generation continues.",
                data=error_payload(
                    exc,
                    error_code="OBSERVABILITY_REFRESH_FAILED",
                    max_length=180,
                    phase="observability",
                    cycle=cycle,
                ),
                level="WARN",
            )
            return self.observability_throttle

        self.observability_throttle = {
            "ok": True,
            "status": "ready",
            "risk_level": context.get("risk_level", "unknown"),
            "health_flags": list(context.get("health_flags") or []),
            "blocking_flags": list(context.get("blocking_flags") or []),
            "warning_flags": list(context.get("warning_flags") or []),
            "recommended_actions": list(context.get("recommended_actions") or context.get("recommendations") or []),
            "backtest_failure_rate": context.get("backtest_failure_rate", 0.0),
            "retryable_error_count": context.get("retryable_error_count", 0),
            "generated_at": context.get("generated_at", ""),
            "generation_guidance": dict(self.observability_generation_guidance),
            "official_call_guard": self._observability_official_call_guard_snapshot(),
        }
        blocking_flags = list(self.observability_throttle.get("blocking_flags") or [])
        if blocking_flags:
            reason = "observability blocking flags: " + ", ".join(blocking_flags[:5])
            self._halt_official_calls(reason, self.config.budget.official_retry_pause_seconds)
            self._event(
                "official_calls_halted_by_observability",
                reason,
                data={"cycle": cycle, "observability": dict(self.observability_throttle)},
                level="WARN",
            )
        return self.observability_throttle

    def _apply_observability_generation_guidance(self, snapshot: dict, context: dict, cycle: int) -> None:
        expression_index = snapshot.get("expression_index") if isinstance(snapshot.get("expression_index"), dict) else {}
        top_duplicates = actionable_duplicate_expression_buckets(expression_index.get("top_duplicates") or [])[:10]
        health_flags = list(context.get("health_flags") or [])
        duplicate_ratio = float(context.get("duplicate_ratio") or 0.0)
        active = bool(top_duplicates or "high_duplicate_expression_ratio" in health_flags)
        guidance = {
            "schema_version": "observability_generation_guidance.v1",
            "source": "research_observability",
            "risk_level": context.get("risk_level", "unknown"),
            "health_flags": health_flags,
            "duplicate_ratio": duplicate_ratio,
            "avoid_expressions": top_duplicates,
        }
        setter = getattr(self.generator, "set_observability_guidance", None)
        applied_to_generator = False
        guidance_status = "idle" if not active else "no_generator_hook"
        guidance_error = ""
        if callable(setter):
            try:
                setter(guidance)
                applied_to_generator = True
                guidance_status = "applied" if active else "idle"
            except Exception as exc:
                guidance_error = redact_error_message(exc, max_length=180)
                guidance_status = "apply_failed"
                logger.warning(
                    "observability generation guidance failed in cycle %s for %s: %s",
                    cycle,
                    type(self.generator).__name__,
                    guidance_error,
                    exc_info=True,
                )
                self._event(
                    "observability_generation_guidance_failed",
                    f"Cycle {cycle}: observability generation guidance could not be applied; generation continues.",
                    data=error_payload(
                        exc,
                        error_code="OBSERVABILITY_GENERATION_GUIDANCE_FAILED",
                        max_length=180,
                        phase="observability_generation",
                        cycle=cycle,
                        generator_type=type(self.generator).__name__,
                    ),
                    level="WARN",
                )
        compact_guidance = {
            "schema_version": "observability_generation_guidance_summary.v1",
            "active": active,
            "cycle": cycle,
            "source": "research_observability",
            "status": guidance_status,
            "risk_level": context.get("risk_level", "unknown"),
            "health_flags": health_flags[:5],
            "duplicate_ratio": duplicate_ratio,
            "avoid_expression_count": len(top_duplicates),
            "top_duplicate_expressions": [
                str(row.get("expression_canonical") or row.get("expression") or "")[:160]
                for row in top_duplicates[:5]
                if isinstance(row, dict)
            ],
            "top_duplicate_fingerprints": [
                str(row.get("expression_fingerprint") or "")[:16]
                for row in top_duplicates[:5]
                if isinstance(row, dict) and row.get("expression_fingerprint")
            ],
            "applied_to_generator": applied_to_generator,
            "generator_type": type(self.generator).__name__,
        }
        if guidance_error:
            compact_guidance["error"] = guidance_error
        self.observability_generation_guidance = compact_guidance
        if active and applied_to_generator:
            self._event(
                "observability_generation_guidance_applied",
                f"Cycle {cycle}: observability diversified generation "
                f"(duplicates={len(top_duplicates)}, duplicate_ratio={duplicate_ratio}).",
                data={
                    "cycle": cycle,
                    "observability_generation_guidance": guidance,
                    "observability_generation_guidance_summary": compact_guidance,
                },
                level="INFO",
            )

    def _runtime_data(
        self,
        cycle: int,
        pool: list[Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        extra: dict | None = None,
    ) -> dict:
        candidate_pool = self._candidate_pool_candidates(pool)
        pending_backtests = self._pending_backtest_candidates(pool)
        validation_attempted = self.official_validation_attempted_count
        validation_passed = self.official_validation_passed_count
        pending_validation = len(self._validation_targets(pool))
        active_backtest_limit = self._active_backtest_limit()
        data = {
            "cycle": cycle,
            "candidates": self._candidate_snapshot(candidate_pool),
            "candidate_pool_available_count": len(candidate_pool),
            "candidate_pool_source_count": len(pool),
            "candidate_pool_excludes_waiting_backtests": True,
            "pending_backtest_candidates": self._candidate_snapshot(pending_backtests, limit=50, retained=False),
            "pending_backtest_count": len(pending_backtests),
            "passed_candidates": self._candidate_snapshot(accepted_candidates, limit=50, retained=False),
            "produced_count": self.produced_count,
            "ready_results_count": len(accepted_candidates),
            "official_validation_attempted": validation_attempted,
            "official_validation_passed": validation_passed,
            "pending_validation_count": pending_validation,
            "simulation_retry_pending": sum(1 for candidate in pool if candidate.lifecycle_status == "simulation_retry_pending"),
            "secondary_fusion_candidates": sum(1 for candidate in pool if candidate.mutation_type == "secondary_fusion"),
            "rejected_count": sum(archive_stats.values()),
            "rejected_stats": archive_stats,
            "archive_count": sum(archive_stats.values()),
            "archive_stats": archive_stats,
            "backtest_slot_limit": active_backtest_limit,
            "recovered_backtest_slot_count": self.recovered_backtest_slot_count,
            "backtests": self._slot_snapshot(),
            "official_call_policy": {
                "local_first": True,
                "retained_alpha_pool_size": self.config.budget.retained_alpha_pool_size,
                "official_backtest_batch_size": self.config.budget.official_backtest_batch_size,
                "max_official_validations_per_cycle": self.config.budget.max_official_validations_per_cycle,
                "max_official_simulations_per_cycle": self.config.budget.max_official_simulations_per_cycle,
                "max_official_concurrent_simulations": self.config.budget.max_official_concurrent_simulations,
                "active_backtest_slot_limit": active_backtest_limit,
                "max_simulation_retries": self.config.budget.max_simulation_retries,
                "enable_secondary_fusion": self.config.budget.enable_secondary_fusion,
                "resume_persisted_backtests": getattr(self.config.budget, "resume_persisted_backtests", True),
                "poll_interval_seconds": self._poll_interval_seconds(),
                "poll_attempt_limit": None,
                "min_prior_score_for_official_validation": self.config.budget.min_prior_score_for_official_validation,
                "min_prior_score_for_official_simulation": self.config.budget.min_prior_score_for_official_simulation,
            },
            "strategy_profile": self._current_strategy_profile(),
            "strategy_switch_count": self.strategy_switch_count,
            "official_calls_halted": self.official_calls_halted,
            "official_halt_reason": self.official_halt_reason,
            "official_retry_remaining_seconds": self._official_retry_remaining_seconds(),
            "observability_throttle": dict(self.observability_throttle),
            "observability_generation_guidance": dict(self.observability_generation_guidance),
            "observability_official_call_guard": self._observability_official_call_guard_snapshot(),
            "cloud_sync": self.cloud_sync,
            "cloud_alphas": self.cloud_alphas,
            "lifecycle_records": self.lifecycle_records,
            "backtest_records": self.backtest_records[-50:],
            "convergence": self.convergence.summary(),
            # P1-8: User profile for web dashboard display
            "user_profile": self.user_profile,
            # P3-1: Bandit stats for strategy selection
            "bandit": {
                "active_profile": self._current_strategy_profile().get("name", "unknown"),
                "profile_rewards": {str(k): round(sum(v)/max(len(v),1), 3)
                                    for k, v in self._bandit_rewards.items()},
                "profile_counts": self._bandit_counts,
                "total_switches": self.strategy_switch_count,
            },
            "strategy_lifecycle": self.strategy_lifecycle.summary(
                active_profile=self._current_strategy_profile(),
                active_index=self.strategy_profile_index,
            ),
            "strategy_plugins": self._strategy_plugin_summary(),
            # P0 UX: Dataset rotation & calibration visibility
            "active_dataset_id": self._active_dataset_id,
            "auto_calibrator_status": self.auto_calibrator.calibrate.__doc__[:1] if hasattr(self.auto_calibrator, 'calibrate') else "ready",
            "scoring_calibrated": bool(getattr(self.config.scoring, 'prior_weights_override', None)),
        }
        data.update(extra or {})
        return data

    def _halt_official_calls(self, reason: str, retry_seconds: float | None = None):
        self.official_calls_halted = True
        self.official_halt_reason = reason
        wait = self.config.budget.official_retry_pause_seconds if retry_seconds is None else retry_seconds
        self.official_resume_at = time.monotonic() + max(0.0, float(wait or 0.0))

    def _maybe_resume_official_calls(self):
        if self.official_calls_halted and time.monotonic() >= self.official_resume_at:
            self.official_calls_halted = False
            self.official_halt_reason = ""
            self.official_resume_at = 0.0

    def _official_retry_remaining_seconds(self) -> float:
        if not self.official_calls_halted:
            return 0.0
        return round(max(0.0, self.official_resume_at - time.monotonic()), 1)

    def _candidate_pool_service(self) -> CandidatePoolService:
        return CandidatePoolService(
            retained_alpha_pool_size=self.config.budget.retained_alpha_pool_size,
            min_prior_score_for_official_validation=self.config.budget.min_prior_score_for_official_validation,
            min_prior_score_for_official_simulation=self.config.budget.min_prior_score_for_official_simulation,
            ranker=rank_candidates,
            smart_ranker=self._smart_rank_candidates,
        )

    def _backtest_submission_service(self) -> BacktestSubmissionService:
        return BacktestSubmissionService(
            api=self.api,
            slots=self.backtest_slot_manager,
            settings_provider=lambda: self.config.settings.to_platform_dict()["settings"],
            poll_interval=self._poll_interval_seconds,
            halt_official_calls=self._halt_official_calls,
            event=self._event,
        )

    def _backtest_polling_service(self) -> BacktestPollingService:
        return BacktestPollingService(
            api=self.api,
            halt_official_calls=self._halt_official_calls,
            event=self._event,
        )

    def _backtest_finalization_service(self) -> BacktestFinalizationService:
        return BacktestFinalizationService(
            config=self.config,
            check_registry=self.check_registry,
            scoring_params=self.auto_calibrator.params,
            record_lifecycle=self._record_lifecycle,
            remember_accepted=self._remember_accepted,
            retry_simulation=self._retry_simulation_candidate,
            create_secondary_fusion=self._create_secondary_fusion_candidate,
            archive=self._archive,
            try_auto_submit=self._try_auto_submit,
            should_remove_after_official_result=self._should_remove_after_official_result,
            event=self._event,
            expression_key=_expr_key,
        )

    def _generation_phase_service(self) -> GenerationPhaseService:
        return GenerationPhaseService(
            generator=self.generator,
            max_candidates=self.config.budget.max_candidates_per_cycle,
            dataset_id=self._active_dataset_id,
            attach_assistant_guidance=_attach_assistant_guidance,
        )

    def _dataset_selection_service(self) -> DatasetSelectionService:
        return DatasetSelectionService(
            selector=self._selector,
            loader=self._loader,
            generator=self.generator,
            settings=self.config.settings,
            strategy=getattr(self.config.budget, "dataset_strategy", "rotate"),
            event=self._event,
        )

    def _experience_feedback_service(self) -> ExperienceFeedbackService:
        return ExperienceFeedbackService(
            storage_dir=self.config.storage_dir,
            generator=self.generator,
            event=self._event,
            log=logger,
        )

    def _official_workflow_service(self) -> OfficialWorkflowService:
        return OfficialWorkflowService(
            validate_for_open_backtest_slots=self._validate_for_open_backtest_slots,
            fill_backtest_slots=self._fill_backtest_slots,
            poll_due_backtests=self._poll_due_backtests,
            finalization_service_factory=self._backtest_finalization_service,
        )

    def _batch_backtest_coordinator(self) -> BatchBacktestCoordinator:
        return BatchBacktestCoordinator(
            ranker=self._smart_rank_candidates,
            min_score=self.config.budget.min_prior_score_for_official_simulation,
            batch_size=self._active_backtest_limit(),
        )

    def _secondary_fusion_service(self) -> SecondaryFusionService:
        return SecondaryFusionService(
            config=self.config,
            scoring_params=self.auto_calibrator.params,
            optimizer=self.optimizer,
            record_lifecycle=self._record_lifecycle,
            event=self._event,
            retry_count=self._simulation_retry_count,
        )

    def _fusion_candidate_service(self) -> FusionCandidateService:
        return FusionCandidateService(
            config=self.config,
            scoring_params=self.auto_calibrator.params,
            record_lifecycle=self._record_lifecycle,
            event=self._event,
        )

    def _eligible_profiles(self) -> list[dict]:
        """Return ADAPTIVE_PROFILES filtered by current account tier."""
        profile = getattr(self, "user_profile", None) or {}
        return eligible_strategy_profiles(profile)

    def _initial_strategy_profile_index(self) -> int:
        for index, profile in enumerate(self._eligible_profiles()):
            if (
                profile["region"] == self.config.settings.region
                and profile["universe"] == self.config.settings.universe
                and profile["delay"] == self.config.settings.delay
                and profile["neutralization"] == self.config.settings.neutralization
            ):
                return index
        return 0

    def _current_strategy_profile(self) -> dict:
        eligible = self._eligible_profiles()
        idx = self.strategy_profile_index % max(len(eligible), 1)
        profile = dict(eligible[idx])
        profile["settings"] = self.config.settings.to_platform_dict()["settings"]
        return profile

    def _maybe_switch_strategy(
        self,
        cycle: int,
        fields: list[dict],
        operators: list[dict],
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
    ) -> tuple[list[dict], list[dict]]:
        if not self.config.budget.adaptive_strategy_enabled:
            return fields, operators
        if self.backtest_slots or self.official_calls_halted:
            return fields, operators
        min_results = max(1, int(self.config.budget.adaptive_min_official_results))
        min_cycles = max(1, int(self.config.budget.adaptive_min_cycles))
        results = self.official_results_since_strategy_switch
        ready_rate = self.ready_since_strategy_switch / max(results, 1)
        chronic_no_candidate = self.cycles_since_strategy_switch >= min_cycles and len(pool_by_expression) < 3
        chronic_official_fail = results >= min_results and ready_rate < float(self.config.budget.adaptive_min_ready_rate)
        if not chronic_no_candidate and not chronic_official_fail:
            return fields, operators
        trigger = "chronic_no_candidate" if chronic_no_candidate else "chronic_official_fail"
        current_profile = self._current_strategy_profile()
        self.strategy_lifecycle.validate(
            current_profile,
            index=self.strategy_profile_index,
            cycle=cycle,
            ready_rate=ready_rate,
            official_results=results,
            pool_size=len(pool_by_expression),
            trigger=trigger,
        )
        self._notify_strategy_plugins(
            "validate",
            current_profile,
            cycle=cycle,
            reason=trigger,
            ready_rate=ready_rate,
            official_results=results,
            pool_size=len(pool_by_expression),
        )

        # P3-1: Epsilon-greedy multi-armed bandit for strategy selection
        #   - epsilon=0.20: 20% random exploration, 80% best-known exploitation
        #   - reward = avg_sharpe × (0.5 + 0.5 × pass_rate)
        #   - cold-start: first selection per profile uses round-robin
        eligible = self._eligible_profiles()
        n_profiles = len(eligible)
        switch_service = StrategySwitchService()
        decision = switch_service.select_next_index(
            current_index=self.strategy_profile_index,
            eligible_profiles=eligible,
            bandit_rewards=self._bandit_rewards,
            bandit_counts=self._bandit_counts,
        )
        next_idx = int(decision["next_index"])
        mean_rewards = dict(decision.get("mean_rewards") or {})

        application = switch_service.build_application(
            current_index=self.strategy_profile_index,
            next_index=next_idx,
            eligible_profiles=eligible,
        )
        old_idx = application.old_index
        old_profile = application.old_profile
        profile = application.next_profile
        self.strategy_profile_index = application.next_index
        if not application.retained:
            self.strategy_lifecycle.retire(old_profile, index=old_idx, cycle=cycle, reason=trigger)
            self._notify_strategy_plugins("retire", old_profile, cycle=cycle, reason=trigger, profile_index=old_idx)
            self.strategy_lifecycle.mutate(
                old_profile,
                profile,
                parent_index=old_idx,
                child_index=next_idx,
                cycle=cycle,
                reason=trigger,
            )
            self._notify_strategy_plugins(
                "mutate",
                profile,
                cycle=cycle,
                reason=trigger,
                parent_profile=old_profile,
                parent_profile_index=old_idx,
                profile_index=next_idx,
            )
        else:
            self.strategy_lifecycle.propose(profile, index=next_idx, cycle=cycle, reason=f"retained after {trigger}")
            self._notify_strategy_plugins(
                "propose",
                profile,
                cycle=cycle,
                reason=f"retained after {trigger}",
                profile_index=next_idx,
            )
        bandit_note = str(decision.get("mode") or ("exploit" if self._bandit_rewards.get(next_idx) else "cold-start"))
        self._event("bandit_selection",
            f"Bandit {bandit_note}: profile {profile['name']} (idx={next_idx}) "
            f"reward={mean_rewards.get(next_idx, 0):.3f} "
            f"count={self._bandit_counts.get(next_idx, 0)}",
            level="INFO")
        self.config.settings.region = application.settings["region"]
        self.config.settings.universe = application.settings["universe"]
        self.config.settings.delay = application.settings["delay"]
        self.config.settings.neutralization = application.settings["neutralization"]
        setter = getattr(self.api, "set_market_scope", None)
        if callable(setter):
            setter(self.config.settings)
        self.strategy_switch_count += 1
        self.cycles_since_strategy_switch = 0
        self.official_results_since_strategy_switch = 0
        self.ready_since_strategy_switch = 0
        self.official_rejections_since_strategy_switch = 0
        retained_ids = set(switch_service.retained_candidate_ids(list(pool_by_expression.values())))
        for candidate in pool_by_expression.values():
            if candidate.alpha_id in retained_ids:
                candidate.validation = {}
                candidate.lifecycle_status = "candidate_pool_retained"
        self._event(
            "adaptive_strategy_switched",
            f"Switched to {profile['label']}: {profile['reason']}",
            data={"profile": profile, "cycle": cycle},
            level="WARN",
        )
        self._progress(
            "strategy_switch",
            self.strategy_switch_count,
            max(1, len(eligible)),
            f"长期回测未通过，切换到：{profile['label']}。{profile['reason']}",
            data=self._runtime_data(
                cycle,
                rank_candidates(list(pool_by_expression.values())),
                accepted_candidates,
                archive_stats,
                {"strategy_profile": self._current_strategy_profile()},
            ),
        )
        return self._load_official_context()

    def _local_prefilter(
        self,
        generated: list[Candidate],
        cycle: int,
        fields: list[dict],
        operators: list[dict],
    ) -> list[Candidate]:
        passed = []
        total = len(generated)
        for index, candidate in enumerate(generated, start=1):
            candidate.local_quality = local_quality(candidate, self.config.budget.min_local_quality_score)
            build_scorecard(candidate, self.config.thresholds, self.config.scoring,
                          params=self.auto_calibrator.params)
            candidate.submission["cycle"] = cycle
            context_reasons = self._official_context_reasons(candidate, fields, operators)
            if context_reasons:
                candidate.gate = {
                    "schema_version": "production-gate-v2.1",
                    "submission_ready": False,
                    "status": "OFFICIAL_CONTEXT_WARNING",
                    "failed_reasons": [],
                    "warnings": context_reasons,
                }
                candidate.local_quality.setdefault("warnings", []).extend(context_reasons)
                self._event("official_context_warning", "; ".join(context_reasons), candidate.alpha_id)
            if candidate.local_quality["passed"]:
                candidate.lifecycle_status = "local_prefilter_passed"
                passed.append(candidate)
            else:
                candidate.lifecycle_status = "local_prefilter_rejected"
                candidate.gate = _blocked_gate("LOCAL_PREFILTER_REJECTED", candidate.local_quality["reasons"])
                self._event("local_prefilter_rejected", "; ".join(candidate.local_quality["reasons"]), candidate.alpha_id)
            self._record_lifecycle(candidate, "local_scored", "; ".join(candidate.local_quality.get("reasons", [])))
            visible_candidates = rank_candidates(passed)
            self._progress(
                "local_scoring",
                index,
                total,
                f"本地评价 {index}/{total}：{candidate.alpha_id} = {candidate.scorecard.get('total_score', 0.0):.2f}",
                candidate.alpha_id,
                data={
                    "cycle": cycle,
                    "produced_count": self.produced_count,
                    "candidates": self._candidate_snapshot(visible_candidates, retained=False),
                    "candidate_pool_available_count": len(visible_candidates),
                    "candidate_pool_source_count": len(visible_candidates),
                    "retained_pool_limit": self.config.budget.retained_alpha_pool_size,
                    "local_scored_count": index,
                    "local_scoring_passed_count": len(visible_candidates),
                },
            )
        ranked = rank_candidates(passed)
        self._event("local_candidates_ranked", f"Ranked {len(ranked)} local candidates before official calls.")
        return ranked

    def _top_up_candidate_pool(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        fields: list[dict],
        operators: list[dict],
        accepted_candidates: list[Candidate],
    ):
        retained_limit = max(1, self.config.budget.retained_alpha_pool_size)
        attempts = 0
        while (
            len(self._candidate_pool_candidates(list(pool_by_expression.values()))) < retained_limit
            and attempts < 2
            and not self._should_stop()
        ):
            available = len(self._candidate_pool_candidates(list(pool_by_expression.values())))
            deficit = retained_limit - available
            batch_size = min(
                max(int(deficit * 2), retained_limit),
                max(1, int(self.config.budget.max_candidates_per_cycle)),
            )
            generated = self.generator.generate(batch_size, dataset_id=self._active_dataset_id)
            attempts += 1
            if not generated:
                break
            self.produced_count += len(generated)
            for candidate in generated:
                self._record_lifecycle(candidate, "generated", "候选池补位生成")
            self._event("candidates_top_up_generated", f"Cycle {cycle}: generated {len(generated)} top-up candidates.")
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

        if attempts:
            pool = rank_candidates(list(pool_by_expression.values()))
            available = len(self._candidate_pool_candidates(pool))
            self._progress(
                "candidate_pool",
                available,
                retained_limit,
                f"候选池补位完成：可见候选 {available}/{retained_limit}；等待回测 Alpha 已从候选池视图移出。",
                data=self._runtime_data(cycle, pool, accepted_candidates, archive_stats),
            )

    def _refresh_context_validation_cache(self, fields: list[dict], operators: list[dict]) -> None:
        field_names: set[str] = set()
        for item in fields:
            for key in ("id", "name"):
                value = str(item.get(key, "")).strip().lower()
                if value:
                    field_names.add(value)
        self._context_field_names = field_names
        self._context_operator_names = {
            str(item.get("name", "")).strip().lower()
            for item in operators
            if item.get("name")
        }
        self._dataset_field_names_cache.clear()

    def _active_dataset_field_names(self) -> set[str]:
        dataset_id = str(self._active_dataset_id or "")
        if not dataset_id or not self._mapper:
            return set()
        cached = self._dataset_field_names_cache.get(dataset_id)
        if cached is not None:
            return cached
        try:
            fields = {str(field).lower() for field in self._mapper.fields_for(dataset_id)}
        except Exception:
            fields = set()
        self._dataset_field_names_cache[dataset_id] = fields
        return fields

    def _official_context_reasons(self, candidate: Candidate, fields: list[dict], operators: list[dict]) -> list[str]:
        if (fields and not self._context_field_names) or (operators and not self._context_operator_names):
            self._refresh_context_validation_cache(fields, operators)
        available_fields = self._context_field_names
        available_operators = self._context_operator_names
        reasons = []
        if available_fields:
            missing_fields = sorted(field for field in candidate.data_fields if field.lower() not in available_fields)
            if missing_fields:
                reasons.append("fields unavailable in current official context: " + ", ".join(missing_fields))
        if available_operators:
            missing_operators = sorted(operator for operator in candidate.operators if operator.lower() not in available_operators)
            if missing_operators:
                reasons.append("operators unavailable in current official context: " + ", ".join(missing_operators))

        # P1-1: Dataset consistency check — fields must belong to active dataset
        if self._active_dataset_id and self._mapper:
            ds_fields = self._active_dataset_field_names()
            for field in candidate.data_fields:
                if field.lower() not in ds_fields and field.lower() not in {"returns", "sector", "industry", "subindustry", "market"}:
                    reasons.append(
                        f"field '{field}' not in active dataset '{self._active_dataset_id}'. "
                        f"Expression may use fields from wrong dataset."
                    )
                    break  # one warning is sufficient
        return reasons

    def _merge_into_pool(
        self,
        pool_by_expression: dict[str, Candidate],
        candidates: list[Candidate],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        return self._candidate_pool_service().merge_into_pool(
            pool_by_expression,
            candidates,
            blocked_expressions,
        )

    def _remove_below_local_standard(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().remove_below_local_standard(pool_by_expression)

    def _prune_pool(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().prune_pool(
            pool_by_expression,
            is_active_backtest_candidate=self._is_active_backtest_candidate,
        )

    def _validation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().validation_targets(pool)

    def _validation_quota(self, pool: list[Candidate]) -> int:
        active_limit = self._active_backtest_limit()
        active_count = self.backtest_slot_manager.active_count()
        pending_count = len(self._pending_backtest_candidates(pool))
        needed_for_slots = max(0, active_limit - active_count - pending_count)
        return min(
            max(0, int(self.config.budget.max_official_validations_per_cycle)),
            needed_for_slots,
        )

    def _validate_for_open_backtest_slots(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        pool = rank_candidates(list(pool_by_expression.values()))
        validation_targets = self._validation_targets(pool)
        max_attempts = max(0, int(self.config.budget.max_official_validations_per_cycle))
        if max_attempts <= 0 or not validation_targets:
            return pool

        attempted = 0
        active_limit = self._active_backtest_limit()
        for candidate in validation_targets:
            pool = rank_candidates(list(pool_by_expression.values()))
            active_count = self.backtest_slot_manager.active_count()
            pending_count = len(self._pending_backtest_candidates(pool))
            if active_count + pending_count >= active_limit:
                break
            if attempted >= max_attempts or self.official_calls_halted:
                break
            if self._block_observability_duplicate_before_official(candidate, phase="official_validation"):
                self._archive(
                    archive_stats,
                    [],
                    self._archive_validation_failures(pool_by_expression, [candidate], blocked_expressions),
                )
                continue

            self._validate([candidate])
            attempted += 1
            self._archive(
                archive_stats,
                [],
                self._archive_validation_failures(pool_by_expression, [candidate], blocked_expressions),
            )
            if self.official_calls_halted:
                break
        return rank_candidates(list(pool_by_expression.values()))

    def _filter_observability_duplicate_targets(self, candidates: list[Candidate], *, phase: str) -> list[Candidate]:
        filtered = []
        for candidate in candidates:
            if self._block_observability_duplicate_before_official(candidate, phase=phase):
                continue
            filtered.append(candidate)
        return filtered

    def _validate(self, candidates: list[Candidate]) -> list[Candidate]:
        outcome = OfficialValidationService(
            api=self.api,
            settings_payload=self.config.settings.to_platform_dict()["settings"],
            progress=self._progress,
            event=self._event,
            record_lifecycle=self._record_lifecycle,
            halt_official_calls=self._halt_official_calls,
        ).validate(candidates)
        self.official_validation_attempted_count += outcome.attempted
        self.official_validation_passed_count += outcome.passed
        return outcome.valid

    def _archive_validation_failures(
        self,
        pool_by_expression: dict[str, Candidate],
        validation_targets: list[Candidate],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        archived = []
        for candidate in validation_targets:
            if candidate.lifecycle_status == "official_validation_failed":
                key = _expr_key(candidate)
                pool_by_expression.pop(key, None)
                blocked_expressions.add(key)
                archived.append(candidate)
            elif candidate.lifecycle_status == "observability_duplicate_blocked":
                key = _expr_key(candidate)
                pool_by_expression.pop(key, None)
                blocked_expressions.add(key)
                archived.append(candidate)
        return archived

    def _backtest_targets(self, pool: list[Candidate]) -> list[Candidate]:
        candidates = self._candidate_pool_service().backtest_targets(
            pool,
            batch_size=self._active_backtest_limit(),
        )
        plan = self._batch_backtest_coordinator().plan(
            candidates,
            capacity=self._active_backtest_limit(),
        )
        self.last_runtime_data["backtest_batch_plan"] = plan.to_dict()
        return list(plan.selected)

    def _pending_backtest_candidates(self, pool: list[Candidate], threshold: float | None = None) -> list[Candidate]:
        return self._candidate_pool_service().pending_backtest_candidates(pool, threshold=threshold)

    def _is_pending_backtest_candidate(self, candidate: Candidate, threshold: float | None = None) -> bool:
        return self._candidate_pool_service().is_pending_backtest_candidate(candidate, threshold)

    def _is_observability_duplicate_before_official(self, candidate: Candidate) -> bool:
        guidance = self.observability_generation_guidance if isinstance(self.observability_generation_guidance, dict) else {}
        return self.official_call_guard.should_block(candidate, guidance)

    def _observability_official_call_guard_snapshot(self) -> dict:
        return self.official_call_guard.snapshot()

    def _record_observability_official_call_guard(self, candidate: Candidate, *, phase: str, expression_canonical: str) -> dict:
        guard = self.official_call_guard.record_block(
            candidate,
            phase=phase,
            expression_canonical=expression_canonical,
        )
        if isinstance(self.observability_throttle, dict):
            self.observability_throttle["official_call_guard"] = guard
        return guard

    def _block_observability_duplicate_before_official(self, candidate: Candidate, *, phase: str) -> bool:
        guidance = self.observability_generation_guidance if isinstance(self.observability_generation_guidance, dict) else {}
        block = self.official_call_guard.block(candidate, phase=phase, guidance=guidance)
        if not block:
            return False
        if isinstance(self.observability_throttle, dict):
            self.observability_throttle["official_call_guard"] = block["guard"]
        self._record_lifecycle(candidate, "observability_duplicate_blocked", phase)
        self._event(
            "observability_duplicate_official_call_blocked",
            block["reason"],
            candidate.alpha_id,
            data={
                "phase": phase,
                "expression_canonical": block["expression_canonical"],
                "observability_generation_guidance": dict(guidance),
                "observability_official_call_guard": block["guard"],
            },
            level="WARN",
        )
        return True

    def _is_active_backtest_candidate(self, candidate: Candidate) -> bool:
        if not candidate.simulation_id or candidate.official_metrics:
            return False
        return candidate.lifecycle_status not in {
            "simulation_failed",
            "simulation_poll_failed",
            "simulation_request_failed",
            "official_standard_rejected",
            "submission_ready",
        }

    def _candidate_pool_candidates(self, pool: list[Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().candidate_pool_candidates(
            pool,
            is_active_backtest_candidate=self._is_active_backtest_candidate,
        )

    def _pending_simulation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        return [
            candidate
            for candidate in pool
            if candidate.simulation_id
            and not candidate.official_metrics
            and candidate.lifecycle_status
            not in {
                "simulation_failed",
                "simulation_poll_failed",
                "simulation_request_failed",
                "official_standard_rejected",
                "submission_ready",
            }
        ]

    def _fill_backtest_slots(
        self,
        cycle: int,
        state: _CycleState,
    ):
        if self.official_calls_halted:
            return
        active_limit = self._active_backtest_limit()
        open_slots = self.backtest_slot_manager.open_slots(active_limit)
        if not open_slots:
            return

        submission_service = self._backtest_submission_service()
        for slot in open_slots:
            pool = rank_candidates(list(state.pool_by_expression.values()))
            candidate = self._next_backtest_candidate(pool)
            if not candidate:
                return
            if self._block_observability_duplicate_before_official(candidate, phase="official_simulation"):
                state.pool_by_expression.pop(_expr_key(candidate), None)
                state.blocked_expressions.add(_expr_key(candidate))
                self._archive(state.archive_stats, state.archive_samples, [candidate])
                continue
            self._progress(
                "simulation_submit",
                slot - 1,
                active_limit,
                f"回测槽 {slot} 准备提交：{candidate.alpha_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
            )
            outcome = submission_service.submit_slot(slot, candidate)
            if not outcome.submitted:
                self._record_backtest(
                    candidate,
                    "submit_failed",
                    slot=slot,
                    note=redact_error_message(outcome.error) if outcome.error else outcome.note,
                    error_context=(
                        self._official_error_context(
                            outcome.error,
                            outcome.error_code or "SIMULATION_SUBMIT_ERROR",
                            phase="simulation_submit",
                            candidate=candidate,
                        )
                        if outcome.error
                        else None
                    ),
                )
                self._progress(
                    "official_deferred" if self.official_calls_halted else "simulation_submit",
                    slot,
                    active_limit,
                    f"回测槽 {slot} 提交延后：{candidate.lifecycle_status}",
                    candidate.alpha_id,
                    data=self._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
                )
                return

            self.backtests_submitted += 1
            self._record_lifecycle(candidate, "simulation_submitted", f"slot={slot}")
            self._record_backtest(candidate, "submitted", slot=slot, status="SUBMITTED")
            self._progress(
                "simulation_submit",
                slot,
                active_limit,
                f"回测槽 {slot} 已提交：{outcome.simulation_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(state.pool_by_expression.values())), state.accepted_candidates, state.archive_stats),
            )

    def _next_backtest_candidate(self, pool: list[Candidate]) -> Candidate | None:
        return self.backtest_slot_manager.next_candidate(
            self._backtest_targets(pool),
            key_fn=_expr_key,
        )

    def _handle_slot_submit_error(self, exc: BrainAPIError, candidate: Candidate):
        self._backtest_submission_service()._handle_submit_error(exc, candidate)

    def _poll_due_backtests(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
        *,
        force_initial: bool = False,
    ) -> int:
        if not self.backtest_slots:
            return submitted_this_run
        now = time.monotonic()
        interval = self._poll_interval_seconds()
        polling_service = self._backtest_polling_service()
        for slot, candidate in self.backtest_slot_manager.items_snapshot():
            next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
            if not force_initial and now < next_poll_at:
                continue
            if force_initial and candidate.submission.get("poll_count", 0):
                continue

            candidate.submission["poll_count"] = int(candidate.submission.get("poll_count", 0) or 0) + 1
            self._progress(
                "simulation_wait",
                slot,
                self._active_backtest_limit(),
                f"轮询回测槽 {slot}：{candidate.alpha_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
            outcome = polling_service.poll(candidate, now=now, interval=interval)
            for record in outcome.records:
                self._record_backtest(
                    candidate,
                    record.action,
                    slot=slot,
                    status=record.status,
                    note=record.note,
                    error_context=(
                        self._official_error_context(
                            record.error,
                            record.error_code,
                            phase=record.phase,
                            candidate=candidate,
                        )
                        if record.error
                        else None
                    ),
                )

            self.officially_simulated_count += outcome.official_simulated_increment
            self.official_results_since_strategy_switch += outcome.official_result_increment
            if outcome.official_result:
                self._run_alpha_checks(candidate, outcome.result, cycle)
                self._run_robustness_checks(candidate, cycle)

            if outcome.release_slot:
                self.backtest_slot_manager.release(slot)
            if outcome.finalize:
                submitted_this_run = self._finalize_backtest_candidate(
                    candidate,
                    pool_by_expression,
                    accepted_candidates,
                    archive_stats,
                    archive_samples,
                    blocked_expressions,
                    submitted_this_run,
                    auto_submit,
                )
            if outcome.halted:
                return submitted_this_run

            self._progress(
                "simulation_wait",
                slot,
                self._active_backtest_limit(),
                f"回测槽 {slot} 状态：{candidate.submission.get('simulation_status') or candidate.lifecycle_status}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
        return submitted_this_run

    # Backtest result checks ──
    def _run_alpha_checks(self, candidate: "Candidate", result: dict, cycle: int) -> None:
        """Run BRAIN-standard alpha checks on a completed simulation result.

        Injects _thresholds into the sim_result for check functions that
        read threshold values.  ERROR-level failures set candidate gate
        to blocked; WARNING/INFO failures are informational only.
        """
        if not self.check_registry:
            return
        try:
            sim_result = dict(result.get("metrics", result))
            # Provide threshold access for check functions
            sim_result["_thresholds"] = self.config.thresholds
            sim_result["settings"] = self.config.settings.to_platform_dict().get("settings", {})
            sim_result["expression"] = candidate.expression
            sim_result["data_fields"] = candidate.data_fields
            sim_result["operators"] = candidate.operators

            report = self.check_registry.evaluate(sim_result)
            candidate.submission["alpha_check_report"] = {
                "total": report.total,
                "passed": report.passed_count,
                "failed": report.failed_count,
                "passed_overall": report.passed,
                "summary": report.summary,
            }
            if not report.passed:
                failed_names = [r.check_name for r in report.results if not r.passed and r.severity == "ERROR"]
                self._event("alpha_checks_failed",
                    f"Cycle {cycle}: AlphaCheckRegistry found {report.failed_count}/{report.total} failures "
                    f"for {candidate.alpha_id}: {failed_names[:5]}",
                    candidate.alpha_id, level="WARN")
            else:
                self._event("alpha_checks_passed",
                    f"Cycle {cycle}: Alpha {candidate.alpha_id} passed {report.passed_count}/{report.total} checks.",
                    candidate.alpha_id, level="INFO")
        except Exception:
            logger.warning("AlphaCheckRegistry failed for %s", candidate.alpha_id, exc_info=True)

    def _run_robustness_checks(self, candidate: Candidate, cycle: int) -> None:
        """Attach deterministic robustness reports after official metrics arrive."""
        try:
            anti_report = AntiOverfitService().evaluate(candidate)
            rolling_report = RollingValidationService().evaluate(candidate)
            candidate.submission["anti_overfit_report"] = anti_report
            candidate.submission["rolling_validation_report"] = rolling_report
            policy = RobustnessPolicy().apply(candidate, anti_report, rolling_report)
            if policy.get("action") != "allow":
                self._event(
                    "robustness_checks_caution",
                    f"Cycle {cycle}: robustness checks flagged {candidate.alpha_id}.",
                    candidate.alpha_id,
                    level="WARN",
                    data={
                        "anti_overfit": anti_report.get("recommendation"),
                        "rolling_validation": rolling_report.get("status"),
                        "robustness_policy": policy,
                    },
                )
            else:
                self._event(
                    "robustness_checks_passed",
                    f"Cycle {cycle}: robustness checks completed for {candidate.alpha_id}.",
                    candidate.alpha_id,
                    level="INFO",
                    data={
                        "anti_overfit_score": anti_report.get("score"),
                        "rolling_validation_score": rolling_report.get("score"),
                    },
                )
        except Exception as exc:
            message = redact_error_message(exc)
            candidate.submission["robustness_check_error"] = message
            self._event(
                "robustness_checks_error",
                f"Cycle {cycle}: robustness checks failed for {candidate.alpha_id}: {message}",
                candidate.alpha_id,
                level="WARN",
            )

    def _finalize_backtest_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
    ) -> int:
        outcome = self._backtest_finalization_service().finalize(
            candidate,
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
            archive_samples=archive_samples,
            blocked_expressions=blocked_expressions,
            submitted_this_run=submitted_this_run,
            auto_submit=auto_submit,
        )
        self.ready_since_strategy_switch += outcome.ready_increment
        self.official_rejections_since_strategy_switch += outcome.rejection_increment
        return outcome.submitted_this_run

    def _simulation_retry_count(self, candidate: Candidate) -> int:
        try:
            return max(0, int(candidate.submission.get("simulation_retry_count", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def _retry_simulation_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        reason: str,
    ) -> bool:
        max_retries = max(0, int(self.config.budget.max_simulation_retries or 0))
        retry_count = self._simulation_retry_count(candidate)
        if candidate.official_metrics or retry_count >= max_retries:
            return False

        candidate.simulation_id = ""
        candidate.official_alpha_id = ""
        candidate.official_metrics = {}
        candidate.lifecycle_status = "simulation_retry_pending"
        candidate.submission["simulation_retry_count"] = retry_count + 1
        candidate.submission["simulation_status"] = "RETRY_PENDING"
        candidate.submission["next_poll_at"] = 0.0
        candidate.submission["poll_count"] = 0
        candidate.gate = _blocked_gate("SIMULATION_RETRY_PENDING", [reason])
        pool_by_expression[_expr_key(candidate)] = candidate
        self._record_lifecycle(candidate, "simulation_retry_pending", reason)
        self._event(
            "simulation_retry_scheduled",
            f"Retry {retry_count + 1}/{max_retries} scheduled after official simulation failure.",
            candidate.alpha_id,
            data={"retry_count": retry_count + 1, "max_retries": max_retries},
            level="WARN",
        )
        return True

    def _create_secondary_fusion_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        reason: str,
    ) -> Candidate | None:
        outcome = self._secondary_fusion_service().create(
            candidate,
            pool_by_expression=pool_by_expression,
            blocked_expressions=blocked_expressions,
            reason=reason,
        )
        self.produced_count += outcome.produced_increment
        return outcome.candidate

    def _try_fusion_top_candidates(
        self,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        cycle: int,
    ) -> int:
        outcome = self._fusion_candidate_service().create_top_candidate_fusions(
            pool_by_expression,
            blocked_expressions,
            cycle=cycle,
        )
        self.produced_count += outcome.created_count
        return outcome.created_count

    def _poll_interval_seconds(self) -> float:
        api_config = getattr(self.api, "config", None)
        return max(0.1, float(getattr(api_config, "poll_interval_seconds", self.config.official_api.poll_interval_seconds)))

    def _simulate_batch(self, candidates: list[Candidate]) -> list[Candidate]:
        submitted: list[Candidate] = []
        total = len(candidates)
        if not candidates:
            self._progress("official_simulation", 0, 1, "候选池中暂时没有满足回测门槛的 Alpha。")
            return submitted

        self._progress(
            "simulation_submit",
            0,
            total,
            f"已选择排名前 {total} 的 Alpha，准备逐个提交官方回测任务。",
            data={"backtests": self._backtest_snapshot(candidates)},
        )
        for index, candidate in enumerate(candidates, start=1):
            self._progress("simulation_submit", index - 1, total, f"提交回测任务 {index}/{total}：{candidate.alpha_id}", candidate.alpha_id)
            settings = self.config.settings.to_platform_dict()["settings"]
            candidate.submission["settings"] = dict(settings)
            try:
                sim_id = self.api.submit_simulation(candidate.expression, settings)
            except BrainAPIError as exc:
                self._handle_simulation_submit_error(exc, candidate, candidates[index:], submitted)
                break
            candidate.simulation_id = sim_id
            candidate.lifecycle_status = "simulation_submitted"
            candidate.submission["backtest_batch_rank"] = index
            submitted.append(candidate)
            self.backtests_submitted += 1
            self._progress(
                "simulation_submit",
                index,
                total,
                f"回测任务 {index}/{total} 已提交：{sim_id}",
                candidate.alpha_id,
                data={"backtests": self._backtest_snapshot(candidates)},
            )

        real_submitted = [candidate for candidate in submitted if candidate.simulation_id]
        if real_submitted:
            self._wait_for_simulation_batch(real_submitted)
        return submitted

    def _handle_simulation_submit_error(
        self,
        exc: BrainAPIError,
        candidate: Candidate,
        remaining: list[Candidate],
        submitted: list[Candidate],
    ):
        error_text = redact_error_message(exc)
        if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
            status = "SIMULATION_DEFERRED_CONCURRENCY_LIMIT"
            reason = "official concurrent simulation limit exceeded; retry after running BRAIN simulations finish"
        elif exc.status_code == 429:
            status = "SIMULATION_DEFERRED_RATE_LIMIT"
            retry_after = f"; retry_after={exc.retry_after}" if exc.retry_after is not None else ""
            reason = f"official API rate limit reached{retry_after}; defer remaining official calls"
        else:
            candidate.lifecycle_status = "simulation_request_failed"
            candidate.gate = _blocked_gate("SIMULATION_REQUEST_FAILED", [error_text])
            submitted.append(candidate)
            self._event("official_simulation_failed", "; ".join(candidate.gate["failed_reasons"]), candidate.alpha_id)
            return

        self._halt_official_calls(reason)
        for item in [candidate] + remaining:
            item.lifecycle_status = status.lower()
            item.gate = _blocked_gate(status, [reason])
            submitted.append(item)
        self._event("official_simulation_halted", reason, candidate.alpha_id)
        self._progress("official_deferred", 0, 1, reason, candidate.alpha_id, data={"backtests": self._backtest_snapshot(submitted)})

    def _wait_for_simulation_batch(self, candidates: list[Candidate]):
        api_config = getattr(self.api, "config", None)
        attempts = max(1, int(getattr(api_config, "poll_attempts", 1)))
        interval = max(0.0, float(getattr(api_config, "poll_interval_seconds", 0.0)))
        running = {candidate.simulation_id: candidate for candidate in candidates if candidate.simulation_id}
        completed_count = 0

        for attempt in range(1, attempts + 1):
            for sim_id, candidate in list(running.items()):
                try:
                    status = self.api.poll_simulation(sim_id)
                except BrainAPIError as exc:
                    if exc.status_code == 429:
                        self._halt_official_calls(f"official simulation polling rate limit reached; retry later: {redact_error_message(exc)}")
                        candidate.lifecycle_status = "simulation_poll_deferred_rate_limit"
                        candidate.gate = _blocked_gate("SIMULATION_POLL_DEFERRED_RATE_LIMIT", [self.official_halt_reason])
                        self._event("official_simulation_poll_deferred", self.official_halt_reason, candidate.alpha_id, level="WARN")
                        return
                    candidate.lifecycle_status = "simulation_poll_failed"
                    candidate.gate = _blocked_gate("SIMULATION_POLL_FAILED", [redact_error_message(exc)])
                    del running[sim_id]
                    completed_count += 1
                    continue

                candidate.submission["simulation_status"] = status
                if status == "COMPLETED":
                    try:
                        result = self.api.fetch_result(sim_id)
                    except BrainAPIError as exc:
                        if exc.status_code == 429:
                            self._halt_official_calls(f"official simulation result rate limit reached; retry later: {redact_error_message(exc)}")
                            candidate.lifecycle_status = "simulation_result_deferred_rate_limit"
                            candidate.gate = _blocked_gate("SIMULATION_RESULT_DEFERRED_RATE_LIMIT", [self.official_halt_reason])
                            self._event("official_simulation_result_deferred", self.official_halt_reason, candidate.alpha_id, level="WARN")
                            return
                        candidate.lifecycle_status = "simulation_result_failed"
                        candidate.gate = _blocked_gate("SIMULATION_RESULT_FAILED", [redact_error_message(exc)])
                        del running[sim_id]
                        completed_count += 1
                        continue
                    candidate.official_alpha_id = result.get("alpha_id", "") or result.get("metrics", {}).get("official_alpha_id", "")
                    candidate.official_metrics = result.get("metrics", {})
                    candidate.lifecycle_status = "official_simulated"
                    self.officially_simulated_count += 1
                    del running[sim_id]
                    completed_count += 1
                elif status == "FAILED":
                    candidate.lifecycle_status = "simulation_failed"
                    candidate.gate = _blocked_gate("SIMULATION_FAILED", [status])
                    del running[sim_id]
                    completed_count += 1
                else:
                    candidate.lifecycle_status = "simulation_running"

            self._progress(
                "simulation_wait",
                completed_count,
                len(candidates),
                f"等待回测结果：完成 {completed_count}/{len(candidates)}，轮询 {attempt}/{attempts}。",
                data={
                    "backtests": self._backtest_snapshot(candidates),
                    "completed": completed_count,
                },
            )
            if not running:
                return
            if attempt < attempts and interval:
                if not self._sleep_with_stop(interval):
                    return

        for candidate in running.values():
            candidate.lifecycle_status = "simulation_timeout"
            candidate.gate = _blocked_gate("SIMULATION_TIMEOUT", ["official simulation did not finish before poll timeout"])

    def _should_remove_after_official_result(self, candidate: Candidate) -> bool:
        if not candidate.official_metrics:
            return candidate.lifecycle_status in {
                "simulation_failed",
                "simulation_poll_failed",
                "simulation_request_failed",
                "simulation_result_failed",
                "simulation_timeout",
            }
        if candidate.gate.get("submission_ready"):
            candidate.lifecycle_status = "submission_ready"
            return False
        candidate.lifecycle_status = "official_standard_rejected"
        if not candidate.gate:
            candidate.gate = _blocked_gate("OFFICIAL_STANDARD_REJECTED", ["official metrics did not pass configured quality gate"])
        return True

    def _check_before_submit(self, candidate: Candidate) -> dict:
        """提交前最终 AlphaCheck 门禁。

        仅在 safety checks 全部通过后调用，确保 ERROR 级别
        AlphaCheck 失败会阻断自动提交。

        Returns:
            {"passed": bool, "failed_checks": [...], "warnings": [...]}
        """
        if not candidate.official_metrics or not candidate.expression:
            return {"passed": True, "failed_checks": [], "warnings": []}

        sim_result = {
            "_thresholds": self.config.thresholds,
            **candidate.official_metrics,
            "expression": candidate.expression,
            "data_fields": getattr(candidate, "data_fields", []),
            "operators": getattr(candidate, "operators", []),
        }
        try:
            sim_result["settings"] = self.config.settings.__dict__
        except Exception as exc:
            logger.warning("Failed to serialize settings for check registry: %s", exc)

        try:
            report = self.check_registry.evaluate(sim_result)
        except Exception as exc:
            return {
                "passed": False,
                "failed_checks": [{"name": "check_registry_error", "message": redact_error_message(exc)}],
                "warnings": [],
            }

        errors = [r for r in report.results if not r.passed and r.severity == "ERROR"]
        warnings = [r for r in report.results if not r.passed and r.severity != "ERROR"]

        return {
            "passed": len(errors) == 0,
            "failed_checks": [{"name": r.check_name, "message": r.message} for r in errors],
            "warnings": [{"name": r.check_name, "message": r.message} for r in warnings],
        }

    def _try_auto_submit(self, candidate: Candidate, submitted_this_run: int) -> int:
        safety = self._assess_auto_submission(candidate, submitted_this_run)
        candidate.submission["safety"] = safety
        if not safety["allowed"]:
            self._event("auto_submit_skipped", "; ".join(safety["failed_reasons"]), candidate.alpha_id)
            return 0
        submission = self.api.submit_alpha(
            candidate.official_alpha_id,
            candidate.expression,
            self.config.settings.to_platform_dict()["settings"],
        )
        candidate.submission["result"] = submission
        candidate.lifecycle_status = "submitted"
        self.ledger.record(candidate, submission, mode="auto")
        self._record_lifecycle(candidate, "submitted", "auto")
        self._event("alpha_submitted", f"Submitted {candidate.alpha_id}.", candidate.alpha_id)
        return 1

    def _assess_auto_submission(self, candidate: Candidate, submitted_this_run: int) -> dict:
        safety = self.ledger.assess(
            candidate,
            self.config.submission_policy,
            mode="auto",
            run_submission_count=submitted_this_run,
        )
        checks = list(safety.get("checks") or [])
        failed = list(safety.get("failed_reasons") or [])

        def add(name: str, passed: bool, detail: str):
            checks.append({"name": name, "passed": bool(passed), "detail": detail})
            if not passed:
                failed.append(detail or name)

        if not self._using_mock_api():
            reasons = mock_source_reasons(candidate)
            add(
                "mock_source_not_present",
                not reasons,
                "; ".join(reasons) if reasons else "no mock/demo/test source markers",
            )

        if self.config.budget.require_cloud_sync:
            cloud_status = str(self.cloud_sync.get("status", "")).lower()
            add(
                "cloud_sync_completed",
                cloud_status in {"synced", "loaded"},
                self.cloud_sync.get("warning") or f"cloud sync status={cloud_status or 'unknown'}",
            )
            add(
                "cloud_sync_has_rows",
                bool(self.cloud_alphas),
                f"{len(self.cloud_alphas)} cloud alphas loaded",
            )
            add(
                "cloud_sync_not_stale",
                not bool(self.cloud_sync.get("stale")),
                "cloud alpha cache is stale" if self.cloud_sync.get("stale") else "cloud alpha sync is fresh",
            )

        cloud_alpha_status = self._cloud_status_for_candidate(candidate)
        already_submitted = str(cloud_alpha_status.get("status", "")).upper() in SUBMITTED_CLOUD_STATUSES
        add(
            "cloud_status_not_already_submitted",
            not already_submitted,
            cloud_alpha_status.get("status") or "not found",
        )

        cloud_risk = self._cloud_correlation_risk(candidate)
        add(
            "cloud_self_correlation",
            cloud_risk.get("level") != "high",
            f"{cloud_risk.get('level', 'unknown')} {float(cloud_risk.get('max_similarity', 0.0) or 0.0):.4f}",
        )

        safety["checks"] = checks
        safety["failed_reasons"] = failed
        safety["allowed"] = not failed
        safety["status"] = "ALLOW" if not failed else "BLOCK"
        # ── P0-4: AlphaCheck gate — ERROR-level failures block submission ──
        if safety["allowed"] and candidate.official_metrics:
            check_result = self._check_before_submit(candidate)
            if not check_result["passed"]:
                for err in check_result["failed_checks"]:
                    failed.append(f"BRAIN_CHECK_GATE:{err['name']}:{err['message']}")
                safety["allowed"] = False
                safety["status"] = "BLOCK"
            safety["alpha_check_gate"] = check_result
        safety["cloud_sync"] = dict(self.cloud_sync)
        safety["cloud_status"] = cloud_alpha_status
        safety["cloud_correlation_risk"] = cloud_risk
        return safety

    def _using_mock_api(self) -> bool:
        return self.api.__class__.__name__.lower().startswith("mock")

    def _summary(
        self,
        candidates: list[Candidate],
        submitted_this_run: int,
        pool_by_expression: dict[str, Candidate],
        archive_stats: dict[str, int],
    ) -> dict:
        ready = [candidate for candidate in candidates if candidate.gate.get("submission_ready")]
        pool_values = list(pool_by_expression.values())
        candidate_pool = self._candidate_pool_candidates(pool_values)
        pending_backtests = self._pending_backtest_candidates(pool_values)
        validation_attempted = self.official_validation_attempted_count
        validation_passed = self.official_validation_passed_count
        auto_allowed = [
            candidate
            for candidate in ready
            if not self._assess_auto_submission(candidate, 0)["failed_reasons"]
        ]
        active_backtest_limit = self._active_backtest_limit()
        return {
            "total_candidates": self.produced_count,
            "produced_count": self.produced_count,
            "retained_pool_size": len(candidate_pool),
            "candidate_pool_available_count": len(candidate_pool),
            "candidate_pool_source_count": len(pool_values),
            "candidate_pool_excludes_waiting_backtests": True,
            "retained_pool_limit": self.config.budget.retained_alpha_pool_size,
            "rejected_count": sum(archive_stats.values()),
            "rejected_stats": dict(archive_stats),
            "archive_count": sum(archive_stats.values()),
            "archive_stats": dict(archive_stats),
            "backtest_batch_size": self.config.budget.official_backtest_batch_size,
            "backtest_slot_limit": active_backtest_limit,
            "backtests_submitted": self.backtests_submitted,
            "recovered_backtest_slot_count": self.recovered_backtest_slot_count,
            "local_ranked": sum(1 for candidate in candidates if candidate.scorecard.get("score_basis") == "local_prior"),
            "official_validation_attempted": validation_attempted,
            "official_validation_passed": validation_passed,
            "pending_validation_count": len(self._validation_targets(pool_values)),
            "officially_simulated": self.officially_simulated_count,
            "official_deferred": sum(1 for candidate in candidates if str(candidate.lifecycle_status).startswith("simulation_deferred")),
            "simulation_retry_pending": sum(1 for candidate in pool_values if candidate.lifecycle_status == "simulation_retry_pending"),
            "secondary_fusion_candidates": sum(1 for candidate in pool_values if candidate.mutation_type == "secondary_fusion"),
            "pending_backtest_count": len(pending_backtests),
            "submission_ready": len(ready),
            "ready_results_count": len(ready),
            "auto_submit_ready": len(auto_allowed),
            "submitted_this_run": submitted_this_run,
            "best_score": max((candidate.scorecard.get("total_score", 0.0) for candidate in candidates), default=0.0),
            "operating_mode": "local_autonomous_loop_top10_top3",
            "run_forever": self.config.budget.run_forever,
            "official_calls_halted": self.official_calls_halted,
            "official_halt_reason": self.official_halt_reason,
            "observability_throttle": dict(self.observability_throttle),
            "observability_generation_guidance": dict(self.observability_generation_guidance),
            "observability_official_call_guard": self._observability_official_call_guard_snapshot(),
            "official_context": dict(self.context_summary),
            "backtest_slots": self._slot_snapshot(),
            "strategy_profile": self._current_strategy_profile(),
            "strategy_switch_count": self.strategy_switch_count,
            "strategy_lifecycle": self.strategy_lifecycle.summary(
                active_profile=self._current_strategy_profile(),
                active_index=self.strategy_profile_index,
            ),
            "strategy_plugins": self._strategy_plugin_summary(),
            "cloud_sync": dict(self.cloud_sync),
            "cloud_alphas": list(self.cloud_alphas),
            "lifecycle_records": list(self.lifecycle_records),
            "backtest_records": list(self.backtest_records[-50:]),
            "convergence": self.convergence.summary(),
            "candidates": self._candidate_snapshot(candidate_pool),
            "passed_candidates": self._candidate_snapshot(ready, limit=50, retained=False),
            "pending_backtest_candidates": self._candidate_snapshot(pending_backtests, limit=50, retained=False),
            "official_call_policy": {
                "local_first": True,
                "retained_alpha_pool_size": self.config.budget.retained_alpha_pool_size,
                "official_backtest_batch_size": self.config.budget.official_backtest_batch_size,
                "max_official_validations_per_cycle": self.config.budget.max_official_validations_per_cycle,
                "max_official_simulations_per_cycle": self.config.budget.max_official_simulations_per_cycle,
                "max_official_concurrent_simulations": self.config.budget.max_official_concurrent_simulations,
                "active_backtest_slot_limit": active_backtest_limit,
                "max_simulation_retries": self.config.budget.max_simulation_retries,
                "enable_secondary_fusion": self.config.budget.enable_secondary_fusion,
                "resume_persisted_backtests": getattr(self.config.budget, "resume_persisted_backtests", True),
                "poll_interval_seconds": self._poll_interval_seconds(),
                "poll_attempt_limit": None,
                "min_prior_score_for_official_validation": self.config.budget.min_prior_score_for_official_validation,
                "min_prior_score_for_official_simulation": self.config.budget.min_prior_score_for_official_simulation,
            },
            "can_complete_goal": {
                "local_production_evaluation_ranking_loop": True,
                "retains_top_10_before_backtest": True,
                "submits_top_3_backtests_per_cycle": True,
                "waits_for_backtest_results": True,
                "screen_progress_updates": True,
                "caveat": "Official rate limits can still defer a batch; deferred candidates are not treated as alpha-quality failures.",
            },
            # P2-8: CLI-readable summary fields
            "user_profile": self.user_profile,
            "score_distribution": _compute_score_distribution(candidates),
            "gate_summary": _compute_gate_summary(candidates),
            "auto_submitted": submitted_this_run,
        }

    def _candidate_snapshot(self, pool: list[Candidate], *, limit: int | None = None, retained: bool = True) -> list[dict]:
        limit = self.config.budget.retained_alpha_pool_size if limit is None else max(0, int(limit))
        return [
            {
                **candidate.to_dict(),
                "pool_rank": index,
                "in_retained_pool": retained,
                "smart_rank_score": self._smart_ranking_score(candidate),
                "cloud_correlation_risk": self._cloud_correlation_risk(candidate),
            }
            for index, candidate in enumerate(self._smart_rank_candidates(pool)[:limit], start=1)
        ]

    def _archive(
        self,
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        candidates: list[Candidate],
    ):
        for candidate in candidates:
            status = candidate.gate.get("status") or candidate.lifecycle_status or "ARCHIVED"
            if status in {
                "LOCAL_PREFILTER_REJECTED",
                "LOCAL_STANDARD_REJECTED",
                "CANDIDATE_POOL_PRUNED",
                "DUPLICATE_EXPRESSION_SKIPPED",
                "PREVIOUSLY_REJECTED_EXPRESSION_SKIPPED",
            }:
                continue
            archive_stats[status] = archive_stats.get(status, 0) + 1
            if len(archive_samples) < 25 and candidate.official_metrics:
                archive_samples.append(candidate)

    def _refresh_cloud_similarity_index(self) -> None:
        rows: list[dict[str, object]] = []
        for row in self.cloud_alphas:
            expr = _cloud_row_expression(row)
            norm = normalize(expr)
            rows.append(
                {
                    "id": str(row.get("id") or row.get("alpha_id") or ""),
                    "status": str(row.get("status", "")),
                    "expression": expr,
                    "norm": norm,
                    "tokens": set(norm.split()) if norm else set(),
                }
            )
        self._cloud_similarity_rows = rows
        self._cloud_risk_cache.clear()

    def _cloud_correlation_risk(self, candidate: Candidate) -> dict:
        if not self.cloud_alphas:
            return {"level": "unknown", "max_similarity": 0.0, "matched_alpha_id": "", "note": "cloud alpha sync unavailable"}
        official_alpha_id = candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
        if not self._cloud_similarity_rows:
            self._refresh_cloud_similarity_index()
        cache_key = (candidate.expression, official_alpha_id, len(self._cloud_similarity_rows))
        cached = self._cloud_risk_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        candidate_norm = normalize(candidate.expression)
        candidate_tokens = set(candidate_norm.split()) if candidate_norm else set()
        best = {"score": 0.0, "id": "", "status": ""}
        top_matches: list[tuple[float, dict[str, object]]] = []
        for row in self._cloud_similarity_rows:
            row_id = str(row.get("id") or "")
            if official_alpha_id and row_id == official_alpha_id:
                continue
            row_tokens = row.get("tokens") or set()
            union = candidate_tokens | row_tokens
            score = (len(candidate_tokens & row_tokens) / len(union)) if union else 0.0
            if score > best["score"]:
                best = {"score": round(score, 4), "id": row_id, "status": str(row.get("status", ""))}
            if score > 0.0:
                top_matches.append((score, row))
                if len(top_matches) > 25:
                    top_matches.sort(key=lambda item: item[0], reverse=True)
                    del top_matches[25:]
        for token_score, row in sorted(top_matches, key=lambda item: item[0], reverse=True):
            ast_score = expression_similarity(candidate.expression, str(row.get("expression") or ""))
            score = round(max(token_score, ast_score), 4)
            if score > best["score"]:
                best = {"score": score, "id": str(row.get("id") or ""), "status": str(row.get("status", ""))}
        level = "high" if best["score"] >= 0.90 else "medium" if best["score"] >= 0.75 else "low"
        result = {
            "level": level,
            "max_similarity": best["score"],
            "matched_alpha_id": best["id"],
            "matched_status": best["status"],
            "note": "用于避免自相关/重复提交，不用于绕过合规限制",
        }
        self._cloud_risk_cache[cache_key] = dict(result)
        return result

    def _cloud_status_for_candidate(self, candidate: Candidate) -> dict:
        official_alpha_id = candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
        candidate_expr_key = _expr_key(candidate)
        for row in self.cloud_alphas:
            row_id = str(row.get("id") or row.get("alpha_id") or "")
            if official_alpha_id and row_id == official_alpha_id:
                return {"id": row_id, "status": str(row.get("status", "")), "match": "official_id"}
        for row in self.cloud_alphas:
            row_expression = expression_key(_cloud_row_expression(row))
            if candidate_expr_key and row_expression == candidate_expr_key:
                return {"id": str(row.get("id") or row.get("alpha_id") or ""), "status": str(row.get("status", "")), "match": "expression"}
        return {"id": "", "status": "", "match": "none"}

    def _remember_accepted(self, accepted_candidates: list[Candidate], candidate: Candidate):
        key = _expr_key(candidate)
        if any(_expr_key(item) == key for item in accepted_candidates):
            return
        candidate.lifecycle_status = "submission_ready"
        accepted_candidates.append(candidate)
        accepted_candidates.sort(key=_ranking_score, reverse=True)
        del accepted_candidates[50:]

    def _smart_rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                bool(candidate.gate.get("submission_ready")),
                bool(candidate.official_metrics),
                self._smart_ranking_score(candidate),
                candidate.scorecard.get("local_rank_score", 0.0),
                candidate.local_quality.get("score", 0.0),
            ),
            reverse=True,
        )

    def _smart_ranking_score(self, candidate: Candidate) -> float:
        score = _ranking_score(candidate)
        risk = self._cloud_correlation_risk(candidate)
        if risk.get("level") == "high":
            score -= 30.0
        elif risk.get("level") == "medium":
            score -= 10.0
        return round(score, 2)

    def _slot_snapshot(self) -> list[dict]:
        active_limit = self._active_backtest_limit()
        rows = []
        for slot in range(1, active_limit + 1):
            candidate = self.backtest_slot_manager.get(slot)
            if not candidate:
                status = "CAPACITY_WAIT" if self.official_calls_halted else "EMPTY"
                rows.append(
                    {
                        "slot": slot,
                        "alpha_id": "",
                        "simulation_id": "",
                        "status": status,
                        "official_alpha_id": "",
                        "score": 0.0,
                        "poll_count": 0,
                        "progress_percent": 0,
                        "next_poll_seconds": 0,
                        "message": (
                            f"官方调用暂停：{self.official_halt_reason}"
                            if self.official_calls_halted
                            else "等待候选补位"
                        ),
                    }
                )
                continue
            status = candidate.submission.get("simulation_status") or candidate.lifecycle_status
            next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
            rows.append(
                {
                    "slot": slot,
                    "alpha_id": candidate.alpha_id,
                    "simulation_id": candidate.simulation_id,
                    "status": status,
                    "lifecycle_status": candidate.lifecycle_status,
                    "official_alpha_id": candidate.official_alpha_id,
                    "score": candidate.scorecard.get("total_score", 0.0),
                    "family": candidate.family,
                    "hypothesis": candidate.hypothesis,
                    "expression": candidate.expression,
                    "scorecard": candidate.scorecard,
                    "local_quality": candidate.local_quality,
                    "validation": candidate.validation,
                    "official_metrics": candidate.official_metrics,
                    "gate": candidate.gate,
                    "cloud_correlation_risk": self._cloud_correlation_risk(candidate),
                    "poll_count": candidate.submission.get("poll_count", 0),
                    "progress_percent": _slot_progress_percent(status),
                    "next_poll_seconds": round(max(0.0, next_poll_at - time.monotonic()), 1),
                    "message": _slot_message(status),
                }
            )
        return rows

    def _active_backtest_limit(self) -> int:
        return min(
            max(1, int(self.config.budget.official_backtest_batch_size)),
            max(1, int(self.config.budget.max_official_simulations_per_cycle)),
            max(1, int(self.config.budget.max_official_concurrent_simulations)),
        )

    def _backtest_snapshot(self, candidates: list[Candidate]) -> list[dict]:
        return [
            {
                "alpha_id": candidate.alpha_id,
                "simulation_id": candidate.simulation_id,
                "status": candidate.submission.get("simulation_status") or candidate.lifecycle_status,
                "official_alpha_id": candidate.official_alpha_id,
                "score": candidate.scorecard.get("total_score", 0.0),
            }
            for candidate in candidates
        ]

    def _should_stop(self) -> bool:
        return bool(self.stop_callback and self.stop_callback())

    def _sleep_with_stop(self, seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, float(seconds or 0.0))
        while time.monotonic() < deadline:
            if self._should_stop():
                return False
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
        return not self._should_stop()

    def _event(
        self,
        event: str,
        message: str,
        alpha_id: str = "",
        data: dict | None = None,
        level: str = "INFO",
    ):
        event_data = {
            **context_payload(run_id=self.run_id, alpha_id=alpha_id, event=event),
            **dict(data or {}),
        }
        self.events.append(PipelineEvent(event=event, message=message, alpha_id=alpha_id, level=level, data=event_data))

    def _progress(
        self,
        phase: str,
        current: int,
        total: int,
        message: str,
        alpha_id: str = "",
        data: dict | None = None,
    ):
        total = max(1, int(total or 1))
        current = max(0, min(int(current or 0), total))
        percent = round(current / total * 100, 1)
        if self.config.budget.run_forever and phase not in {"completed", "stopped", "failed"}:
            percent = min(percent, 99.0)
        payload_data = {**self.last_runtime_data, **dict(data or {})}
        if payload_data:
            self.last_runtime_data = dict(payload_data)
        if "backtests" in payload_data:
            self.last_backtests = list(payload_data.get("backtests") or [])
        elif self.last_backtests:
            payload_data["backtests"] = self.last_backtests
        payload = {
            "phase": phase,
            "current": current,
            "total": total,
            "percent": percent,
            "message": message,
            "alpha_id": alpha_id,
            "run_id": self.run_id,
            "continuous": self.config.budget.run_forever,
            "data": payload_data,
        }
        if self.progress_callback:
            self.progress_callback(payload)


def rank_candidates(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda c: (
            bool(c.gate.get("submission_ready")),
            bool(c.official_metrics),
            _ranking_score(c),
            c.scorecard.get("local_rank_score", 0.0),
            c.local_quality.get("score", 0.0),
        ),
        reverse=True,
    )


def _ranking_score(candidate: Candidate) -> float:
    return float(candidate.scorecard.get("total_score", 0.0) or 0.0)


def _assistant_guidance_for_generator(guidance: dict) -> dict:
    if not guidance or guidance.get("ok") is False:
        return {}
    if not _truthy(guidance.get("usable", True)):
        return {}
    top_operators = _unique_strings(guidance.get("top_operators"))
    preferred_windows = _unique_numbers(guidance.get("preferred_windows"))
    field_combinations = _field_combinations(guidance.get("field_combinations"))
    top_fields = _unique_strings(guidance.get("top_fields"))
    if top_fields:
        field_combinations = _unique_field_combinations(
            field_combinations + [{"fields": top_fields, "rationale": "assistant top fields"}]
        )
    if not top_operators and not preferred_windows and not field_combinations:
        return {}
    return {
        "sample_size": max(3, _safe_int(guidance.get("sample_size"), 0)),
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "field_combinations": field_combinations,
    }


def _attach_assistant_guidance(candidate: Candidate, guidance: dict) -> None:
    guidance = ensure_assistant_guidance_digest(guidance)
    digest = str(guidance.get("guidance_digest") or "")
    tags = list(candidate.source_tags or [])
    for tag in ("assistant_guided", f"assistant_guidance_{digest}"):
        if tag and tag not in tags:
            tags.append(tag)
    candidate.source_tags = tags
    submission = dict(candidate.submission or {})
    submission.update(assistant_guidance_candidate_metadata(guidance))
    candidate.submission = submission


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _string_items(value) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _unique_strings(value) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in _string_items(value):
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _number_items(value) -> list[int | float]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    rows: list[int | float] = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number != number or number in (float("inf"), float("-inf")):
            continue
        rows.append(int(number) if number.is_integer() else number)
    return rows


def _unique_numbers(value) -> list[int | float]:
    seen: set[float] = set()
    unique: list[int | float] = []
    for item in _number_items(value):
        marker = float(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _field_combinations(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            fields = _unique_strings(item.get("fields") or item.get("field") or item.get("value"))
            rationale = str(item.get("rationale") or "")
        else:
            fields = _unique_strings(item)
            rationale = ""
        if fields:
            rows.append({"fields": fields, "rationale": rationale})
    return rows


def _unique_field_combinations(value) -> list[dict]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict] = []
    for combo in _field_combinations(value):
        fields = _unique_strings(combo.get("fields"))
        marker = tuple(field.lower() for field in fields)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append({"fields": fields, "rationale": str(combo.get("rationale") or "")})
    return unique


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_hard_backtest_blocked(status: str) -> bool:
    text = str(status or "").lower()
    if "simulation_deferred_concurrency_limit" in text or "simulation_deferred_rate_limit" in text:
        return False
    return any(
        marker in text
        for marker in (
            "official_validation_failed",
            "observability_duplicate_blocked",
            "local_standard_rejected",
            "official_standard_rejected",
            "simulation_request_failed",
            "simulation_poll_failed",
            "simulation_result_failed",
            "simulation_failed",
            "simulation_timeout",
            "rejected",
        )
    )


def _merge_context_defaults(items: list[dict], defaults: list[dict]) -> list[dict]:
    merged = list(items)
    seen = {str(item.get("name", "")).lower() for item in merged if item.get("name")}
    for item in defaults:
        name = str(item.get("name", "")).lower()
        if name and name not in seen:
            merged.append(dict(item))
            seen.add(name)
    return merged


def _expr_key(candidate: Candidate) -> str:
    return expression_key(candidate.expression)


def _cloud_row_expression(row: dict) -> str:
    expression = row.get("expression", "")
    if isinstance(expression, dict):
        code = expression.get("code") or expression.get("regular")
        if code:
            return str(code)
    regular = row.get("regular")
    if isinstance(regular, dict) and regular.get("code"):
        return str(regular.get("code"))
    raw = row.get("raw")
    if isinstance(raw, dict):
        raw_regular = raw.get("regular")
        if isinstance(raw_regular, dict) and raw_regular.get("code"):
            return str(raw_regular.get("code"))
    return str(expression or "")


def _blocked_gate(status: str, reasons: list[str]) -> dict:
    return {
        "schema_version": "production-gate-v2.1",
        "submission_ready": False,
        "status": status,
        "failed_reasons": list(reasons),
        "warnings": [],
    }


def _slot_progress_percent(status: str) -> int:
    value = str(status or "").upper()
    if value == "EMPTY":
        return 0
    if value == "CAPACITY_WAIT":
        return 5
    if value in {"SUBMITTED", "SIMULATION_SUBMITTED"}:
        return 25
    if value in {"RUNNING", "SIMULATION_RUNNING"}:
        return 65
    if value in {"COMPLETED", "OFFICIAL_SIMULATED", "SUBMISSION_READY"}:
        return 100
    if "DEFERRED" in value:
        return 40
    if "FAILED" in value or "REJECTED" in value:
        return 100
    return 50


def _slot_message(status: str) -> str:
    value = str(status or "").upper()
    if value == "CAPACITY_WAIT":
        return "官方并发容量占满，暂缓提交新回测。"
    if value == "EMPTY":
        return "等待排名靠前的候选 Alpha。"
    if value in {"SUBMITTED", "SIMULATION_SUBMITTED"}:
        return "已提交，等待官方开始计算。"
    if value in {"RUNNING", "SIMULATION_RUNNING"}:
        return "官方回测运行中，按 6 秒节奏顺序轮询。"
    if value in {"COMPLETED", "OFFICIAL_SIMULATED", "SUBMISSION_READY"}:
        return "回测完成，结果已进入评价/排序。"
    if "DEFERRED" in value:
        return "官方限流或并发限制，保持本地生产并稍后恢复。"
    if "FAILED" in value:
        return "未达标，已进入生命周期回溯。"
    if "REJECTED" in value:
        return "未通过官方/本地门禁，已记录原因。"
    return "状态更新中。"


# ═══════════════════════════════════════════════════════════════════════
# P2-8: CLI summary helpers
# ═══════════════════════════════════════════════════════════════════════
def _compute_score_distribution(candidates: list) -> dict:
    """Compute score band distribution for display."""
    from collections import Counter
    dist = Counter()
    for c in candidates:
        s = c.scorecard.get("total_score", 0.0)
        if s >= 85:    dist["submit (≥85)"] += 1
        elif s >= 70:  dist["optimize (70-84)"] += 1
        elif s >= 50:  dist["research (50-69)"] += 1
        else:          dist["abandon (<50)"] += 1
    return dict(dist)


def _compute_gate_summary(candidates: list) -> dict:
    """Compute gate pass/fail/block summary for display."""
    result = {"local_prefilter": {"pass": 0, "fail": 0, "block": 0},
              "expression_validate": {"pass": 0, "fail": 0, "block": 0},
              "official_simulation": {"pass": 0, "fail": 0, "block": 0},
              "quality_gate": {"pass": 0, "fail": 0, "block": 0}}
    for c in candidates:
        if c.lifecycle_status == "local_prefilter_rejected":
            result["local_prefilter"]["fail"] += 1
        elif c.lifecycle_status in ("validation_rejected", "expression_invalid"):
            result["expression_validate"]["fail"] += 1
        elif c.lifecycle_status in ("simulation_failed", "simulation_rejected"):
            result["official_simulation"]["fail"] += 1
        elif c.gate.get("submission_ready"):
            result["quality_gate"]["pass"] += 1
        elif c.gate.get("hard_gate_blocked"):
            result["quality_gate"]["block"] += 1
        elif c.official_metrics:
            result["quality_gate"]["fail"] += 1
    return result
