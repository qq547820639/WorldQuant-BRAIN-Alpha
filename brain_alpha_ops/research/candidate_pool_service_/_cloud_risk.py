"""Cloud-similarity / cloud-risk mixin for ``CandidatePoolService_``.

Extracted from the original ``candidate_pool_service_.py`` monolith. Groups
the cloud-alpha correlation risk cache, the pre-official high-similarity
rejection gate, and the smart-ranking wrappers. All of these methods consume
the pipeline's ``cloud_alphas`` / ``_cloud_similarity_rows`` /
``_cloud_risk_cache`` state, which is why they live together here.
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from brain_alpha_ops.research.batch_backtest_coordinator import (
    _cloud_similarity_details,
    _is_high_cloud_similarity,
    _reject_high_cloud_similarity_candidate,
)
from brain_alpha_ops.research.pipeline_cloud import (
    build_cloud_similarity_rows,
    cloud_correlation_risk,
    cloud_status_for_candidate,
    remember_accepted,
    smart_rank_candidates,
    smart_ranking_score,
)


class _CloudRiskMixin:
    """Cloud correlation-risk and smart-ranking helpers.

    The mixin is consumed by ``CandidatePoolService_`` in ``_service``. It
    relies on ``self._pipeline`` being set by the assembling class.
    """

    def _refresh_cloud_similarity_index(self) -> None:
        p = self._pipeline
        p._cloud_similarity_rows = build_cloud_similarity_rows(p.cloud_alphas)
        p._cloud_risk_cache.clear()

    def _cloud_correlation_risk(self, candidate: Candidate) -> dict:
        p = self._pipeline
        official_alpha_id = candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", "")
        if not p._cloud_similarity_rows:
            self._refresh_cloud_similarity_index()
        cache_key = (candidate.expression, official_alpha_id, len(p._cloud_similarity_rows))
        cached = p._cloud_risk_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        result = cloud_correlation_risk(candidate, p._cloud_similarity_rows, official_alpha_id=official_alpha_id)
        p._cloud_risk_cache[cache_key] = dict(result)
        return result

    def _reject_high_cloud_similarity_before_official(self, candidate: Candidate) -> bool:
        risk = self._cloud_correlation_risk(candidate)
        threshold = self._pipeline.config.submission_policy.max_expression_similarity
        if not _is_high_cloud_similarity(risk, threshold):
            return False
        _reject_high_cloud_similarity_candidate(candidate, _cloud_similarity_details(risk, threshold))
        return True

    def _cloud_status_for_candidate(self, candidate: Candidate) -> dict:
        return cloud_status_for_candidate(candidate, self._pipeline.cloud_alphas)

    def _remember_accepted(self, accepted_candidates: list[Candidate], candidate: Candidate):
        remember_accepted(accepted_candidates, candidate)

    def _smart_rank_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        return smart_rank_candidates(candidates, self._cloud_correlation_risk)

    def _smart_ranking_score(self, candidate: Candidate) -> float:
        return smart_ranking_score(candidate, self._cloud_correlation_risk(candidate))
