"""Official validation, simulation polling, and finalization workflow facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring._ranker import ScoringRanker


@dataclass
class OfficialWorkflowService:
    """Thin facade over the official services used by AlphaResearchPipeline.

    Workstream D1.2: official simulation priority is score-ranked.  The
    ``ranker`` field (defaults to ``ScoringRanker``) provides TopK selection
    so ``fill_slots`` consumes the highest-scoring candidates first.
    """

    validate_for_open_backtest_slots: Callable[..., list[Candidate]]
    fill_backtest_slots: Callable[..., None]
    poll_due_backtests: Callable[..., int]
    finalization_service_factory: Callable[[], Any]
    ranker: ScoringRanker = field(default_factory=ScoringRanker)

    def validate_slots(self, *args: Any, **kwargs: Any) -> list[Candidate]:
        return self.validate_for_open_backtest_slots(*args, **kwargs)

    def fill_slots(self, *args: Any, **kwargs: Any) -> None:
        self.fill_backtest_slots(*args, **kwargs)

    def poll_due(self, *args: Any, **kwargs: Any) -> int:
        return self.poll_due_backtests(*args, **kwargs)

    def finalization_service(self) -> Any:
        return self.finalization_service_factory()

    def select_simulation_top_k(
        self,
        candidates: list[Candidate],
        *,
        k: int,
        threshold: float | None = None,
    ) -> list[Candidate]:
        """Return the score-ranked TopK candidates for official simulation.

        Workstream D1.2: official simulation priority is driven by scientific
        score via ``ScoringRanker.select_top_k``.
        """
        return self.ranker.select_top_k(candidates, k=k, threshold=threshold)
