"""Create top-candidate fusion alpha variants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.models import Candidate, new_id

from . import fusion as alpha_fusion
from .generator import extract_fields, extract_operators, local_quality
from .scoring import build_scorecard


RecordLifecycle = Callable[[Candidate, str, str], None]
EventCallback = Callable[..., None]


@dataclass
class FusionCandidateOutcome:
    created_count: int = 0
    candidates: list[Candidate] | None = None


@dataclass
class FusionCandidateService:
    config: OpsConfig
    scoring_params: object | None
    record_lifecycle: RecordLifecycle
    event: EventCallback

    def create_top_candidate_fusions(
        self,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        *,
        cycle: int,
        top_n: int = 3,
        max_created: int = 2,
    ) -> FusionCandidateOutcome:
        pairs = alpha_fusion.select_fusion_candidates(pool_by_expression, top_n=top_n, require_official=True)
        if not pairs:
            return FusionCandidateOutcome(candidates=[])

        created_candidates: list[Candidate] = []
        for first, second in pairs:
            if len(created_candidates) >= max_created:
                break
            fusion_exprs = alpha_fusion.generate_fusion_expressions(first, second)
            for mode, expression in fusion_exprs.items():
                if len(created_candidates) >= max_created:
                    break
                expr_key = _fusion_expression_key(expression)
                if expr_key in blocked_expressions or expr_key in pool_by_expression:
                    continue
                if len(expression) > 500:
                    continue

                child = self._build_child(first, second, mode, expression, cycle)
                child.local_quality = local_quality(child, self.config.budget.min_local_quality_score)
                build_scorecard(child, self.config.thresholds, params=self.scoring_params)
                if (
                    not child.local_quality.get("passed")
                    or child.scorecard.get("total_score", 0.0) < self.config.budget.min_prior_score_for_official_validation
                ):
                    continue

                pool_by_expression[expr_key] = child
                created_candidates.append(child)
                self.record_lifecycle(
                    child,
                    "fusion_created",
                    f"Fusion [{mode}] from {first.alpha_id} + {second.alpha_id} (cycle {cycle})",
                )
                self.event(
                    "fusion_created",
                    f"Fusion [{mode}]: {first.alpha_id} + {second.alpha_id} -> {child.alpha_id}",
                    child.alpha_id,
                    data={"mode": mode, "parents": [first.alpha_id, second.alpha_id]},
                )

        return FusionCandidateOutcome(
            created_count=len(created_candidates),
            candidates=created_candidates,
        )

    def _build_child(
        self,
        first: Candidate,
        second: Candidate,
        mode: str,
        expression: str,
        cycle: int,
    ) -> Candidate:
        return Candidate(
            alpha_id=new_id("alpha"),
            expression=expression,
            family="Hybrid",
            hypothesis=f"Fusion [{mode}]: {first.alpha_id} + {second.alpha_id}",
            data_fields=extract_fields(expression),
            operators=extract_operators(expression),
            source_tags=["fusion", f"fusion_{mode}"],
            parent_id=first.alpha_id,
            mutation_type="fusion",
            submission={
                "fusion_mode": mode,
                "parent_alpha_ids": [first.alpha_id, second.alpha_id],
                "fusion_cycle": cycle,
            },
            lifecycle_status="fusion_pending",
        )


def _fusion_expression_key(expression: str) -> str:
    return " ".join(expression.split()).lower()
