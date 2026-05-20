"""Official pre-backtest validation service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.models import Candidate

from .candidate_pool import blocked_gate


ProgressCallback = Callable[[str, int, int, str, str], None]
EventCallback = Callable[..., None]
LifecycleCallback = Callable[[Candidate, str, str], None]
HaltCallback = Callable[[str], None]


@dataclass
class OfficialValidationOutcome:
    valid: list[Candidate] = field(default_factory=list)
    attempted: int = 0
    passed: int = 0
    halted: bool = False
    halt_reason: str = ""


@dataclass
class OfficialValidationService:
    api: BrainAPI
    settings_payload: dict
    progress: ProgressCallback
    event: EventCallback
    record_lifecycle: LifecycleCallback
    halt_official_calls: HaltCallback

    def validate(self, candidates: list[Candidate]) -> OfficialValidationOutcome:
        outcome = OfficialValidationOutcome()
        total = len(candidates)
        for index, candidate in enumerate(candidates, start=1):
            self.progress(
                "official_validation",
                index - 1,
                total,
                f"回测前预检 {index}/{total}: {candidate.alpha_id}",
                candidate.alpha_id,
            )
            try:
                result = self.api.validate_expression(candidate.expression, self.settings_payload)
            except BrainAPIError as exc:
                if exc.status_code == 429:
                    reason = f"official validation rate limit reached; retry later: {exc}"
                    self.halt_official_calls(reason)
                    candidate.lifecycle_status = "official_validation_deferred_rate_limit"
                    candidate.gate = blocked_gate("OFFICIAL_VALIDATION_DEFERRED_RATE_LIMIT", [reason])
                    self.event("official_validation_deferred", reason, candidate.alpha_id, level="WARN")
                    outcome.halted = True
                    outcome.halt_reason = reason
                    break
                raise

            candidate.validation = result
            outcome.attempted += 1
            if result.get("status") == "PASS":
                candidate.lifecycle_status = "official_validation_passed"
                outcome.passed += 1
                outcome.valid.append(candidate)
            else:
                candidate.lifecycle_status = "official_validation_failed"
                candidate.gate = blocked_gate("OFFICIAL_VALIDATION_FAILED", result.get("errors", ["validation failed"]))
                self.event("official_validation_failed", "; ".join(candidate.gate["failed_reasons"]), candidate.alpha_id)

            self.record_lifecycle(candidate, "official_validation", result.get("status", ""))
            self.progress(
                "official_validation",
                index,
                total,
                f"回测前预检 {index}/{total} 完成。",
                candidate.alpha_id,
            )
        return outcome
