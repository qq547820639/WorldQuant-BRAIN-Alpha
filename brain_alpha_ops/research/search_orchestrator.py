"""Higher-level parameter scan and evolution orchestration."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.parameter_search import ParameterSearchService


class ParameterSearchOrchestrator:
    """Run bounded multi-round parameter search without unbounded API calls."""

    def __init__(self, *, service: ParameterSearchService | None = None) -> None:
        self.service = service or ParameterSearchService()

    def run(
        self,
        candidate: Candidate,
        *,
        rounds: int = 2,
        max_mutations: int = 4,
        keep_top: int = 3,
    ) -> dict[str, Any]:
        safe_rounds = max(1, min(int(rounds or 1), 8))
        safe_keep_top = max(1, min(int(keep_top or 1), 20))
        frontier = [candidate]
        all_results: list[dict[str, Any]] = []
        for round_index in range(safe_rounds):
            round_results: list[dict[str, Any]] = []
            for item in frontier:
                result = self.service.search(item, max_mutations=max_mutations)
                round_results.extend([row for row in result.get("results", []) if isinstance(row, dict)])
            round_results.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
            selected = round_results[:safe_keep_top]
            all_results.extend(selected)
            frontier = [
                Candidate.from_dict(row["candidate"])
                for row in selected
                if isinstance(row.get("candidate"), dict)
            ]
            if not frontier:
                break
        all_results.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        return {
            "ok": True,
            "schema_version": "parameter_search_orchestration.v1",
            "rounds": safe_rounds,
            "max_mutations": max_mutations,
            "keep_top": safe_keep_top,
            "result_count": len(all_results),
            "best_result": all_results[0] if all_results else {},
            "results": all_results[: safe_keep_top * safe_rounds],
            "budget": {
                "max_candidate_expansions": safe_rounds * safe_keep_top * max(1, int(max_mutations or 1)),
                "live_api_calls": 0,
                "bounded": True,
            },
        }
