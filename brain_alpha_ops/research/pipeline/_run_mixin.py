"""Run entry-point mixin for ``AlphaResearchPipeline``.

Extracted from the original ``pipeline.py`` monolith. Contains the
top-level ``run()`` method that orchestrates auth → context load →
production context → main loop → persist.
"""

from __future__ import annotations

import logging
import time

from brain_alpha_ops.models import PipelineResult, new_id
from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot
from brain_alpha_ops.redaction import redact_error_message

from ..pipeline_helpers import rank_candidates
from ..pipeline_state import CycleState
from ..production_context import build_production_context
from ..research_cycle_orchestrator import ResearchCycleOrchestrator

# Preserve the original ``brain_alpha_ops.research.pipeline`` logger name so
# downstream log filters and test caplog assertions keep working after the
# monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline")


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
            logger.warning("failed to persist run history for %s: %s", run_id, redact_error_message(exc))
            logger.debug("run history persistence traceback for %s", run_id, exc_info=True)

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
