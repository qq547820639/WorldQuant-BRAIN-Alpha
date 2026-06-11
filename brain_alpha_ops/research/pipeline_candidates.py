"""Candidate scoring, pool, and cloud-risk helpers for AlphaResearchPipeline."""

from __future__ import annotations

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .batch_backtest_coordinator import (
    _cloud_similarity_details,
    _is_high_cloud_similarity,
    _reject_high_cloud_similarity_candidate,
)
from .candidate_pool import is_active_backtest_candidate, pending_simulation_targets
from .generator import extract_fields, extract_operators, local_quality
from .field_quality import non_signal_generation_fields
from .knowledge_base import KnowledgeEntry
from .local_backtest_gate import apply_local_backtest_gate
from .pipeline_cloud import (
    build_cloud_similarity_rows,
    cloud_correlation_risk,
    cloud_status_for_candidate,
    remember_accepted,
    smart_rank_candidates,
    smart_ranking_score,
)
from .pipeline_helpers import blocked_gate as _blocked_gate, expr_key as _expr_key, rank_candidates
from .pipeline_official_context import active_dataset_field_names, official_context_reasons, refresh_context_validation_cache
from .scoring import build_scorecard


def _local_backtest_failure_category(result: dict) -> str:
    """Classify failed local backtests for generation feedback."""
    turnover = _safe_float(result.get("turnover"))
    if turnover is not None and turnover > 0.70:
        return "high_turnover"
    reasons = " ".join(str(reason).lower() for reason in (result.get("pass_reasons") or []))
    if "turnover" in reasons and "(fail)" in reasons and ("70%" in reasons or "0.70" in reasons):
        return "high_turnover"
    return "low_signal"


