"""Inner cycle machinery for ``AlphaResearchPipeline``.

Consolidated from the original ``pipeline.py`` monolith's split files
(``_main_loop_mixin`` / ``_post_processing_mixin`` / ``_cycle_mixin``).
All per-cycle mechanics now live in ``PipelineMainLoopMixin``.

Thin adapter pattern (post-refactor):
  - ``PipelinePostProcessingMixin`` and ``PipelineCycleMixin`` are kept
    as empty subclasses for backward-compatible imports but contribute
    no additional methods.
  - ``_try_fusion_top_candidates`` is provided as a thin adapter
    that delegates to ``self.services.fusion_candidates``, eliminating
    the need for ``PipelineBacktestMixin`` in the MRO.
"""

from __future__ import annotations

import logging
import time

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from ..guidance import ensure_assistant_guidance_digest
from ..memory import ResearchMemory
from ..pipeline_helpers import (
    attach_assistant_guidance as _attach_assistant_guidance,
    assistant_guidance_for_generator as _assistant_guidance_for_generator,
    rank_candidates,
)
from ..pipeline_state import CycleState, record_strategy_reward
from ..research_cycle_orchestrator import ResearchCycleOrchestrator
# Import the module (not the function) so test monkeypatching of
# ``brain_alpha_ops.research.pipeline_submission_gate.live_submit_readiness_hard_gate``
# takes effect at call time.
from .. import pipeline_submission_gate

# Preserve the original ``brain_alpha_ops.research.pipeline`` logger name so
# downstream log filters and test caplog assertions keep working after the
# monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline")

CONTEXT_REFRESH_INTERVAL_SECONDS = 86400
CONVERGENCE_REPORT_INTERVAL = 10


