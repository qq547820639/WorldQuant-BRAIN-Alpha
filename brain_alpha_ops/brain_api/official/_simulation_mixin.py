"""Simulation submission and polling mixin for OfficialBrainAPI."""

from __future__ import annotations

from brain_alpha_ops.types import BrainAPIResponse


class _OfficialSimulationMixin:
    """Simulation-related thin wrappers delegating to ``self._simulation_submission``."""

    def submit_simulation(self, expression: str, settings: dict) -> str:
        """Submit an alpha expression for simulation.

        Args:
            expression: Alpha expression (e.g., "rank(ts_delta(close, 20))")
            settings: Simulation settings (region, delay, universe, etc.)

        Returns:
            Simulation ID for polling results

        Raises:
            BrainAPIError: If submission fails
        """
        return self._simulation_submission.submit_simulation(expression, settings)

    def poll_simulation(self, simulation_id: str) -> str:
        """Poll simulation status once.

        Args:
            simulation_id: ID from submit_simulation()

        Returns:
            Status string: "RUNNING", "COMPLETED", or "FAILED"
        """
        return self._simulation_submission.poll_simulation(simulation_id)

    def fetch_result(self, simulation_id: str) -> BrainAPIResponse:
        """Fetch simulation results after completion.

        Args:
            simulation_id: ID from submit_simulation()

        Returns:
            BrainAPIResponse with simulation_id, alpha_id, metrics, and raw data
        """
        return self._simulation_submission.fetch_result(simulation_id)

    def concurrent_simulate(self, alphas, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        """Simulate multiple alphas concurrently.

        Args:
            alphas: List of (expression, settings) tuples or dicts
            concurrency: Max concurrent simulations
            return_exceptions: If True, return exceptions instead of raising

        Returns:
            List of simulation results
        """
        return self._simulation_submission.concurrent_simulate(
            alphas,
            concurrency=concurrency,
            return_exceptions=return_exceptions,
        )

    def concurrent_check(self, alpha_ids, concurrency: int = 3, *, return_exceptions: bool = False) -> list:
        return self._simulation_submission.concurrent_check(
            alpha_ids,
            concurrency=concurrency,
            return_exceptions=return_exceptions,
        )

    def check_alpha(self, alpha_id: str) -> BrainAPIResponse:
        """Check alpha submission readiness.

        Args:
            alpha_id: BRAIN alpha ID

        Returns:
            BrainAPIResponse with status ("PASSED"/"FAILED"), checks, and details
        """
        return self._simulation_submission.check_alpha(alpha_id)

    def submit_alpha(self, alpha_id: str, expression: str, settings: dict, *, bodyless: bool = True) -> BrainAPIResponse:
        """Submit alpha to BRAIN platform.

        WARNING: This performs a REAL submission. In production, use the
        web console's pre-submit review + HIL confirmation flow instead.

        Args:
            alpha_id: BRAIN alpha ID
            expression: Alpha expression
            settings: Submission settings
            bodyless: Must be True (body sent via pre-submit check)

        Returns:
            BrainAPIResponse with submission status and details

        Raises:
            BrainAPIError: If submission is blocked or fails
        """
        return self._simulation_submission.submit_alpha(alpha_id, expression, settings, bodyless=bodyless)

    def check_prod_correlation(
        self,
        expression: str,
        settings: dict | None = None,
    ) -> dict:
        """Check correlation with existing production alphas.

        Args:
            expression: Alpha expression to check
            settings: Optional settings override

        Returns:
            Dict with max_correlation, related_alphas, warning
        """
        return self._simulation_submission.check_prod_correlation(expression, settings)

    def poll_until_complete(self, simulation_id: str) -> str:
        """Poll simulation until completion or timeout.

        Args:
            simulation_id: ID from submit_simulation()

        Returns:
            "COMPLETED", "FAILED", or "TIMEOUT"
        """
        return self._simulation_submission.poll_until_complete(simulation_id)