def _safe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class PipelineCandidatePoolMixin:
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
            self._apply_local_backtest_prefilter(candidate)
            self._apply_generation_field_prefilter(candidate)
            candidate.scorecard = build_scorecard(
                candidate,
                self.config.thresholds,
                self.config.scoring,
                params=self.auto_calibrator.params,
            )
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

    def _apply_local_backtest_prefilter(self, candidate: Candidate) -> None:
        outcome = apply_local_backtest_gate(
            candidate,
            engine=self._local_backtest_engine,
            cache_key=candidate.dataset_id or self._active_dataset_id or "default",
            extract_fields=extract_fields,
            extract_operators=extract_operators,
            reject_unsupported=True,
        )
        if outcome.get("result") is not None:
            self._record_local_backtest_knowledge(candidate, outcome["result"])

    def _apply_generation_field_prefilter(self, candidate: Candidate) -> None:
        non_signal_fields = non_signal_generation_fields(candidate)
        if not non_signal_fields:
            return
        local = dict(candidate.local_quality or {})
        reasons = list(local.get("reasons") or [])
        reason = "non_signal_generation_fields=" + ",".join(non_signal_fields[:8])
        if reason not in reasons:
            reasons.append(reason)
        local["passed"] = False
        local["reasons"] = reasons
        local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - 8.0, 2))
        local["non_signal_generation_fields"] = non_signal_fields
        candidate.local_quality = local

    def _record_local_backtest_knowledge(self, candidate: Candidate, result: dict) -> None:
        try:
            if not result.get("ok"):
                layer = "failure"
                category = "low_signal"
                title = f"Local backtest error for {candidate.alpha_id}"
            elif result.get("pass_local"):
                layer = "finding"
                category = "field_effectiveness"
                title = f"Local backtest passed for {candidate.alpha_id}"
            else:
                layer = "failure"
                category = _local_backtest_failure_category(result)
                title = f"Local backtest rejected {candidate.alpha_id}"
            entry = KnowledgeEntry(
                layer=layer,
                category=category,
                title=title,
                description=f"Expression {candidate.expression} evaluated locally with status={result.get('ok')} pass_local={result.get('pass_local')}.",
                evidence=[str(result.get("pass_reasons") or result.get("error") or result.get("error_type") or "")],
                confidence=0.8 if result.get("pass_local") else 0.55,
                source_tags=["pipeline", "local_backtest", category],
                expression_pattern=candidate.expression,
                fields_involved=list(candidate.data_fields or []),
                operators_involved=list(candidate.operators or []),
                metadata={
                    "alpha_id": candidate.alpha_id,
                    "dataset_id": candidate.dataset_id,
                    "failure_category": category,
                    "local_backtest": dict(result),
                },
            )
            self._knowledge_base.save(entry)
        except Exception as exc:
            self._event(
                "knowledge_base_write_failed",
                redact_error_message(exc, max_length=160),
                candidate.alpha_id,
                level="WARN",
            )

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
            self._attach_active_assistant_guidance(generated)
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
        state = refresh_context_validation_cache(fields, operators)
        self._context_field_names = state.field_names
        self._context_operator_names = state.operator_names
        self._dataset_field_names_cache = state.dataset_field_names_cache

    def _active_dataset_field_names(self) -> set[str]:
        return active_dataset_field_names(
            self._active_dataset_id,
            self._mapper,
            self._dataset_field_names_cache,
        )

    def _official_context_reasons(self, candidate: Candidate, fields: list[dict], operators: list[dict]) -> list[str]:
        if (fields and not self._context_field_names) or (operators and not self._context_operator_names):
            self._refresh_context_validation_cache(fields, operators)
        return official_context_reasons(
            candidate,
            available_fields=self._context_field_names,
            available_operators=self._context_operator_names,
            active_dataset_id=self._active_dataset_id,
            mapper=self._mapper,
            dataset_field_names_cache=self._dataset_field_names_cache,
        )

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
        targets = self._candidate_pool_service().validation_targets(pool)
        filtered: list[Candidate] = []
        for candidate in targets:
            if self._block_observability_duplicate_before_official(candidate, phase="official_validation"):
                continue
            if self._reject_high_cloud_similarity_before_official(candidate):
                continue
            filtered.append(candidate)
        return filtered

    def _validation_quota(self, pool: list[Candidate]) -> int:
        active_limit = self._active_backtest_limit()
        active_count = self.backtest_slot_manager.active_count()
        self._preflight_pending_backtest_candidates(pool)
        pending_count = len(self._pending_backtest_candidates(pool))
        needed_for_slots = max(0, active_limit - active_count - pending_count)
        return min(
            max(0, int(self.config.budget.max_official_validations_per_cycle)),
            needed_for_slots,
        )

    def _pending_backtest_plan(self, pool: list[Candidate]):
        candidates = self._candidate_pool_service().pending_backtest_candidates(
            pool,
            threshold=self.config.budget.min_prior_score_for_official_simulation,
        )
        plan = self._batch_backtest_coordinator().plan(
            candidates,
            capacity=self._active_backtest_limit(),
        )
        self.last_runtime_data["backtest_batch_plan"] = plan.to_dict()
        return plan

    def _preflight_pending_backtest_candidates(self, pool: list[Candidate]) -> None:
        self._pending_backtest_plan(pool)

    def _backtest_targets(self, pool: list[Candidate]) -> list[Candidate]:
        plan = self._pending_backtest_plan(pool)
        return list(plan.selected)

    def _pending_backtest_candidates(self, pool: list[Candidate], threshold: float | None = None) -> list[Candidate]:
        return self._candidate_pool_service().pending_backtest_candidates(pool, threshold=threshold)

    def _is_pending_backtest_candidate(self, candidate: Candidate, threshold: float | None = None) -> bool:
        return self._candidate_pool_service().is_pending_backtest_candidate(candidate, threshold)

    def _is_active_backtest_candidate(self, candidate: Candidate) -> bool:
        return is_active_backtest_candidate(candidate)

    def _candidate_pool_candidates(self, pool: list[Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().candidate_pool_candidates(
            pool,
            is_active_backtest_candidate=self._is_active_backtest_candidate,
        )

    def _pending_simulation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        return pending_simulation_targets(pool)

    def _refresh_cloud_similarity_index(self) -> None:
        self._cloud_similarity_rows = build_cloud_similarity_rows(self.cloud_alphas)
        self._cloud_risk_cache.clear()

    def _cloud_correlation_risk(self, candidate: Candidate) -> dict:
        official_alpha_id = candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
        if not self._cloud_similarity_rows:
            self._refresh_cloud_similarity_index()
        cache_key = (candidate.expression, official_alpha_id, len(self._cloud_similarity_rows))
        cached = self._cloud_risk_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        result = cloud_correlation_risk(
            candidate,
            self._cloud_similarity_rows,
            official_alpha_id=official_alpha_id,
        )
        self._cloud_risk_cache[cache_key] = dict(result)
        return result

    def _reject_high_cloud_similarity_before_official(self, candidate: Candidate) -> bool:
        risk = self._cloud_correlation_risk(candidate)
        threshold = self.config.submission_policy.max_expression_similarity
        if not _is_high_cloud_similarity(risk, threshold):
            return False
        _reject_high_cloud_similarity_candidate(candidate, _cloud_similarity_details(risk, threshold))
        return True

    def _cloud_status_for_candidate(self, candidate: Candidate) -> dict:
        return cloud_status_for_candidate(candidate, self.cloud_alphas)

    def _remember_accepted(self, accepted_candidates: list[Candidate], candidate: Candidate):
        remember_accepted(accepted_candidates, candidate)

    def _smart_rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        return smart_rank_candidates(candidates, self._cloud_correlation_risk)

    def _smart_ranking_score(self, candidate: Candidate) -> float:
        return smart_ranking_score(candidate, self._cloud_correlation_risk(candidate))
