"""Main loop mixin for ``AlphaResearchPipeline``.

Extracted from the original ``pipeline.py`` monolith. Contains the
``_run_main_loop`` method that drives per-cycle dataset selection,
generation, filtering, simulation, and post-processing.
"""

from __future__ import annotations

import logging
import time

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from ..pipeline_helpers import rank_candidates
from ..pipeline_state import CycleState
from ..research_cycle_orchestrator import ResearchCycleOrchestrator

# Preserve the original ``brain_alpha_ops.research.pipeline`` logger name so
# downstream log filters and test caplog assertions keep working after the
# monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline")

CONTEXT_REFRESH_INTERVAL_SECONDS = 86400


class PipelineMainLoopMixin:
    """Main research loop body extracted from ``run()``."""

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