class PipelineMainLoopMixin:
    """Consolidated per-cycle machinery for ``AlphaResearchPipeline``.

    Contains the main loop body, post-cycle convergence/calibration/fusion,
    dataset selection, assistant guidance, and simulation+backtest phases.
    Previously split across three mixins; merged to reduce MRO count.
    """

    # ── Main loop ──────────────────────────────────────────────────────

    def _run_main_loop(
        self,
        *,
        state: CycleState,
        fields: list[dict],
        operators: list[dict],
        auto_submit: bool,
        cycle_orchestrator: ResearchCycleOrchestrator,
        pipeline_start_time: float,
        max_cycle_runtime: int,
        max_pipeline_runtime: int,
        submitted_this_run: int,
    ) -> tuple[int, list[dict], list[dict], CycleState]:
        """Execute the main research loop.

        Returns (submitted_this_run, fields, operators, state).
        """
        pool_by_expression = state.pool_by_expression
        blocked_expressions = state.blocked_expressions
        archive_stats = state.archive_stats
        archive_samples = state.archive_samples
        accepted_candidates = state.accepted_candidates

        while True:
            _cycle_t0 = time.time()

            # Per-cycle timeout enforcement
            _pipeline_elapsed = time.time() - pipeline_start_time
            if _pipeline_elapsed > max_pipeline_runtime:
                logger.warning(
                    'pipeline MAX RUNTIME exceeded: %.1fs > %ds limit',
                    _pipeline_elapsed, max_pipeline_runtime,
                )
                self.services.runtime._event('pipeline_timeout',
                    f'Pipeline max runtime {max_pipeline_runtime}s exceeded after {_pipeline_elapsed:.0f}s.',
                    level='WARN')
                break

            cycle_decision = cycle_orchestrator.next_cycle()
            if not cycle_decision.should_run:
                logger.info('pipeline cycle stop: %s', cycle_decision.reason)
                break
            cycle = cycle_decision.cycle
            self.cycles_since_strategy_switch += 1
            logger.info('pipeline cycle %d start — elapsed=%.1fs, timeout=%ds',
                        cycle, _pipeline_elapsed, max_cycle_runtime)

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
            self.services.runtime._refresh_observability_throttle(cycle)

            # ── P2-5: Periodic context refresh (every ~24h / 50 cycles) ──
            if self._loader and (cycle == 1 or (cycle % 50 == 0) or
                                (time.time() - self._last_context_refresh > CONTEXT_REFRESH_INTERVAL_SECONDS)):
                try:
                    refresh_result = self._loader.refresh()
                    self._last_context_refresh = time.time()
                    if refresh_result.get("status") == "refreshed":
                        f_delta = refresh_result.get("fields_delta", 0)
                        o_delta = refresh_result.get("operators_delta", 0)
                        if f_delta or o_delta:
                            self.services.runtime._event("context_refreshed",
                                f"Cycle {cycle}: Context refreshed — fields {f_delta:+d}, "
                                f"operators {o_delta:+d}")
                            # Update generator context with refreshed data
                            fields, operators = self.services.context_sync._load_official_context()
                    elif refresh_result.get("status") == "refresh_failed":
                        # P1-4: Alert on context refresh failure
                        error_detail = refresh_result.get("error", "unknown")
                        self.services.runtime._event("context_refresh_failed",
                            f"Cycle {cycle}: Context refresh FAILED — {error_detail}",
                            level="ERROR")
                except Exception as exc:
                    message = redact_error_message(exc)
                    logger.warning("Context refresh exception in cycle %s: %s", cycle, message)
                    logger.debug("Context refresh exception traceback in cycle %s", cycle, exc_info=True)
                    self.services.runtime._event("context_refresh_error",
                        f"Cycle {cycle}: Context refresh exception — {message}",
                        level="ERROR")
            generated = self._generation_phase_service().generate(
                assistant_guidance=assistant_guidance if assistant_guidance_applied else None,
            )
            self.produced_count += len(generated)
            for candidate in generated:
                self.services.runtime._record_lifecycle(candidate, "generated", "本地生成")
            self.services.runtime._event("candidates_generated", f"Cycle {cycle}: generated {len(generated)} candidates.")
            self.services.runtime._progress(
                "production_loop",
                0 if self.config.budget.run_forever else cycle - 1,
                1 if self.config.budget.run_forever else self.config.budget.max_cycles,
                f"第 {cycle} 轮：生产 {len(generated)} 个 Alpha，进入本地评分与排序。",
                data={"cycle": cycle, "produced_count": self.produced_count},
            )

            locally_passed = self.services.candidate_pool._local_prefilter(generated, cycle, fields, operators)
            self.services.runtime._archive(
                archive_stats,
                archive_samples,
                [
                    candidate
                    for candidate in generated
                    if candidate.lifecycle_status == "local_prefilter_rejected"
                ],
            )

            self.services.runtime._archive(archive_stats, archive_samples, self.services.candidate_pool._merge_into_pool(pool_by_expression, locally_passed, blocked_expressions))
            self.services.runtime._archive(archive_stats, archive_samples, self.services.candidate_pool._remove_below_local_standard(pool_by_expression))
            self.services.runtime._archive(archive_stats, archive_samples, self.services.candidate_pool._prune_pool(pool_by_expression))
            pool = rank_candidates(list(pool_by_expression.values()))
            self.services.runtime._progress(
                "candidate_pool",
                len(pool),
                self.config.budget.retained_alpha_pool_size,
                f"候选池已按本地分排序，保留 {len(pool)}/{self.config.budget.retained_alpha_pool_size} 个 Alpha。",
                data=self._runtime_data(cycle, pool, accepted_candidates, archive_stats),
            )

            # ── P2-05: Single official_calls_halted gate moved into _cycle_simulate_and_submit ──
            self.services.runtime._refresh_observability_throttle(cycle)

            validation_targets = []
            if not self.official_calls_halted:
                validation_targets = self.services.official_validation._filter_observability_duplicate_targets(
                    self.services.candidate_pool._validation_targets(pool),
                    phase="official_validation",
                )
            self.services.runtime._archive(
                archive_stats,
                archive_samples,
                self.services.official_validation._archive_validation_failures(pool_by_expression, pool, blocked_expressions),
            )
            pool = rank_candidates(list(pool_by_expression.values()))
            validation_quota = 0 if self.official_calls_halted else self.services.candidate_pool._validation_quota(pool)
            if self.official_calls_halted:
                validation_quota = 0
            elif validation_quota > 0:
                self.services.official_validation._validate(validation_targets[:validation_quota])
            pool = rank_candidates(list(pool_by_expression.values()))
            self.services.runtime._archive(
                archive_stats,
                archive_samples,
                self.services.official_validation._archive_validation_failures(pool_by_expression, pool, blocked_expressions),
            )
            self.services.runtime._archive(
                archive_stats,
                archive_samples,
                self.services.official_validation._archive_validation_failures(pool_by_expression, validation_targets, blocked_expressions),
            )

            pool = rank_candidates(list(pool_by_expression.values()))
            self.services.candidate_pool._top_up_candidate_pool(
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

            # ── Phase 3: Simulation + Backtest + Strategy (gate guard inside) ──
            submitted_this_run, abort = self._cycle_simulate_and_submit(
                cycle, pool_by_expression, blocked_expressions,
                archive_stats, archive_samples, accepted_candidates,
                submitted_this_run, auto_submit,
            )
            if abort is True:
                break
            elif abort is False:
                continue

            # Top-up pool after simulation
            self.services.candidate_pool._top_up_candidate_pool(
                cycle,
                pool_by_expression,
                blocked_expressions,
                archive_stats,
                archive_samples,
                fields,
                operators,
                accepted_candidates,
            )
            fields, operators = self.services.strategy._maybe_switch_strategy(
                cycle,
                fields,
                operators,
                pool_by_expression,
                accepted_candidates,
                archive_stats,
            )

            self.services.runtime._event(
                "cycle_completed",
                f"Cycle {cycle} completed with {len(pool_by_expression)} retained candidates.",
                data={"cycle": cycle, "pool_size": len(pool_by_expression)},
            )

            # ── B-03: Post-processing (convergence, calibration, fusion, progress) ──
            archive_stats, _ = self._run_cycle_post_processing(
                cycle, pool_by_expression, pool, generated, locally_passed,
                accepted_candidates, archive_stats, submitted_this_run,
            )

            self.services.runtime._progress(
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
            if self.config.budget.run_forever and not self.services.runtime._sleep_with_stop(self.config.budget.cycle_pause_seconds):
                break

        return submitted_this_run, fields, operators, state

    # ── Post-processing (was PipelinePostProcessingMixin) ──────────────

    def _run_cycle_post_processing(
        self,
        cycle: int,
        pool_by_expression: dict,
        pool: list,
        generated: list,
        locally_passed: list,
        accepted_candidates: list,
        archive_stats: dict,
        submitted_this_run: int,
    ) -> tuple[dict, list]:
        """Post-processing: convergence tracking, calibration, fusion, progress."""
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
            self.services.strategy._current_strategy_profile(),
            index=idx,
            cycle=cycle,
            reward=reward_snapshot.reward,
            metrics=reward_snapshot.metrics,
        )

        conv_summary = self.convergence.summary()

        # ── P2-2: Output convergence report every 10 cycles ──
        if cycle > 0 and cycle % CONVERGENCE_REPORT_INTERVAL == 0:
            conv = conv_summary
            self.services.runtime._event(
                "convergence_report",
                f"Cycle {cycle} convergence: {conv['sharpe_trend']}, "
                f"avg Sharpe={conv['recent_avg_sharpe']:.3f}, "
                f"stalled={conv['stalled']}",
                data={"convergence": conv},
            )
            if conv["stalled"]:
                self.services.runtime._event(
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
                    self.services.runtime._event(
                        "scoring_calibrated",
                        calib_report.get("summary", "Scoring parameters calibrated."),
                        data=calib_report,
                    )
            except Exception as exc:
                message = redact_error_message(exc)
                logger.warning("Scoring auto-calibration failed in cycle %s: %s", cycle, message)
                logger.debug("Scoring auto-calibration traceback in cycle %s", cycle, exc_info=True)
                self.services.runtime._event(
                    "scoring_calibration_failed",
                    f"Auto-calibration failed: {message}",
                    level="WARN",
                )

        # ── P0-3: Fusion trigger when convergence stalls ──
        if (
            cycle > 0
            and self.config.budget.enable_secondary_fusion
            and conv_summary.get("stalled")
            and conv_summary.get("stall_cycles", 0) >= 3
        ):
            try:
                self._try_fusion_top_candidates(
                    pool_by_expression,
                    blocked_expressions=None,
                    cycle=cycle,
                )
            except Exception as exc:
                message = redact_error_message(exc)
                logger.warning(
                    "Secondary fusion attempt failed in cycle %s: %s",
                    cycle,
                    message,
                )
                logger.debug("Secondary fusion traceback in cycle %s", cycle, exc_info=True)
                self.services.runtime._event(
                    "fusion_attempt_failed",
                    f"Fusion attempt during convergence stall failed: {message}",
                    level="WARN",
                )

        return archive_stats, pool

    # ── Thin adapter for fusion (was PipelineBacktestMixin) ────────────
    #  This adapter delegates to FusionCandidateService via the composition
    #  container, eliminating the need for PipelineBacktestMixin in the MRO.

    def _try_fusion_top_candidates(
        self,
        pool_by_expression: dict,
        blocked_expressions: set | None,
        cycle: int,
    ) -> int:
        """Thin adapter delegating fusion to ``self.services.fusion_candidates``."""
        outcome = self.services.fusion_candidates.create_top_candidate_fusions(
            pool_by_expression,
            blocked_expressions or set(),
            cycle=cycle,
        )
        return outcome.created_count

    # ── Per-cycle phases (was PipelineCycleMixin) ──────────────────────

    def _cycle_select_dataset(self, cycle: int) -> "_Phase":
        """Select dataset for this cycle. Returns _Phase.SKIP or _Phase.BREAK on failure."""
        result = self._dataset_selection_service().select()
        if result.dataset_id:
            self._active_dataset_id = result.dataset_id
            # Item 7: Log warning when dataset changes (universe switch)
            if self._active_dataset_id and self._active_dataset_id != getattr(self, "_last_dataset_id", ""):
                if hasattr(self, "_last_dataset_id") and self._last_dataset_id:
                    logger.info(
                        "universe switch detected: %s -> %s (same expressions across universes "
                        "will be re-evaluated; verify this is intentional)",
                        self._last_dataset_id, self._active_dataset_id,
                    )
                self._last_dataset_id = self._active_dataset_id
        if result.should_continue:
            return self._Phase.CONTINUE
        if result.should_skip:
            return self._Phase.SKIP
        return self._Phase.BREAK

    def _apply_assistant_guidance(self, cycle: int) -> dict | None:
        self._active_assistant_guidance = None
        if not getattr(self.config.budget, "use_assistant_guidance", True):
            return None

        # P2-4: return cached guidance for up to 5 cycles to avoid
        # re-reading the JSONL file on every single cycle.
        if (self._cached_assistant_guidance is not None
                and cycle - self._cached_guidance_at_cycle < 5):
            return self._cached_assistant_guidance

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
            self._active_assistant_guidance = guidance
            self.services.runtime._event(
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
            self._cached_assistant_guidance = guidance
            self._cached_guidance_at_cycle = cycle
            return guidance
        except Exception as exc:
            # P2-4: invalidate cache on exception so the next cycle re-reads
            self._cached_assistant_guidance = None
            logger.warning("Assistant guidance unavailable in cycle %s: %s", cycle, redact_error_message(exc))
            logger.debug("Assistant guidance traceback in cycle %s", cycle, exc_info=True)
        return None

    def _attach_active_assistant_guidance(self, candidates: list[Candidate]) -> None:
        guidance = self._active_assistant_guidance
        if not guidance:
            return
        for candidate in candidates:
            _attach_assistant_guidance(candidate, guidance)

    def _live_submit_readiness_gate(self, candidate: Candidate) -> dict:
        return pipeline_submission_gate.live_submit_readiness_hard_gate(
            candidate.to_dict(),
            RunConfig(ops=self.config),
            candidate.official_alpha_id,
        )

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
    ) -> tuple[int, bool | None]:
        """Execute the simulation+backtest+strategy phase for one cycle.

        Returns (submitted_this_run, abort) where:
          abort=True  → caller should break
          abort=False → caller should continue
          abort=None  → normal flow, caller should proceed
        """
        # ── Gate guard: consolidated official_calls_halted check (P2-05) ──
        if self.official_calls_halted and self.official_halt_cycle != cycle:
            self.services.runtime._maybe_resume_official_calls()
        if self.official_calls_halted:
            pool = rank_candidates(list(pool_by_expression.values()))
            if not self.services.runtime._defer_official_cycle(cycle, pool, accepted_candidates, archive_stats):
                return submitted_this_run, True   # break
            return submitted_this_run, False       # continue

        # Poll existing backtests
        submitted_this_run = self.services.backtest_flow._poll_due_backtests(
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

        self.services.runtime._archive(archive_stats, archive_samples, self.services.candidate_pool._prune_pool(pool_by_expression))
        return submitted_this_run, None


# ── Backward-compatible empty shells ───────────────────────────────────
# Kept so that tests and sibling modules that import these class names
# do not break.  The classes contribute zero additional methods to the
# MRO — all logic lives in PipelineMainLoopMixin.

class PipelinePostProcessingMixin(PipelineMainLoopMixin):
    """Backward-compatible shell — logic merged into PipelineMainLoopMixin."""
    pass


class PipelineCycleMixin(PipelineMainLoopMixin):
    """Backward-compatible shell — logic merged into PipelineMainLoopMixin."""
    pass
