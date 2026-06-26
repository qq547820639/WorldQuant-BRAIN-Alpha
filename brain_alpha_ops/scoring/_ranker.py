"""Scoring-driven candidate ranker and eliminator (Workstream D1.1).

``ScoringRanker`` formalises the use of scientific scores as ranking and
elimination gates.  It takes a candidate list (optionally with pre-computed
scorecards) and returns ranked/eliminated partitions based on configurable
thresholds.

The ranker is callable so it can be used as a drop-in ``CandidateRanker``
(see ``research.candidate_pool.CandidateRanker``) for ``CandidatePoolService``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from brain_alpha_ops.models import Candidate

logger = logging.getLogger(__name__)

# Default thresholds aligned with ``CandidatePoolService`` defaults
# (``min_prior_score_for_official_validation`` = 60.0,
#  ``min_prior_score_for_official_simulation`` = 70.0).
DEFAULT_VALIDATION_THRESHOLD: float = 60.0
DEFAULT_SIMULATION_THRESHOLD: float = 70.0
DEFAULT_SUBMIT_THRESHOLD: float = 85.0
DEFAULT_RESEARCH_THRESHOLD: float = 50.0


@dataclass
class RankingPartition:
    """Result of partitioning candidates by score thresholds."""

    ranked: list[Candidate] = field(default_factory=list)
    eliminated: list[Candidate] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked": [c.alpha_id for c in self.ranked],
            "eliminated": [c.alpha_id for c in self.eliminated],
            "thresholds": dict(self.thresholds),
            "ranked_count": len(self.ranked),
            "eliminated_count": len(self.eliminated),
        }


class ScoringRanker:
    """Rank candidates by scientific score and partition by thresholds.

    Used by the candidate pool and the official workflow service to ensure
    TopK selection for official simulation is score-ranked (Workstream D1.2).

    Callable form: ``ranker(candidates) -> ranked_candidates`` (backward
    compatible with ``CandidateRanker``).
    """

    def __init__(
        self,
        *,
        validation_threshold: float = DEFAULT_VALIDATION_THRESHOLD,
        simulation_threshold: float = DEFAULT_SIMULATION_THRESHOLD,
        submit_threshold: float = DEFAULT_SUBMIT_THRESHOLD,
        research_threshold: float = DEFAULT_RESEARCH_THRESHOLD,
        score_extractor: Callable[[Candidate], float] | None = None,
    ) -> None:
        self.validation_threshold = float(validation_threshold)
        self.simulation_threshold = float(simulation_threshold)
        self.submit_threshold = float(submit_threshold)
        self.research_threshold = float(research_threshold)
        self._score_extractor = score_extractor or _default_score

    # --- Callable interface (CandidateRanker compatible) -------------------

    def __call__(self, candidates: Iterable[Candidate]) -> list[Candidate]:
        return self.rank(candidates)

    # --- Ranking -----------------------------------------------------------

    def rank(self, candidates: Iterable[Candidate]) -> list[Candidate]:
        """Return candidates sorted by score descending (stable).

        Tie-breakers mirror ``research.pipeline_helpers.rank_candidates``:
        submission-ready gates, official metrics, then local rank score and
        local quality.
        """
        return sorted(
            list(candidates),
            key=lambda c: (
                bool(_gate_submission_ready(c)),
                bool(c.official_metrics),
                self._score_extractor(c),
                float(c.scorecard.get("local_rank_score", 0.0) or 0.0),
                float(c.local_quality.get("score", 0.0) or 0.0),
            ),
            reverse=True,
        )

    # --- Partitioning ------------------------------------------------------

    def partition(
        self,
        candidates: Iterable[Candidate],
        *,
        threshold: float | None = None,
    ) -> RankingPartition:
        """Split candidates into ranked (>= threshold) and eliminated (< threshold).

        Defaults to ``validation_threshold`` when ``threshold`` is None.
        """
        cutoff = float(self.validation_threshold if threshold is None else threshold)
        ranked: list[Candidate] = []
        eliminated: list[Candidate] = []
        for candidate in candidates:
            if self._score_extractor(candidate) >= cutoff:
                ranked.append(candidate)
            else:
                eliminated.append(candidate)
        ranked = self.rank(ranked)
        return RankingPartition(
            ranked=ranked,
            eliminated=eliminated,
            thresholds={
                "validation": self.validation_threshold,
                "simulation": self.simulation_threshold,
                "submit": self.submit_threshold,
                "cutoff_applied": cutoff,
            },
        )

    def select_top_k(
        self,
        candidates: Iterable[Candidate],
        *,
        k: int,
        threshold: float | None = None,
    ) -> list[Candidate]:
        """Return the TopK candidates by score, respecting the simulation threshold.

        Used by ``OfficialWorkflowService.fill_slots()`` to pull score-ranked
        TopK for official simulation priority (Workstream D1.2).
        """
        cutoff = float(self.simulation_threshold if threshold is None else threshold)
        eligible = [
            c for c in list(candidates)
            if self._score_extractor(c) >= cutoff
        ]
        return self.rank(eligible)[: max(0, int(k or 0))]

    def decision_band(self, candidate: Candidate) -> str:
        """Map a candidate's score to a decision band for ranking attribution."""
        score = self._score_extractor(candidate)
        if _gate_hard_blocked(candidate):
            return "hard_gate_blocked"
        if score >= self.submit_threshold:
            return "submit_candidate"
        if score >= self.simulation_threshold:
            return "optimize_before_submit"
        if score >= self.research_threshold:
            return "research_only"
        return "abandon_or_rebuild"

    def ranking_reason(self, candidate: Candidate) -> str:
        """Human-readable reason for why a candidate is ranked this way."""
        score = self._score_extractor(candidate)
        band = self.decision_band(candidate)
        reasons: list[str] = [f"score={score:.2f}", f"band={band}"]
        gate = candidate.gate if isinstance(candidate.gate, dict) else {}
        if gate.get("submission_ready"):
            reasons.append("submission_ready")
        if gate.get("hard_gate_blocked"):
            failures = gate.get("failed_reasons") or []
            if failures:
                reasons.append(f"hard_gate_blocked:{failures[0]}")
        if candidate.official_metrics:
            reasons.append("official_verified")
        return "; ".join(reasons)


def _default_score(candidate: Candidate) -> float:
    """Extract the total scientific score from a candidate's scorecard."""
    return float(candidate.scorecard.get("total_score", 0.0) or 0.0)


def _gate_submission_ready(candidate: Candidate) -> bool:
    gate = candidate.gate if isinstance(candidate.gate, dict) else {}
    return bool(gate.get("submission_ready"))


def _gate_hard_blocked(candidate: Candidate) -> bool:
    gate = candidate.gate if isinstance(candidate.gate, dict) else {}
    return bool(gate.get("hard_gate_blocked"))


__all__ = [
    "DEFAULT_RESEARCH_THRESHOLD",
    "DEFAULT_SIMULATION_THRESHOLD",
    "DEFAULT_SUBMIT_THRESHOLD",
    "DEFAULT_VALIDATION_THRESHOLD",
    "RankingPartition",
    "ScoringRanker",
]
