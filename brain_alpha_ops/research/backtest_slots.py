"""Backtest slot state management for official simulation polling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from brain_alpha_ops.models import Candidate

from .contracts import recoverable_backtest_candidates


ExpressionKey = Callable[[Candidate], str]


@dataclass
class BacktestSlotManager:
    """Owns the mutable official backtest slot map.

    The pipeline still performs API calls and business decisions; this class is
    intentionally small and handles only capacity, recovery, and duplicate slot
    selection.
    """

    slots: dict[int, Candidate] = field(default_factory=dict)
    recovered_slot_count: int = 0

    def active_count(self) -> int:
        return len(self.slots)

    def open_slots(self, active_limit: int) -> list[int]:
        limit = _positive_limit(active_limit)
        return [slot for slot in range(1, limit + 1) if slot not in self.slots]

    def assign(self, slot: int, candidate: Candidate) -> None:
        slot_number = int(slot or 0)
        if slot_number <= 0:
            raise ValueError("backtest slot must be a positive integer")
        self.slots[slot_number] = candidate

    def release(self, slot: int) -> Candidate | None:
        return self.slots.pop(int(slot or 0), None)

    def get(self, slot: int) -> Candidate | None:
        return self.slots.get(int(slot or 0))

    def values(self) -> list[Candidate]:
        return list(self.slots.values())

    def items_snapshot(self) -> list[tuple[int, Candidate]]:
        return list(self.slots.items())

    def active_expression_keys(self, key_fn: ExpressionKey) -> set[str]:
        return {key_fn(candidate) for candidate in self.slots.values()}

    def next_candidate(
        self,
        candidates: Iterable[Candidate],
        *,
        key_fn: ExpressionKey,
    ) -> Candidate | None:
        active_keys = self.active_expression_keys(key_fn)
        for candidate in candidates:
            if key_fn(candidate) not in active_keys:
                return candidate
        return None

    def recover_from_records(self, rows: list[dict], *, max_slots: int) -> list[tuple[int, Candidate]]:
        recovered = recoverable_backtest_candidates(rows, max_slots=_positive_limit(max_slots))
        added = self.recover(recovered, max_slots=max_slots)
        self.recovered_slot_count = len(added)
        return added

    def recover(self, candidates: Iterable[Candidate], *, max_slots: int) -> list[tuple[int, Candidate]]:
        limit = _positive_limit(max_slots)
        added: list[tuple[int, Candidate]] = []
        for candidate in candidates:
            slot = int(candidate.submission.get("backtest_slot", 0) or 0)
            if slot <= 0 or slot > limit or slot in self.slots:
                continue
            self.slots[slot] = candidate
            added.append((slot, candidate))
        return added


def _positive_limit(value: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, limit)
