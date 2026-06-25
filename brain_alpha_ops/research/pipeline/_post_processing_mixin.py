"""Post-processing phase mixin for ``AlphaResearchPipeline``.

Extracted from the original ``pipeline.py`` monolith. Handles convergence
tracking, auto-calibration, and fusion triggers at the end of each cycle.
"""

from __future__ import annotations

import logging

from brain_alpha_ops.redaction import redact_error_message

from ..pipeline_state import record_strategy_reward

# Preserve the original ``brain_alpha_ops.research.pipeline`` logger name so
# downstream log filters and test caplog assertions keep working after the
# monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline")

CONVERGENCE_REPORT_INTERVAL = 10


class PipelinePostProcessingMixin:
    """Post-processing phase: convergence, calibration, fusion, progress."""

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
        """Post-processing: convergence tracking, calibration, fusion, progress.

        Extracted from run() to reduce method length (B-03).
        Called at the end of each cycle.
        """
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
