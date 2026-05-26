"""Local parameter search helpers for research candidates.

This is a small, deterministic search layer that reuses the existing
diagnostics and mutation logic. It is designed to be budgeted and easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.diagnostics import diagnose
from brain_alpha_ops.research.iterative_optimizer import IterativeOptimizer


@dataclass
class ParameterSearchResult:
    candidate: Candidate
    score: float
    diagnosis: dict[str, Any]
    mutation_mode: str = ""
    source: str = "parameter_search"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "score": float(self.score),
            "diagnosis": dict(self.diagnosis),
            "mutation_mode": self.mutation_mode,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


class ParameterSearchService:
    """Generate and rank small candidate mutations within a bounded budget."""

    def __init__(self, *, optimizer: IterativeOptimizer | None = None, search_budget: int = 8) -> None:
        self.optimizer = optimizer or IterativeOptimizer()
        self.search_budget = max(1, int(search_budget or 1))

    def search(
        self,
        candidate: Candidate,
        *,
        max_mutations: int = 4,
        diagnosis: dict[str, Any] | None = None,
        thresholds: Any | None = None,
    ) -> dict[str, Any]:
        diagnosis = diagnosis or diagnose(candidate, thresholds or _fallback_thresholds())
        mutations = self._bounded_mutations(candidate, diagnosis, max_mutations=max_mutations)
        ranked = self.rank(candidate, mutations, diagnosis=diagnosis)
        requested_mutations = max(1, int(max_mutations or 1))
        return {
            "ok": True,
            "schema_version": "parameter_search_result.v1",
            "source": "parameter_search",
            "candidate": candidate.to_dict(),
            "diagnosis": diagnosis,
            "mutation_count": len(mutations),
            "unique_expression_count": len({item.candidate.expression for item in ranked}),
            "budget": {
                "requested_mutations": requested_mutations,
                "evaluated_mutations": len(ranked),
                "search_budget": self.search_budget,
                "bounded": True,
                "live_api_calls": 0,
            },
            "termination_reason": "budget_exhausted"
            if len(ranked) >= min(requested_mutations, self.search_budget)
            else "mutation_space_exhausted",
            "results": [item.to_dict() for item in ranked],
            "best_result": ranked[0].to_dict() if ranked else {},
        }

    def _bounded_mutations(
        self,
        candidate: Candidate,
        diagnosis: dict[str, Any],
        *,
        max_mutations: int,
    ) -> list[Any]:
        safe_max = max(1, int(max_mutations or 1))
        mutations = list(self.optimizer.optimize(candidate, diagnosis, max_mutations=safe_max) or [])
        seen = {str(getattr(item, "expression", "") or "").strip() for item in mutations}
        for fallback in _fallback_mutations(candidate, diagnosis):
            expression = str(getattr(fallback, "expression", "") or "").strip()
            if not expression or expression in seen:
                continue
            mutations.append(fallback)
            seen.add(expression)
            if len(mutations) >= safe_max:
                break
        return mutations[:safe_max]

    def rank(
        self,
        candidate: Candidate,
        mutations: Iterable[Any],
        *,
        diagnosis: dict[str, Any] | None = None,
    ) -> list[ParameterSearchResult]:
        diagnosis = diagnosis or {}
        results: list[ParameterSearchResult] = []
        seen_expressions = {str(candidate.expression or "").strip().lower()}
        for index, mutation in enumerate(mutations):
            if len(results) >= self.search_budget:
                break
            expression = str(getattr(mutation, "expression", "") or "").strip()
            marker = expression.lower()
            if not expression or marker in seen_expressions:
                continue
            seen_expressions.add(marker)
            score = self._score_candidate(candidate, expression, diagnosis)
            mutated_candidate = Candidate.from_dict(candidate.to_dict())
            mutated_candidate.expression = expression
            mutated_candidate.data_fields = list(getattr(mutation, "metadata", {}).get("data_fields") or candidate.data_fields)
            mutated_candidate.operators = list(getattr(mutation, "metadata", {}).get("operators") or candidate.operators)
            mutated_candidate.parent_id = candidate.alpha_id
            mutated_candidate.mutation_type = getattr(mutation, "mode", "")
            mutated_candidate.scorecard = {
                **dict(candidate.scorecard or {}),
                "search_score": score,
            }
            results.append(
                ParameterSearchResult(
                    candidate=mutated_candidate,
                    score=score,
                    diagnosis=diagnosis,
                    mutation_mode=getattr(mutation, "mode", ""),
                    metadata={
                        "rank_input_index": index,
                        "lineage": {
                            "parent_alpha_id": candidate.alpha_id,
                            "parent_expression": candidate.expression,
                        },
                        "reason": getattr(mutation, "reason", ""),
                        "parent_failure": getattr(mutation, "parent_failure", ""),
                    },
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        return results

    def _score_candidate(self, candidate: Candidate, expression: str, diagnosis: dict[str, Any]) -> float:
        base = float(candidate.scorecard.get("total_score", 0.0) or 0.0)
        failed_dimensions = list(diagnosis.get("failed_dimensions") or [])
        penalty = 0.0
        reward = 0.0
        if "sharpe" in failed_dimensions:
            reward += 6.0
        if "fitness" in failed_dimensions:
            reward += 4.0
        if "correlation" in failed_dimensions:
            reward += 5.0
        if "turnover_platform" in failed_dimensions or "turnover_quality" in failed_dimensions:
            reward += 3.0
        if "concentration" in failed_dimensions:
            reward += 2.5
        if "margin" in failed_dimensions:
            reward += 2.0
        if "sub_universe_sharpe" in failed_dimensions:
            reward += 2.5
        if not expression.strip():
            penalty += 100.0
        if expression.strip() == candidate.expression.strip():
            penalty += 3.0
        return round(max(0.0, base + reward - penalty), 4)


def _fallback_thresholds() -> Any:
    class _Thresholds:
        min_sharpe = 1.25
        min_fitness = 1.0
        min_turnover = 0.01
        platform_max_turnover = 0.70
        target_max_turnover = 0.30
        max_self_correlation = 0.70
        max_weight_concentration = 0.10
        min_margin_bps = 4.0
        sub_universe_sharpe_min_ratio = 0.75

    return _Thresholds()


def _fallback_mutations(candidate: Candidate, diagnosis: dict[str, Any]) -> list[Any]:
    expression = candidate.expression or ""
    failed = [str(item) for item in diagnosis.get("failed_dimensions") or [] if str(item)]
    rows: list[Any] = []
    if any(item in failed for item in ("sharpe", "fitness", "turnover_low")):
        rows.append(_mutation(_replace_first_window(expression, 30), "window_perturb", "Deterministic window fallback", "sharpe"))
    if any(item in failed for item in ("fitness", "margin", "concentration", "sub_universe_sharpe")):
        rows.append(_mutation(f"winsorize({expression}, std=4)", "structure_refine", "Deterministic structure fallback", "fitness"))
    if any(item in failed for item in ("turnover_platform", "turnover_quality")):
        rows.append(_mutation(_scale_windows(expression, 2), "longer_window", "Deterministic longer-window fallback", "turnover_quality"))
    if any(item in failed for item in ("correlation", "gate")):
        rows.append(_mutation(f"group_neutralize({expression}, subindustry)", "structure_refine", "Deterministic neutralization fallback", "correlation"))
    if not rows:
        rows.append(_mutation(f"zscore({expression})", "structure_refine", "General deterministic fallback", "general"))
    return rows


def _mutation(expression: str, mode: str, reason: str, parent_failure: str) -> Any:
    return type(
        "FallbackMutation",
        (),
        {
            "expression": expression,
            "mode": mode,
            "reason": reason,
            "parent_failure": parent_failure,
            "metadata": {},
        },
    )()


def _replace_first_window(expression: str, replacement: int) -> str:
    return re.sub(r"\b\d+\b", str(replacement), expression, count=1)


def _scale_windows(expression: str, factor: int) -> str:
    def repl(match: re.Match[str]) -> str:
        value = int(match.group(0))
        if value < 2:
            return match.group(0)
        return str(min(252, max(3, value * factor)))

    return re.sub(r"\b\d+\b", repl, expression)
