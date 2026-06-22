"""BrowserExecutionAdapter — bridges BrainBrowserRunner → AlphaExecutionBackend Protocol.

Wraps Playwright-driven browser interactions behind the execution_backend.AlphaExecutionBackend
Protocol, so the production pipeline can transparently switch between browser-first and API
execution paths.

Usage::

    from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter
    from brain_alpha_ops.execution_backend import AlphaExecutionBackend

    backend: AlphaExecutionBackend = BrowserExecutionAdapter(
        username="user@example.com",
        password="secret",
    )
    with backend:
        backend.authenticate({"username": "...", "password": "..."})
        result = backend.simulate_alpha("rank(returns)", {})
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.execution_backend import ExecutionEvidence
from brain_alpha_ops.browser.brain_ui_runner import BrainBrowserRunner

logger = logging.getLogger(__name__)


@dataclass
class BrowserExecutionAdapter:
    """Production adapter: browser-first executor implementing AlphaExecutionBackend."""

    username: str = ""
    password: str = ""
    base_url: str = "https://brain.worldquant.com"
    headless: bool = True
    evidence_dir: str = "artifacts"

    # Internal state — managed by context manager
    _runner: BrainBrowserRunner | None = field(default=None, init=False, repr=False)
    _authenticated: bool = field(default=False, init=False, repr=False)

    # ---- Context manager ----

    def __enter__(self) -> BrowserExecutionAdapter:
        self._runner = BrainBrowserRunner(
            base_url=self.base_url,
            headless=self.headless,
            evidence_dir=self.evidence_dir,
        )
        self._runner.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._runner is not None:
            self._runner.__exit__(exc_type, exc, tb)
            self._runner = None
        self._authenticated = False

    @property
    def runner(self) -> BrainBrowserRunner:
        if self._runner is None:
            raise RuntimeError(
                "BrowserExecutionAdapter must be used as a context manager "
                "(with BrowserExecutionAdapter(...) as backend: ...)"
            )
        return self._runner

    # ---- AlphaExecutionBackend Protocol methods ----

    def authenticate(self, credentials: dict[str, str]) -> dict[str, Any]:
        """Login to BRAIN via real browser interaction.

        Args:
            credentials: dict with "username" and "password" keys.

        Returns:
            {"ok": bool, "step": str, "screenshots": [...]}
        """
        username = credentials.get("username", self.username)
        password = credentials.get("password", self.password)

        if not username or not password:
            return {"ok": False, "error": "Missing credentials", "step": "auth.missing_credentials"}

        result = self.runner.login(username, password)
        self._authenticated = result.get("ok", False)
        return result

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
                    self.runner._page.fill(
                        'input[name="universe"], select[name="universe"]',
                        universe,
                    )
                except Exception:
                    logger.warning("Could not set universe selector")
            if delay:
                try:
                    self.runner._page.fill(
                        'input[name="delay"], select[name="delay"]',
                        str(delay),
                    )
                except Exception:
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
            return {"ok": False, "error": "Not authenticated", "step": "check.not_authenticated"}

        # Navigate to the Alpha detail page
        try:
            self.runner._page.goto(
                f"{self.base_url}/alpha/{alpha_id}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            return {"ok": False, "error": f"Navigation failed: {e}", "alpha_id": alpha_id}

        self.runner._take_screenshot(f"alpha_check_{alpha_id}")
        self.runner._snapshot_dom(f"alpha_check_{alpha_id}")

        # Extract check results from page
        try:
            page_text = self.runner._page.inner_text("body")
            return {
                "ok": True,
                "alpha_id": alpha_id,
                "checks": page_text[:3000],
                "evidence": self.get_evidence(),
            }
        except Exception as e:
            return {
                "ok": False,
                "alpha_id": alpha_id,
                "error": f"Failed to extract check results: {e}",
            }

    def submit_alpha(self, alpha_id: str) -> dict[str, Any]:
        """Submit an Alpha via browser interaction.

        **Security note**: This method navigates the real BRAIN submit flow.
        It is gated upstream by ``REAL_SUBMIT_DISABLED_WEB_FLOW`` and should
        only be called after explicit human confirmation in the browser UI.

        Args:
            alpha_id: BRAIN Alpha identifier to submit.

        Returns:
            {"ok": bool, "alpha_id": str, "confirmation": ...}
        """
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated", "step": "submit.not_authenticated"}

        # Navigate to submit page
        try:
            self.runner._page.goto(
                f"{self.base_url}/alpha/{alpha_id}/submit",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            return {"ok": False, "error": f"Navigation failed: {e}", "alpha_id": alpha_id}

        self.runner._take_screenshot(f"submit_before_{alpha_id}")

        # Click confirm/submit button
        try:
            confirm = self.runner._page.locator(
                'button:has-text("Submit"), button:has-text("Confirm"), '
                'button:has-text("Yes"), input[type="submit"]'
            )
            if confirm.count() > 0:
                confirm.first.click()
                self.runner._page.wait_for_load_state("networkidle", timeout=30000)
        except Exception as e:
            logger.warning(f"Submit confirmation click may have failed: {e}")

        self.runner._take_screenshot(f"submit_after_{alpha_id}")

        return {
            "ok": True,
            "alpha_id": alpha_id,
            "evidence": self.get_evidence(),
        }

    def get_evidence(self) -> ExecutionEvidence:
        """Collect all browser interaction evidence."""
        raw = self.runner.get_evidence()
        return ExecutionEvidence(
            transport=raw.get("transport", "browser"),
            screenshots=list(raw.get("screenshots", [])),
            dom_snapshots=list(raw.get("dom_snapshots", [])),
            har_path=f"{self.evidence_dir}/brain_interactions.har",
            console_logs=list(raw.get("console_logs", [])),
            network_logs=list(raw.get("network_logs", [])),
        )
