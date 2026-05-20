"""Official validation, simulation polling, and finalization workflow facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.models import Candidate


@dataclass
class OfficialWorkflowService:
    """Thin facade over the official services used by AlphaResearchPipeline."""

    validate_for_open_backtest_slots: Callable[..., list[Candidate]]
    fill_backtest_slots: Callable[..., None]
    poll_due_backtests: Callable[..., int]
    finalization_service_factory: Callable[[], Any]

    def validate_slots(self, *args: Any, **kwargs: Any) -> list[Candidate]:
        return self.validate_for_open_backtest_slots(*args, **kwargs)

    def fill_slots(self, *args: Any, **kwargs: Any) -> None:
        self.fill_backtest_slots(*args, **kwargs)

    def poll_due(self, *args: Any, **kwargs: Any) -> int:
        return self.poll_due_backtests(*args, **kwargs)

    def finalization_service(self) -> Any:
        return self.finalization_service_factory()
