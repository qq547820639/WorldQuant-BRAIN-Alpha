"""Create directed secondary-fusion candidates after official failures."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable

from brain_alpha_ops.config import OpsConfig
from brain_alpha_ops.models import Candidate, new_id
from brain_alpha_ops.redaction import redact_error_message

from .expression_ast import expression_key
from .generator import extract_fields, extract_operators, local_quality, mutate_expression
from .scoring import build_scorecard

logger = logging.getLogger(__name__)


RecordLifecycle = Callable[[Candidate, str, str], None]
EventCallback = Callable[..., None]
RetryCount = Callable[[Candidate], int]


@dataclass
class SecondaryFusionOutcome:
    candidate: Candidate | None = None
    produced_increment: int = 0
    skipped: bool = False
    reason: str = ""


@dataclass
class SecondaryFusionService:
    config: OpsConfig
    scoring_params: object | None
    optimizer: object | None
    record_lifecycle: RecordLifecycle
    event: EventCallback
    retry_count: RetryCount

    def create(
        self,
        candidate: Candidate,
        *,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        reason: str,
    ) -> SecondaryFusionOutcome:
        if not self.config.budget.enable_secondary_fusion:
            return SecondaryFusionOutcome(skipped=True, reason="secondary fusion disabled")

        parent_key = expression_key(candidate.expression)
        failed_reasons = candidate.gate.get("failed_reasons", [])
        note = "; ".join(str(item) for item in failed_reasons if item) or reason
        diagnostic, mutation_mode = self._diagnose_mutation(candidate)
        expression_pool = self._expression_pool(candidate, diagnostic, mutation_mode)

        for expression in expression_pool:
            child_key = expression_key(expression)
            if not child_key or child_key == parent_key:
                continue
            if child_key in blocked_expressions or child_key in pool_by_expression:
                continue
            child = self._build_child(candidate, expression, note)
            child.local_quality = local_quality(child, self.config.budget.min_local_quality_score)
            build_scorecard(child, self.config.thresholds, self.config.scoring, params=self.scoring_params)
            if (
                not child.local_quality.get("passed")
                or child.scorecard.get("total_score", 0.0) < self.config.budget.min_prior_score_for_official_validation
            ):
                continue

            pool_by_expression[child_key] = child
            candidate.submission["secondary_fusion_child_id"] = child.alpha_id
            self.record_lifecycle(child, "secondary_fusion_created", note)
            self.event(
                "secondary_fusion_created",
                f"Created secondary fusion candidate from {candidate.alpha_id}.",
                child.alpha_id,
                data={"parent_alpha_id": candidate.alpha_id, "reason": note[:240]},
                level="WARN",
            )
            return SecondaryFusionOutcome(candidate=child, produced_increment=1)

        self.event(
            "secondary_fusion_skipped",
            f"No eligible secondary fusion variant created for {candidate.alpha_id}.",
            candidate.alpha_id,
            data={"reason": note[:240]},
            level="WARN",
        )
        return SecondaryFusionOutcome(skipped=True, reason=note[:240])

    def _diagnose_mutation(self, candidate: Candidate) -> tuple[dict, str]:
        metrics = candidate.official_metrics or {}
        diagnostic: dict = {}
        try:
            from .diagnostics import diagnose, get_mutation_mode

            diagnostic = diagnose(candidate, self.config.thresholds)
            mutation_mode = get_mutation_mode(diagnostic, fallback="default")
            primary_failure = diagnostic.get("primary_failure", "")
        except Exception as exc:
            message = redact_error_message(exc)
            logger.warning(
                "diagnostics unavailable for secondary fusion candidate %s: %s",
                candidate.alpha_id,
                message,
                exc_info=True,
            )
            self.event(
                "secondary_fusion_diagnostics_unavailable",
                f"Falling back to simple mutation heuristics: {message}",
                candidate.alpha_id,
                level="WARN",
            )
            diagnostic = {}
            mutation_mode = "default"
            primary_failure = ""

        if not primary_failure:
            sharpe = float(metrics.get("sharpe", 0) or 0)
            correlation = abs(float(metrics.get("correlation", 0) or 0))
            turnover = float(metrics.get("turnover", 0) or 0)
            if correlation >= 0.70:
                mutation_mode = "structure_change"
            elif turnover > 0.30:
                mutation_mode = "longer_window"
            elif sharpe < 0.8:
                mutation_mode = "field_swap"
            else:
                mutation_mode = "default"
        return diagnostic, mutation_mode

    def _expression_pool(self, candidate: Candidate, diagnostic: dict, mutation_mode: str) -> list[str]:
        expression_pool: list[str] = []
        if self.optimizer and diagnostic.get("failed_dimensions"):
            mutations = self.optimizer.optimize(candidate, diagnostic, max_mutations=6)
            expression_pool = [item.expression for item in mutations if item.expression != candidate.expression]
        if expression_pool:
            return expression_pool

        base_seed = self.retry_count(candidate) * 8
        return [
            expression
            for expression in (
                mutate_expression(candidate.expression, base_seed + index, mode=mutation_mode)
                for index in range(1, 9)
            )
            if expression != candidate.expression
        ]

    def _build_child(self, candidate: Candidate, expression: str, note: str) -> Candidate:
        source_tags = list(candidate.source_tags or [])
        if "secondary_fusion" not in source_tags:
            source_tags.append("secondary_fusion")
        return Candidate(
            alpha_id=new_id("alpha"),
            expression=expression,
            family=candidate.family,
            hypothesis=f"{candidate.hypothesis} Secondary fusion after: {note[:160]}",
            data_fields=extract_fields(expression),
            operators=extract_operators(expression),
            source_tags=source_tags,
            parent_id=candidate.alpha_id,
            mutation_type="secondary_fusion",
            submission={
                "parent_alpha_id": candidate.alpha_id,
                "secondary_fusion_reason": note[:240],
                "source_official_alpha_id": candidate.official_alpha_id,
            },
            lifecycle_status="secondary_fusion_pending",
        )
