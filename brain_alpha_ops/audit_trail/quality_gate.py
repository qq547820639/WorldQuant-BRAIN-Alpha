"""Quality gate auto-interception (Workstream B4.2).

Detects and auto-archives candidates exhibiting anti-overfit violations:
- Highly similar expressions (skeleton convergence)
- Parameter micro-tuning (only numeric changes from parent)
- Duplicate submissions (same expression already submitted)
- Abnormally high-frequency failure retries

Each interception records a ``gate_decision`` audit entry and transitions
the candidate to ``gate_rejected`` via the lifecycle state machine.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from brain_alpha_ops.audit_trail.lifecycle_writer import record_gate_decision
from brain_alpha_ops.candidate_lifecycle import LifecycleState, transition
from brain_alpha_ops.research.expression_diversity import ExpressionDiversityGuard

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate

logger = logging.getLogger(__name__)


@dataclass
class GateResult:
    """Result of a single quality-gate check."""
    passed: bool
    gate_name: str
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed, "gate_name": self.gate_name,
            "reason": self.reason, "details": self.details,
        }


class QualityGateInterceptor:
    """Auto-interception for anti-overfit quality gates (B4.2).

    Stateful: tracks submitted expressions and failure retry counts across
    calls. Thread-safe.
    """

    SIMILAR_EXPRESSION_THRESHOLD: float = 0.30
    RETRY_THRESHOLD: int = 5
    _NUMERIC_RE = re.compile(r"\b\d+(?:\.\d+)?\b")

    def __init__(self, *, diversity_guard: ExpressionDiversityGuard | None = None) -> None:
        self._guard = diversity_guard or ExpressionDiversityGuard()
        self._submitted: set[str] = set()
        self._retry_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    # --- Individual checks --------------------------------------------------

    def check_similar_expression(
        self, expression: str, pool_expressions: list[str],
    ) -> GateResult:
        """Detect skeleton convergence (高度相似表达式)."""
        if not expression or not pool_expressions:
            return GateResult(True, "similar_expression")
        try:
            is_conv = self._guard.is_converged(expression, pool_expressions)
            if is_conv:
                skel = self._guard.skeleton(expression)
                concentration = sum(
                    1 for e in pool_expressions
                    if self._guard.skeleton(e) == skel
                ) / max(len(pool_expressions), 1)
                return GateResult(
                    False, "similar_expression",
                    f"expression skeleton concentration {concentration:.0%} exceeds threshold",
                    {"skeleton": skel, "concentration": round(concentration, 4),
                     "threshold": self.SIMILAR_EXPRESSION_THRESHOLD},
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("similar_expression check skipped: %s", exc)
        return GateResult(True, "similar_expression")

    def check_parameter_micro_tuning(
        self, expression: str, parent_expression: str,
    ) -> GateResult:
        """Detect parameter micro-tuning (参数微调刷分).

        Flags candidates whose skeleton matches the parent's skeleton but
        only numeric values differ — i.e., no structural change, just
        window/parameter tweaks.
        """
        if not expression or not parent_expression or expression == parent_expression:
            return GateResult(True, "parameter_micro_tuning")
        try:
            parent_skel = self._guard.skeleton(parent_expression)
            child_skel = self._guard.skeleton(expression)
            if parent_skel != child_skel:
                return GateResult(True, "parameter_micro_tuning")
            parent_nums = self._NUMERIC_RE.findall(parent_expression)
            child_nums = self._NUMERIC_RE.findall(expression)
            if parent_nums == child_nums:
                return GateResult(True, "parameter_micro_tuning")
            return GateResult(
                False, "parameter_micro_tuning",
                "expression is a parameter micro-tuning of parent (same skeleton, different numbers only)",
                {"parent_skeleton": parent_skel, "parent_numbers": parent_nums,
                 "child_numbers": child_nums},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("parameter_micro_tuning check skipped: %s", exc)
        return GateResult(True, "parameter_micro_tuning")

    def check_duplicate_submission(self, expression: str) -> GateResult:
        """Detect duplicate submissions (重复提交)."""
        if not expression:
            return GateResult(True, "duplicate_submission")
        normalized = " ".join(expression.split()).lower()
        with self._lock:
            if normalized in self._submitted:
                return GateResult(
                    False, "duplicate_submission",
                    "expression was already submitted",
                    {"expression_hash": hash(normalized)},
                )
        return GateResult(True, "duplicate_submission")

    def check_high_frequency_retry(self, alpha_id: str) -> GateResult:
        """Detect abnormally high-frequency failure retries (异常高频失败重试)."""
        if not alpha_id:
            return GateResult(True, "high_frequency_retry")
        with self._lock:
            count = self._retry_counts.get(alpha_id, 0)
        if count >= self.RETRY_THRESHOLD:
            return GateResult(
                False, "high_frequency_retry",
                f"failure retry count {count} exceeds threshold {self.RETRY_THRESHOLD}",
                {"retry_count": count, "threshold": self.RETRY_THRESHOLD},
            )
        return GateResult(True, "high_frequency_retry")

    # --- State mutation -----------------------------------------------------

    def record_submission(self, expression: str) -> None:
        """Record a submitted expression for duplicate detection."""
        if not expression:
            return
        normalized = " ".join(expression.split()).lower()
        with self._lock:
            self._submitted.add(normalized)

    def record_failure(self, alpha_id: str) -> int:
        """Increment failure count for an alpha. Returns new count."""
        if not alpha_id:
            return 0
        with self._lock:
            self._retry_counts[alpha_id] = self._retry_counts.get(alpha_id, 0) + 1
            return self._retry_counts[alpha_id]

    def reset(self) -> None:
        """Clear all tracked state (e.g., between pipeline runs)."""
        with self._lock:
            self._submitted.clear()
            self._retry_counts.clear()

    # --- Combined interception ---------------------------------------------

    def intercept(
        self, candidate: "Candidate",
        *,
        pool_expressions: list[str] | None = None,
        parent_expression: str | None = None,
    ) -> dict[str, Any]:
        """Run all quality-gate checks. Auto-archive via lifecycle if intercepted.

        Returns a dict with ``intercepted`` (bool), ``results`` (list of
        GateResult dicts), and ``reason`` (combined failure reason).
        """
        expression = str(getattr(candidate, "expression", "") or "")
        alpha_id = str(getattr(candidate, "alpha_id", "") or "")
        parent_expr = parent_expression or str(getattr(candidate, "parent_expression", "") or "")
        pool = list(pool_expressions or [])

        results = [
            self.check_similar_expression(expression, pool),
            self.check_parameter_micro_tuning(expression, parent_expr),
            self.check_duplicate_submission(expression),
            self.check_high_frequency_retry(alpha_id),
        ]
        failed = [r for r in results if not r.passed]
        intercepted = bool(failed)
        reason = "; ".join(f"{r.gate_name}: {r.reason}" for r in failed) if failed else ""

        if intercepted:
            try:
                record_gate_decision(
                    alpha_id=alpha_id, gate_name="quality_gate_interception",
                    passed=False, reason=reason,
                    attribution={r.gate_name: r.details for r in failed},
                    context={"all_results": [r.to_dict() for r in results]},
                )
                transition(
                    candidate, LifecycleState.gate_rejected,
                    reason=f"quality_gate_intercepted:{reason}",
                    legacy_status="quality_gate_intercepted",
                    context={"trigger_rule": "anti_overfit_quality_gate",
                             "failed_gates": [r.gate_name for r in failed]},
                )
                logger.info(
                    "quality gate intercepted %s: %s", alpha_id, reason,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("quality gate interception writeback skipped: %s", exc)

        return {
            "intercepted": intercepted,
            "reason": reason,
            "results": [r.to_dict() for r in results],
            "alpha_id": alpha_id,
        }


# Module-level singleton for pipeline-wide use.
_interceptor: QualityGateInterceptor | None = None
_interceptor_lock = threading.Lock()


def get_quality_gate_interceptor() -> QualityGateInterceptor:
    """Return the module-level singleton interceptor."""
    global _interceptor
    if _interceptor is None:
        with _interceptor_lock:
            if _interceptor is None:
                _interceptor = QualityGateInterceptor()
    return _interceptor
