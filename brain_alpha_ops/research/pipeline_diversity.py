"""Pipeline mixin that integrates ExpressionDiversityGuard into the generation loop.

This mixin monitors skeleton convergence during alpha generation and triggers
forced diversification when the pool becomes structurally concentrated.

Integration point: added as a mixin to AlphaResearchPipeline in pipeline.py.
"""

from __future__ import annotations

from typing import Any


class PipelineDiversityMixin:
    """Mixin that adds expression diversity monitoring to the pipeline.

    Usage:
        class AlphaResearchPipeline(..., PipelineDiversityMixin):
            pass
    """

    _diversity_guard: Any = None
    _diversity_alerted: set[str] = set()
    _diversity_stall_count: int = 0
    _diversity_max_stall: int = 5

    def _init_diversity_guard(self) -> None:
        """Lazy-init the expression diversity guard."""
        if self._diversity_guard is not None:
            return
        try:
            from brain_alpha_ops.research.expression_diversity import ExpressionDiversityGuard

            self._diversity_guard = ExpressionDiversityGuard(
                max_skeleton_concentration=0.30,
                min_unique_skeletons=3,
            )
        except ImportError:
            self._diversity_guard = False  # Sentinel: module not available

    def _check_expression_diversity(
        self,
        pool_expressions: list[str],
        new_expression: str | None = None,
    ) -> dict[str, Any]:
        """Check expression diversity and return convergence status.

        Args:
            pool_expressions: existing expressions in the candidate pool.
            new_expression: optional new expression to check for convergence.

        Returns:
            dict with keys: is_converged, report, recommended_action
        """
        self._init_diversity_guard()
        if not self._diversity_guard:
            return {"is_converged": False, "report": {}, "recommended_action": "none"}

        report = self._diversity_guard.analyze_pool(pool_expressions)

        # Check if the new expression would cause convergence
        if new_expression and pool_expressions:
            would_converge = self._diversity_guard.is_converged(
                new_expression, pool_expressions
            )
        else:
            would_converge = report.is_converged

        action = "none"
        if would_converge:
            self._diversity_stall_count += 1
            if self._diversity_stall_count >= self._diversity_max_stall:
                action = "force_diversify"
            else:
                action = "diversity_warning"

        return {
            "is_converged": would_converge,
            "report": report.to_dict() if hasattr(report, "to_dict") else {},
            "recommended_action": action,
        }

    def _get_diversification_strategies(
        self,
        converged_expression: str,
        pool_expressions: list[str] | None = None,
    ) -> list[str]:
        """Get diversification strategies when convergence is detected.

        Args:
            converged_expression: the expression causing convergence.
            pool_expressions: optional existing pool for context.

        Returns:
            list of diversification strategy descriptions.
        """
        self._init_diversity_guard()
        if not self._diversity_guard:
            return []

        strategies = self._diversity_guard.force_diversify(
            converged_expression,
            pool_expressions=pool_expressions,
            max_attempts=8,
        )
        return strategies

    def _reset_diversity_stall(self) -> None:
        """Reset the diversity stall counter."""
        self._diversity_stall_count = 0

    def _record_diversity_alert(self, cycle: int, report: dict) -> None:
        """Record a diversity alert for this cycle."""
        alert_key = f"cycle_{cycle}_skeleton_{report.get('most_common_skeleton', 'unknown')[:20]}"
        if alert_key in self._diversity_alerted:
            return
        self._diversity_alerted.add(alert_key)

        # Trim old alerts
        if len(self._diversity_alerted) > 100:
            self._diversity_alerted = set(list(self._diversity_alerted)[-50:])

        event_data: dict[str, Any] = {
            "cycle": cycle,
            "unique_skeletons": report.get("unique_skeletons", 0),
            "convergence_rate": report.get("convergence_rate", 0),
            "most_common_skeleton": report.get("most_common_skeleton", ""),
            "stall_count": self._diversity_stall_count,
        }
        if hasattr(self, "_event"):
            self._event(
                "expression_diversity_alert",
                f"Cycle {cycle}: expression skeleton convergence detected "
                f"(rate={report.get('convergence_rate', 0):.3f}, "
                f"unique={report.get('unique_skeletons', 0)})",
                level="WARN",
                data=event_data,
            )
