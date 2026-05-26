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
        round_summaries: list[dict[str, Any]] = []
        seen_expressions = {str(candidate.expression or "").strip().lower()}
        evaluated_candidates = 0
        for round_index in range(safe_rounds):
            round_results: list[dict[str, Any]] = []
            for item in frontier:
                result = self.service.search(item, max_mutations=max_mutations)
                evaluated_candidates += 1
                round_results.extend([row for row in result.get("results", []) if isinstance(row, dict)])
            round_results.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
            unique_round_results: list[dict[str, Any]] = []
            duplicate_count = 0
            for row in round_results:
                candidate_payload = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
                marker = str(candidate_payload.get("expression") or "").strip().lower()
                if not marker:
                    continue
                if marker in seen_expressions:
                    duplicate_count += 1
                    continue
                seen_expressions.add(marker)
                unique_round_results.append(row)
            selected = unique_round_results[:safe_keep_top]
            all_results.extend(selected)
            frontier = [
                Candidate.from_dict(row["candidate"])
                for row in selected
                if isinstance(row.get("candidate"), dict)
            ]
            round_summaries.append(
                {
                    "round_index": round_index,
                    "input_count": len(round_results),
                    "selected_count": len(selected),
                    "duplicate_count": duplicate_count,
                    "frontier_count": len(frontier),
                }
            )
            if not frontier:
                break
        all_results.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
        max_expansions = safe_rounds * safe_keep_top * max(1, int(max_mutations or 1))
        return {
            "ok": True,
            "schema_version": "parameter_search_orchestration.v1",
            "rounds": safe_rounds,
            "max_mutations": max_mutations,
            "keep_top": safe_keep_top,
            "result_count": len(all_results),
            "evaluated_candidate_count": evaluated_candidates,
            "unique_expression_count": len(seen_expressions),
            "round_summaries": round_summaries,
            "termination_reason": "round_budget_exhausted" if len(round_summaries) == safe_rounds else "frontier_exhausted",
            "best_result": all_results[0] if all_results else {},
            "results": all_results[: safe_keep_top * safe_rounds],
            "budget": {
                "max_candidate_expansions": max_expansions,
                "evaluated_candidates": evaluated_candidates,
                "selected_results": len(all_results),
                "live_api_calls": 0,
                "bounded": True,
            },
        }
