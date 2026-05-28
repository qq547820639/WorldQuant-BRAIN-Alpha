"""Service factories for AlphaResearchPipeline."""

from __future__ import annotations

import logging

from .backtest_finalization import BacktestFinalizationService
from .backtest_polling import BacktestPollingService
from .backtest_submission import BacktestSubmissionService
from .batch_backtest_coordinator import BatchBacktestCoordinator
from .candidate_pool import CandidatePoolService
from .dataset_selection import DatasetSelectionService
from .experience_feedback import ExperienceFeedbackService
from .fusion_candidates import FusionCandidateService
from .generation_phase import GenerationPhaseService
from .official_workflow import OfficialWorkflowService
from .pipeline_helpers import attach_assistant_guidance as _attach_assistant_guidance
from .pipeline_helpers import expr_key as _expr_key, rank_candidates
from .secondary_fusion import SecondaryFusionService

logger = logging.getLogger(__name__)


class PipelineServiceFactoryMixin:
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
            max_expression_similarity=self.config.submission_policy.max_expression_similarity,
        )

    def _dataset_selection_service(self) -> DatasetSelectionService:
        return DatasetSelectionService(
            selector=self._selector,
            loader=self._loader,
            generator=self.generator,
            settings=self.config.settings,
            strategy=getattr(self.config.budget, "dataset_strategy", "rotate"),
            allow_datasetless=bool(self.context_summary.get("fields_count", 0) or self.context_summary.get("operators_count", 0)),
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
