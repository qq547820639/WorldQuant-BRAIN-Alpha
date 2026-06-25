"""Cycle phase mixin for ``AlphaResearchPipeline``.

Extracted from the original ``pipeline.py`` monolith. Holds per-cycle
helpers: dataset selection, assistant guidance application, live submit
readiness gate, and the simulation+backtest phase driver.
"""

from __future__ import annotations

import logging

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from ..guidance import ensure_assistant_guidance_digest
from ..memory import ResearchMemory
from ..pipeline_helpers import (
    attach_assistant_guidance as _attach_assistant_guidance,
    assistant_guidance_for_generator as _assistant_guidance_for_generator,
    rank_candidates,
)
from ..pipeline_state import CycleState
# Import the module (not the function) so test monkeypatching of
# ``brain_alpha_ops.research.pipeline_submission_gate.live_submit_readiness_hard_gate``
# takes effect at call time.
from .. import pipeline_submission_gate

# Preserve the original ``brain_alpha_ops.research.pipeline`` logger name so
# downstream log filters and test caplog assertions keep working after the
# monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline")


class PipelineCycleMixin:
    """Per-cycle phase methods extracted from ``run()``."""

    def _cycle_select_dataset(self, cycle: int) -> "_Phase":
        """Select dataset for this cycle. Returns _Phase.SKIP or _Phase.BREAK on failure."""
        result = self._dataset_selection_service().select()
        if result.dataset_id:
            self._active_dataset_id = result.dataset_id
            # Item 7: Log warning when dataset changes (universe switch)
            if self._active_dataset_id and self._active_dataset_id != getattr(self, "_last_dataset_id", ""):
                if hasattr(self, "_last_dataset_id") and self._last_dataset_id:
                    logger.info(
                        "universe switch detected: %s -> %s (same expressions across universes "
                        "will be re-evaluated; verify this is intentional)",
                        self._last_dataset_id, self._active_dataset_id,
                    )
                self._last_dataset_id = self._active_dataset_id
        if result.should_continue:
            return self._Phase.CONTINUE
        if result.should_skip:
            return self._Phase.SKIP
        return self._Phase.BREAK

    def _apply_assistant_guidance(self, cycle: int) -> dict | None:
        self._active_assistant_guidance = None
        if not getattr(self.config.budget, "use_assistant_guidance", True):
            return None

        # P2-4: return cached guidance for up to 5 cycles to avoid
        # re-reading the JSONL file on every single cycle.
        if (self._cached_assistant_guidance is not None
                and cycle - self._cached_guidance_at_cycle < 5):
            return self._cached_assistant_guidance

        try:
            min_confidence = float(getattr(self.config.budget, "assistant_guidance_min_confidence", 0.6) or 0.0)
            guidance = ResearchMemory(self.config.storage_dir).latest_assistant_guidance(
                min_confidence=min_confidence,
            )
            if not guidance.get("usable"):
                return None
            guidance = ensure_assistant_guidance_digest(guidance)
            generator_guidance = _assistant_guidance_for_generator(guidance)
            if not generator_guidance:
                return None
            self.generator.set_experience_guidance(generator_guidance)
            self._active_assistant_guidance = guidance
            self.services.runtime._event(
            "assistant_guidance_applied",
            f"Cycle {cycle}: Applied persisted assistant guidance "
            f"(confidence={guidance.get('confidence', 0.0)}; "
            f"operators={generator_guidance.get('top_operators', [])[:5]}; "
            f"windows={generator_guidance.get('preferred_windows', [])[:5]}).",
                level="INFO",
                data={
                    "guidance_source": guidance.get("source", ""),
                    "guidance_digest": guidance.get("guidance_digest", ""),
                    "persisted_at": guidance.get("persisted_at", ""),
                    "confidence": guidance.get("confidence", 0.0),
                    "historical_outcome_status": guidance.get("historical_outcome_status", "unknown"),
                    "historical_outcome": guidance.get("historical_outcome", {}),
                    "top_fields": guidance.get("top_fields", [])[:10],
                    "top_operators": guidance.get("top_operators", [])[:10],
                    "preferred_windows": guidance.get("preferred_windows", [])[:10],
                },
            )
            self._cached_assistant_guidance = guidance
            self._cached_guidance_at_cycle = cycle
            return guidance
        except Exception as exc:
            # P2-4: invalidate cache on exception so the next cycle re-reads
            self._cached_assistant_guidance = None
            logger.warning("Assistant guidance unavailable in cycle %s: %s", cycle, redact_error_message(exc))
            logger.debug("Assistant guidance traceback in cycle %s", cycle, exc_info=True)
        return None

    def _attach_active_assistant_guidance(self, candidates: list[Candidate]) -> None:
        guidance = self._active_assistant_guidance
        if not guidance:
            return
        for candidate in candidates:
            _attach_assistant_guidance(candidate, guidance)

    def _live_submit_readiness_gate(self, candidate: Candidate) -> dict:
        return pipeline_submission_gate.live_submit_readiness_hard_gate(
            candidate.to_dict(),
            RunConfig(ops=self.config),
            candidate.official_alpha_id,
        )

    def _cycle_simulate_and_submit(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        accepted_candidates: list[Candidate],
        submitted_this_run: int,
        auto_submit: bool,
    ) -> tuple[int, bool | None]:
        """Execute the simulation+backtest+strategy phase for one cycle.

        Returns (submitted_this_run, abort) where:
          abort=True  → caller should break
          abort=False → caller should continue
          abort=None  → normal flow, caller should proceed
        """
        # ── Gate guard: consolidated official_calls_halted check (P2-05) ──
        if self.official_calls_halted and self.official_halt_cycle != cycle:
            self.services.runtime._maybe_resume_official_calls()
        if self.official_calls_halted:
            pool = rank_candidates(list(pool_by_expression.values()))
            if not self.services.runtime._defer_official_cycle(cycle, pool, accepted_candidates, archive_stats):
                return submitted_this_run, True   # break
            return submitted_this_run, False       # continue

        # Poll existing backtests
        submitted_this_run = self.services.backtest_flow._poll_due_backtests(
            cycle, pool_by_expression, accepted_candidates,
            archive_stats, archive_samples, blocked_expressions,
            submitted_this_run, auto_submit,
        )

        # Validate candidates for open backtest slots
        official_workflow = self._official_workflow_service()
        official_workflow.validate_slots(
            cycle, pool_by_expression, accepted_candidates,
            archive_stats, blocked_expressions,
        )

        # Fill backtest slots
        cyc_state = CycleState(
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
        )
        official_workflow.fill_slots(cycle, cyc_state)
        submitted_this_run = official_workflow.poll_due(
            cycle, pool_by_expression, accepted_candidates,
            archive_stats, archive_samples, blocked_expressions,
            submitted_this_run, auto_submit, force_initial=True,
        )

        if not self.official_calls_halted:
            official_workflow.fill_slots(cycle, cyc_state)

        self.services.runtime._archive(archive_stats, archive_samples, self.services.candidate_pool._prune_pool(pool_by_expression))
        return submitted_this_run, None
