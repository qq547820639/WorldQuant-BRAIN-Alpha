"""Guards official API calls using local observability signals."""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from brain_alpha_ops.models import Candidate

from .candidate_pool import blocked_gate
from .expression_ast import expression_key


GUARD_SCHEMA = "observability_official_call_guard.v1"


@dataclass
class OfficialCallGuard:
    guard: dict = field(default_factory=dict)

    def snapshot(self) -> dict:
        guard = self.guard if isinstance(self.guard, dict) else {}
        blocked_candidates = guard.get("blocked_candidates") if isinstance(guard.get("blocked_candidates"), list) else []
        return {
            "schema_version": GUARD_SCHEMA,
            "blocked_count": int(guard.get("blocked_count") or 0),
            "validation_blocked_count": int(guard.get("validation_blocked_count") or 0),
            "simulation_blocked_count": int(guard.get("simulation_blocked_count") or 0),
            "phase_counts": dict(guard.get("phase_counts") or {}),
            "last_blocked_alpha_id": str(guard.get("last_blocked_alpha_id") or ""),
            "last_blocked_phase": str(guard.get("last_blocked_phase") or ""),
            "last_blocked_expression": str(guard.get("last_blocked_expression") or ""),
            "last_blocked_at": guard.get("last_blocked_at"),
            "blocked_candidates": [dict(row) for row in blocked_candidates[-10:] if isinstance(row, dict)],
        }

    def should_block(self, candidate: Candidate, guidance: dict | None) -> bool:
        guidance = guidance if isinstance(guidance, dict) else {}
        if not guidance.get("active"):
            return False
        duplicate_keys = set(str(item) for item in guidance.get("top_duplicate_expressions") or [] if str(item))
        duplicate_keys.update(str(item) for item in guidance.get("top_duplicate_fingerprints") or [] if str(item))
        if not duplicate_keys:
            return False
        return expression_key(candidate.expression) in duplicate_keys

    def block(
        self,
        candidate: Candidate,
        *,
        phase: str,
        guidance: dict | None,
        blocked_at: float | None = None,
    ) -> dict | None:
        if not self.should_block(candidate, guidance):
            return None
        candidate_key = expression_key(candidate.expression)
        reason = "observability duplicate expression history blocked official call before " + phase
        candidate.lifecycle_status = "observability_duplicate_blocked"
        candidate.gate = blocked_gate("OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED", [reason])
        candidate.submission["observability_duplicate_blocked_phase"] = phase
        guard_summary = self.record_block(
            candidate,
            phase=phase,
            expression_canonical=candidate_key,
            blocked_at=blocked_at,
        )
        return {
            "blocked": True,
            "phase": phase,
            "reason": reason,
            "expression_canonical": candidate_key,
            "guard": guard_summary,
        }

    def record_block(
        self,
        candidate: Candidate,
        *,
        phase: str,
        expression_canonical: str,
        blocked_at: float | None = None,
    ) -> dict:
        guard = self.snapshot()
        phase_counts = dict(guard.get("phase_counts") or {})
        phase_counts[phase] = int(phase_counts.get(phase) or 0) + 1
        guard["blocked_count"] = int(guard.get("blocked_count") or 0) + 1
        guard["validation_blocked_count"] = int(guard.get("validation_blocked_count") or 0) + (
            1 if phase == "official_validation" else 0
        )
        guard["simulation_blocked_count"] = int(guard.get("simulation_blocked_count") or 0) + (
            1 if phase == "official_simulation" else 0
        )
        guard["phase_counts"] = phase_counts
        guard["last_blocked_alpha_id"] = candidate.alpha_id
        guard["last_blocked_phase"] = phase
        guard["last_blocked_expression"] = expression_canonical
        guard["last_blocked_at"] = time.time() if blocked_at is None else blocked_at
        blocked_candidates = list(guard.get("blocked_candidates") or [])
        blocked_candidates.append(
            {
                "alpha_id": candidate.alpha_id,
                "phase": phase,
                "expression_canonical": expression_canonical[:160],
                "family": candidate.family,
                "score": round(float(candidate.scorecard.get("total_score", 0.0) or 0.0), 4),
                "blocked_at": guard["last_blocked_at"],
            }
        )
        guard["blocked_candidates"] = blocked_candidates[-10:]
        self.guard = guard
        return self.snapshot()
