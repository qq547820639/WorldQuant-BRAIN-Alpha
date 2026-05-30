"""Stage-based pipeline processor framework for AlphaResearchPipeline.

Refactors the monolithic 2555-line pipeline.py into six cohesive stage processors,
each with a single responsibility.  The existing pipeline.py retains backward
compatibility by composing these stages internally.

Stages
------
  Stage 1 — GenerationStage       : Generate candidate alpha expressions.
  Stage 2 — LocalScoringStage     : Run local quality scoring and pre-filtering.
  Stage 3 — OfficialValidationStage : Validate expressions via BRAIN API.
  Stage 4 — SimulationStage       : Submit and poll BRAIN simulations.
  Stage 5 — QualityGateStage      : Evaluate quality gates and decision bands.
  Stage 6 — SubmissionStage        : Safe submission with ledger tracking.

Architecture
------------
    PipelineStagesOrchestrator
     ├── GenerationStage
     ├── LocalScoringStage
     ├── OfficialValidationStage
     ├── SimulationStage
     ├── QualityGateStage
     └── SubmissionStage

Each stage:
  - Accepts a shared PipelineContext (immutable configuration + mutable state).
  - Returns a StageResult with status, metrics, and the updated context.
  - Automatically records lifecycle events for auditability.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

STAGE_SCHEMA_VERSION = "pipeline_stages.v1"


# ═══════════════════════════════════════════════════════════════════════════
# Stage protocol & context
# ═══════════════════════════════════════════════════════════════════════════

class StageStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    SKIPPED = auto()
    FAILED = auto()
    BLOCKED = auto()


@dataclass
class StageResult:
    """Result of executing a single pipeline stage."""
    stage_name: str = ""
    status: StageStatus = StageStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0
    items_processed: int = 0
    items_passed: int = 0
    items_failed: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "status": self.status.name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "items_processed": self.items_processed,
            "items_passed": self.items_passed,
            "items_failed": self.items_failed,
            "metrics": self.metrics,
            "error": self.error,
            "recommendations": self.recommendations,
        }


class PipelineStage(ABC):
    """Base class for all pipeline stages.

    Subclasses must implement:
      - stage_name: class attribute (str) identifying the stage.
      - execute(ctx): the core stage logic.
    """

    @abstractmethod
    def stage_name(self) -> str:
        """Stage identifier — subclasses override as a class attribute."""
        ...

    def run(self, ctx: Any) -> StageResult:
        """Run the stage with timing, error handling, and lifecycle events."""
        result = StageResult(stage_name=self.stage_name)
        result.started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()

        try:
            result.status = StageStatus.RUNNING
            updated_ctx = self.execute(ctx)
            result.status = StageStatus.COMPLETED
            result.duration_seconds = time.perf_counter() - started
            # Copy mutable state back
            if updated_ctx is not None and updated_ctx is not ctx:
                _merge_context(ctx, updated_ctx)
        except Exception as exc:
            result.status = StageStatus.FAILED
            result.error = str(exc)
            result.duration_seconds = time.perf_counter() - started
            logger.error("pipeline stage %s failed: %s", self.stage_name, exc, exc_info=True)

        result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    @abstractmethod
    def execute(self, ctx: Any) -> Any:
        """Execute the stage logic.  May return an updated context."""
        ...


def _merge_context(target: Any, source: Any) -> None:
    """Merge selected mutable attributes from source into target."""
    for attr in dir(source):
        if attr.startswith("_"):
            continue
        if callable(getattr(source, attr, None)):
            continue
        try:
            setattr(target, attr, getattr(source, attr))
        except AttributeError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Concrete Stage Processors
# ═══════════════════════════════════════════════════════════════════════════

class GenerationStage(PipelineStage):
    """Stage 1: Generate candidate alpha expressions.

    Delegates to the pipeline's CandidateGenerator, applying experience guidance,
    assistant guidance, and observability constraints.
    """

    stage_name: str = "generation"

    def execute(self, ctx: Any) -> Any:
        pipeline = ctx  # ctx is the AlphaResearchPipeline instance
        count = pipeline.ops.budget.max_candidates_per_cycle
        generator = getattr(pipeline, "_generator", None)

        if generator is None:
            from brain_alpha_ops.research.generator import CandidateGenerator
            generator = CandidateGenerator()
            pipeline._generator = generator

        # Apply guidance from research memory
        memory_guidance = getattr(pipeline, "_current_memory_guidance", None)
        if memory_guidance:
            generator.set_experience_guidance(memory_guidance)

        # Apply observability guidance
        observability_guidance = getattr(pipeline, "_current_observability_guidance", None)
        if observability_guidance:
            generator.set_observability_guidance(observability_guidance)

        candidates = generator.generate(count)

        # Store in context
        if not hasattr(pipeline, "_candidate_pool"):
            pipeline._candidate_pool = []
        pipeline._candidate_pool = list(candidates)

        return pipeline


class LocalScoringStage(PipelineStage):
    """Stage 2: Run local quality scoring and pre-filtering.

    Evaluates each candidate with local_quality() + build_scorecard().
    Filters candidates below min_local_quality_score threshold.
    """

    stage_name: str = "local_scoring"

    def execute(self, ctx: Any) -> Any:
        pipeline = ctx
        candidates = getattr(pipeline, "_candidate_pool", [])
        if not candidates:
            logger.info("local_scoring: no candidates to score")
            return pipeline

        from brain_alpha_ops.research.generator import local_quality
        from brain_alpha_ops.research.scoring import build_scorecard

        thresholds = pipeline.ops.thresholds
        scoring = pipeline.ops.scoring
        budget = pipeline.ops.budget
        min_quality = budget.min_local_quality_score

        passed = []
        failed = []
        for candidate in candidates:
            quality = local_quality(candidate, min_quality)
            candidate.local_quality = quality
            if not quality.get("passed", quality.get("score", 0) >= min_quality * 10):
                candidate.lifecycle_status = "local_quality_failed"
                failed.append(candidate)
                continue
            scorecard = build_scorecard(candidate, thresholds, scoring)
            candidate.scorecard = scorecard
            candidate.lifecycle_status = "scored"
            passed.append(candidate)

        pipeline._candidate_pool = passed
        pipeline._scored_rejected = failed

        logger.info(
            "local_scoring: %d passed (quality>=%s), %d rejected",
            len(passed), min_quality, len(failed),
        )
        return pipeline


class OfficialValidationStage(PipelineStage):
    """Stage 3: Validate expressions through BRAIN API alpha check.

    Submits candidates for official BRAIN validation.
    Respects budget.max_official_validations_per_cycle.
    """

    stage_name: str = "official_validation"

    def execute(self, ctx: Any) -> Any:
        pipeline = ctx
        api = getattr(pipeline, "_api", None)
        if api is None:
            logger.warning("official_validation: no API instance — skipping")
            return pipeline

        candidates = getattr(pipeline, "_candidate_pool", [])
        max_validations = pipeline.ops.budget.max_official_validations_per_cycle
        to_validate = candidates[:max_validations]

        validated = []
        for candidate in to_validate:
            try:
                api.authenticate()
                settings = pipeline.ops.settings.to_platform_dict()["settings"]
                validation = api.validate_expression(candidate.expression, settings)
                candidate.validation_result = validation
                if str(validation.get("status", "")).upper() in {"PASS", "PASSED", "OK"}:
                    candidate.lifecycle_status = "validated"
                    candidate.official_alpha_id = str(validation.get("alpha_id") or "")
                else:
                    candidate.lifecycle_status = "validation_failed"
                validated.append(candidate)
            except Exception as exc:
                logger.warning("validation failed for %s: %s", candidate.alpha_id, exc)
                candidate.lifecycle_status = "validation_error"
                validated.append(candidate)

        pipeline._candidate_pool = validated
        return pipeline


class SimulationStage(PipelineStage):
    """Stage 4: Submit and poll BRAIN simulations for validated candidates.

    Manages backtest slot lifecycle: submit → poll → fetch results.
    Respects budget max_official_simulations_per_cycle and concurrent limits.
    """

    stage_name: str = "simulation"

    def execute(self, ctx: Any) -> Any:
        pipeline = ctx
        api = getattr(pipeline, "_api", None)
        if api is None:
            logger.warning("simulation: no API instance — skipping")
            return pipeline

        candidates = getattr(pipeline, "_candidate_pool", [])
        max_sim = pipeline.ops.budget.max_official_simulations_per_cycle
        to_simulate = [c for c in candidates if c.lifecycle_status == "validated"][:max_sim]

        for candidate in to_simulate:
            try:
                api.authenticate()
                settings = pipeline.ops.settings.to_platform_dict()["settings"]
                sim_id = api.submit_simulation(candidate.expression, settings)
                candidate.simulation_id = sim_id
                candidate.lifecycle_status = "simulating"

                # Poll for completion (limited polls)
                poll_config = pipeline.ops.official_api
                for _ in range(poll_config.poll_attempts):
                    status = str(api.poll_simulation(sim_id))
                    if status.upper() in {"COMPLETED", "FAILED", "ERROR"}:
                        break
                    time.sleep(poll_config.poll_interval_seconds)

                if status.upper() == "COMPLETED":
                    result = api.fetch_result(sim_id)
                    candidate.official_metrics = result
                    candidate.lifecycle_status = "simulation_completed"
                else:
                    candidate.lifecycle_status = "simulation_failed"
            except Exception as exc:
                logger.warning("simulation failed for %s: %s", candidate.alpha_id, exc)
                candidate.lifecycle_status = "simulation_error"

        return pipeline


class QualityGateStage(PipelineStage):
    """Stage 5: Evaluate quality gates and assign decision bands.

    Runs evaluate_quality_gate() and decision_band() on each candidate
    with completed simulations.  Produces submit/optimize/research/abandon
    recommendations.
    """

    stage_name: str = "quality_gate"

    def execute(self, ctx: Any) -> Any:
        pipeline = ctx
        candidates = getattr(pipeline, "_candidate_pool", [])

        from brain_alpha_ops.research.scoring import (
            build_scorecard,
            decision_band,
            evaluate_quality_gate,
        )

        thresholds = pipeline.ops.thresholds
        scoring = pipeline.ops.scoring

        for candidate in candidates:
            if getattr(candidate, "lifecycle_status", "") != "simulation_completed":
                continue

            # Re-score with official metrics
            scorecard = build_scorecard(candidate, thresholds, scoring)
            candidate.scorecard = scorecard

            # Evaluate gate
            gate = evaluate_quality_gate(candidate, thresholds)
            candidate.gate = gate

            # Decision band
            total_score = scorecard.get("total_score", 0)
            band = decision_band(total_score)
            candidate.decision_band = band
            candidate.lifecycle_status = f"gated:{band}" if gate.get("passed") else "gated:blocked"

        # Sort by score
        pipeline._candidate_pool.sort(
            key=lambda c: (c.scorecard or {}).get("total_score", 0) if c.scorecard else 0,
            reverse=True,
        )
        return pipeline


class SubmissionStage(PipelineStage):
    """Stage 6: Safe submission with ledger tracking.

    Only submits candidates whose decision_band == "submit_candidate"
    and which pass all safety checks.  Records every submission in
    SubmissionLedger for auditability.
    """

    stage_name: str = "submission"

    def execute(self, ctx: Any) -> Any:
        pipeline = ctx
        api = getattr(pipeline, "_api", None)
        if api is None:
            logger.info("submission: no API instance — skipping")
            return pipeline

        if not pipeline.auto_submit:
            logger.info("submission: auto_submit disabled — skipping")
            return pipeline

        from brain_alpha_ops.research.safety import SubmissionLedger

        candidates = getattr(pipeline, "_candidate_pool", [])
        submissions = [
            c for c in candidates
            if getattr(c, "decision_band", "") == "submit_candidate"
            and getattr(c, "lifecycle_status", "").startswith("gated")
        ]

        policy = pipeline.ops.submission_policy
        ledger = SubmissionLedger(pipeline.ops.storage_dir)
        submitted = 0

        for candidate in submissions:
            if submitted >= policy.max_auto_submissions_per_run:
                break

            # Safety assessment
            safety = ledger.assess(candidate, policy, mode="auto")
            if not safety.get("allowed"):
                logger.info("submission blocked by safety: %s", safety.get("failed_reasons"))
                continue

            try:
                api.authenticate()
                check = api.check_alpha(candidate.official_alpha_id)
                if str(check.get("status", "")).upper() not in {"PASS", "PASSED"}:
                    logger.warning("pre-submit check failed for %s", candidate.official_alpha_id)
                    continue

                settings = pipeline.ops.settings.to_platform_dict()["settings"]
                result = api.submit_alpha(
                    candidate.official_alpha_id,
                    candidate.expression,
                    settings,
                )
                ledger.record(candidate, result, mode="auto")
                candidate.lifecycle_status = "submitted"
                submitted += 1
                logger.info("submitted alpha %s", candidate.official_alpha_id)
            except Exception as exc:
                logger.error("submission failed for %s: %s", candidate.official_alpha_id, exc)

        logger.info("submission stage: %d submitted", submitted)
        return pipeline


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline Stages Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class PipelineStagesOrchestrator:
    """Chains pipeline stage processors in sequence.

    Usage::

        orchestrator = PipelineStagesOrchestrator()
        orchestrator.add_stage(GenerationStage())
        orchestrator.add_stage(LocalScoringStage())
        orchestrator.add_stage(QualityGateStage())
        results = orchestrator.run(pipeline_instance)
        for result in results:
            print(f"{result.stage_name}: {result.status.name}")
    """

    def __init__(self):
        self._stages: list[PipelineStage] = []

    def add_stage(self, stage: PipelineStage) -> "PipelineStagesOrchestrator":
        self._stages.append(stage)
        return self

    @property
    def stages(self) -> list[PipelineStage]:
        return list(self._stages)

    def run(self, ctx: Any) -> list[StageResult]:
        """Execute all stages in sequence.  Stops on first FAILED or BLOCKED."""
        results: list[StageResult] = []
        skipped = False

        for stage in self._stages:
            if skipped:
                result = StageResult(
                    stage_name=stage.stage_name,
                    status=StageStatus.SKIPPED,
                    error="previous stage failed or was blocked",
                )
                results.append(result)
                continue

            logger.info("pipeline: starting stage %s", stage.stage_name)
            result = stage.run(ctx)
            results.append(result)

            if result.status in (StageStatus.FAILED, StageStatus.BLOCKED):
                logger.warning("pipeline: stage %s %s — skipping remaining stages", stage.stage_name, result.status.name)
                skipped = True

        return results

    def summary(self, results: list[StageResult]) -> dict[str, Any]:
        """Generate a summary of pipeline execution."""
        total_duration = sum(r.duration_seconds for r in results)
        return {
            "schema_version": STAGE_SCHEMA_VERSION,
            "total_stages": len(results),
            "completed": sum(1 for r in results if r.status == StageStatus.COMPLETED),
            "failed": sum(1 for r in results if r.status == StageStatus.FAILED),
            "skipped": sum(1 for r in results if r.status == StageStatus.SKIPPED),
            "total_duration_seconds": round(total_duration, 3),
            "stages": [r.to_dict() for r in results],
            "overall": "PASS"
                if all(r.status == StageStatus.COMPLETED for r in results)
                else "FAIL",
        }


# ═══════════════════════════════════════════════════════════════════════════
# Pre-built pipeline configurations
# ═══════════════════════════════════════════════════════════════════════════

def build_full_pipeline() -> PipelineStagesOrchestrator:
    """Build the complete six-stage pipeline."""
    return (
        PipelineStagesOrchestrator()
        .add_stage(GenerationStage())
        .add_stage(LocalScoringStage())
        .add_stage(OfficialValidationStage())
        .add_stage(SimulationStage())
        .add_stage(QualityGateStage())
        .add_stage(SubmissionStage())
    )


def build_local_only_pipeline() -> PipelineStagesOrchestrator:
    """Build a local-only pipeline (no BRAIN API calls)."""
    return (
        PipelineStagesOrchestrator()
        .add_stage(GenerationStage())
        .add_stage(LocalScoringStage())
        .add_stage(QualityGateStage())
    )
