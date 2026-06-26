"""Simulation and check operations mixin for BrowserExecutionAdapter.

Holds the ``simulate_alpha`` and ``check_alpha`` Protocol methods, which
drive the browser through the Alpha creation → simulation flow and the
pre-submission Alpha detail/check flow respectively.

Combined with :class:`BrowserExecutionAdapterBase` in the package
``__init__`` to form the final :class:`BrowserExecutionAdapter`.

Extracted from the former ``execution_adapter.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

from typing import Any

from ._state import _DEFAULT_NAV_TIMEOUT_MS, logger


class _SimulateMixin:
    """``simulate_alpha`` and ``check_alpha`` Protocol methods."""

    def simulate_alpha(self, expression: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Simulate an Alpha expression via real browser interaction.

        Full browser flow: navigate to creation page → fill expression →
        configure settings → trigger simulation → collect results.

        Args:
            expression: BRAIN Alpha expression string.
            settings: dict with optional keys like "universe", "delay", etc.

        Returns:
            {"ok": bool, "expression": str, "results": ..., "evidence": ...}
        """
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated", "step": "simulate.not_authenticated"}

        # Step 1: Navigate
        nav = self.runner.navigate_to_alpha_creation()
        if not nav.get("ok"):
            return {"ok": False, "error": "Navigation failed", "details": nav}

        # Step 2: Fill expression
        fill = self.runner.fill_expression(expression)
        if not fill.get("ok"):
            return {"ok": False, "error": "Expression fill failed", "details": fill}

        # Step 3: Configure settings if provided
        if settings:
            universe = settings.get("universe", "")
            delay = settings.get("delay", "")
            if universe:
                try:
                    page = getattr(self.runner, "_page", None)
                    if page is not None:
                        page.fill(
                            'input[name="universe"], select[name="universe"]',
                            universe,
                        )
                except (AttributeError, Exception):
                    logger.warning("Could not set universe selector")
            if delay:
                try:
                    page = getattr(self.runner, "_page", None)
                    if page is not None:
                        page.fill(
                            'input[name="delay"], select[name="delay"]',
                            str(delay),
                        )
                except (AttributeError, Exception):
                    logger.warning("Could not set delay selector")

        # Step 4: Trigger simulation
        sim = self.runner.trigger_simulation()
        if not sim.get("ok"):
            return {"ok": False, "error": "Simulation trigger failed", "details": sim}

        # Step 5: Collect results
        results = self.runner.check_results()
        return {
            "ok": results.get("ok", False),
            "expression": expression,
            "results": results.get("page_text_preview", ""),
            "evidence": self.get_evidence(),
        }

    def check_alpha(self, alpha_id: str) -> dict[str, Any]:
        """Run pre-submission checks on an Alpha via browser.

        Navigates to the Alpha detail/check page and collects quality output.

        Args:
            alpha_id: BRAIN Alpha identifier.

        Returns:
            {"ok": bool, "alpha_id": str, "checks": ..., "evidence": ...}
        """
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated", "step": "check.not_authenticated", "alpha_id": alpha_id}

        # Navigate to the Alpha detail page
        try:
            page = getattr(self.runner, "_page", None)
            if page is None:
                return {"ok": False, "error": "Browser page not initialized", "alpha_id": alpha_id}
            page.goto(
                f"{self.base_url}/alpha/{alpha_id}",
                wait_until="domcontentloaded",
                timeout=_DEFAULT_NAV_TIMEOUT_MS,
            )
        except Exception as e:
            return {"ok": False, "error": f"Navigation failed: {e}", "alpha_id": alpha_id}

        self.runner._take_screenshot(f"alpha_check_{alpha_id}")
        self.runner._snapshot_dom(f"alpha_check_{alpha_id}")

        # Extract check results from page
        try:
            page = getattr(self.runner, "_page", None)
            if page is None:
                return {
                    "ok": False,
                    "alpha_id": alpha_id,
                    "error": "Browser page not initialized",
                }
            page_text = page.inner_text("body")
            return {
                "ok": True,
                "alpha_id": alpha_id,
                "checks": page_text[:2000],
                "evidence": self.get_evidence(),
            }
        except Exception as e:
            return {
                "ok": False,
                "alpha_id": alpha_id,
                "error": f"Failed to extract check results: {e}",
            }
