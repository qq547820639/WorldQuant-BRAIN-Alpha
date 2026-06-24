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
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.browser.brain_ui_runner import BrainBrowserRunner
from brain_alpha_ops.execution_backend import ExecutionEvidence
from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)

_DEFAULT_NAV_TIMEOUT_MS = 30000


@dataclass
class BrowserExecutionAdapter:
    """Production adapter: browser-first executor implementing AlphaExecutionBackend."""

    username: str = ""
    password: str = ""
    base_url: str = "https://brain.worldquant.com"
    headless: bool = True
    evidence_dir: str = "artifacts"
    mode: str = "readonly"
    allow_live_navigation: bool | None = None
    readonly: bool = True
    approval_ticket: str = ""
    idempotency_key: str = ""
    _used_idempotency_keys: set[str] = field(default_factory=set, init=False, repr=False)
    _idempotency_key_order: deque[str] = field(default_factory=deque, init=False, repr=False)
    _MAX_IDEMPOTENCY_KEYS = 1000

    # Internal state — managed by context manager
    _runner: BrainBrowserRunner | None = field(default=None, init=False, repr=False)
    _authenticated: bool = field(default=False, init=False, repr=False)

    # ---- Context manager ----

    def __enter__(self) -> BrowserExecutionAdapter:
        self._runner = BrainBrowserRunner(
            base_url=self.base_url,
            headless=self.headless,
            evidence_dir=self.evidence_dir,
            mode=self.mode,
            allow_live_navigation=self.allow_live_navigation,
            readonly=self.readonly,
        )
        try:
            self._runner.__enter__()
        except Exception:
            self._runner = None
            raise
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

    def submit_alpha(
        self,
        alpha_id: str,
        *,
        approval_ticket: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Submit an Alpha via browser interaction.

        **Security note**: This method navigates the real BRAIN submit flow.
        It requires a human approval ticket and idempotency key before the
        adapter touches the browser page.

        Args:
            alpha_id: BRAIN Alpha identifier to submit.

        Returns:
            {"ok": bool, "alpha_id": str, "confirmation": ...}
        """
        approval = str(approval_ticket if approval_ticket is not None else self.approval_ticket).strip()
        key = str(idempotency_key if idempotency_key is not None else self.idempotency_key).strip()
        missing = [name for name, value in (("approval_ticket", approval), ("idempotency_key", key)) if not value]
        if missing:
            return {
                "ok": False,
                "alpha_id": alpha_id,
                "step": "submit.guard",
                "error_code": "BROWSER_SUBMIT_GUARD_MISSING",
                "error": "Browser submit requires approval_ticket and idempotency_key",
                "missing": missing,
            }
        if key in self._used_idempotency_keys:
            return {
                "ok": False,
                "alpha_id": alpha_id,
                "step": "submit.guard",
                "error_code": "BROWSER_SUBMIT_DUPLICATE_IDEMPOTENCY_KEY",
                "error": "Browser submit idempotency key was already used in this adapter session",
            }
        if not self._authenticated:
            return {"ok": False, "error": "Not authenticated", "step": "submit.not_authenticated"}
        guard = self.runner.side_effect_guard("submit")
        if not guard["allowed"]:
            return {"ok": False, "alpha_id": alpha_id, "step": "submit.guard", **guard}

        # Navigate to submit page
        try:
            page = getattr(self.runner, "_page", None)
            if page is None:
                return self._submit_failure(alpha_id, "submit.navigate", "Browser page not initialized")
            page.goto(
                f"{self.base_url}/alpha/{alpha_id}/submit",
                wait_until="domcontentloaded",
                timeout=_DEFAULT_NAV_TIMEOUT_MS,
            )
        except Exception as e:
            return self._submit_failure(alpha_id, "submit.navigate", f"Navigation failed: {e}")

        self.runner._take_screenshot(f"submit_before_{alpha_id}")
        self.runner._snapshot_dom(f"submit_before_{alpha_id}")
        blocking = self.runner.classify_blocking_state()
        if blocking:
            return self._submit_failure(
                alpha_id,
                "submit.blocked_state",
                blocking["message"],
                error_code=str(blocking["code"]),
                details=blocking,
            )

        # Click confirm/submit button
        try:
            page = getattr(self.runner, "_page", None)
            if page is None:
                return self._submit_failure(alpha_id, "submit.confirm_missing", "Browser page not initialized")
            confirm = page.locator(
                'button:has-text("Submit"), button:has-text("Confirm"), '
                'button:has-text("Yes"), input[type="submit"]'
            )
            if confirm.count() <= 0:
                return self._submit_failure(
                    alpha_id,
                    "submit.confirm_missing",
                    "Submit confirmation button not found",
                    error_code="BROWSER_SUBMIT_CONFIRMATION_MISSING",
                )
            confirm.first.click()
            page.wait_for_load_state("networkidle", timeout=_DEFAULT_NAV_TIMEOUT_MS)
        except Exception as e:
            message = redact_error_message(e)
            logger.warning("Submit confirmation click failed: %s", message)
            return self._submit_failure(
                alpha_id,
                "submit.confirm_failed",
                f"Submit confirmation failed: {message}",
                error_code="BROWSER_SUBMIT_CONFIRMATION_FAILED",
            )

        self.runner._take_screenshot(f"submit_after_{alpha_id}")
        self.runner._snapshot_dom(f"submit_after_{alpha_id}")
        blocking = self.runner.classify_blocking_state()
        if blocking:
            return self._submit_failure(
                alpha_id,
                "submit.post_submit_blocked_state",
                blocking["message"],
                error_code=str(blocking["code"]),
                details=blocking,
            )
        self._used_idempotency_keys.add(key)
        self._idempotency_key_order.append(key)
        if len(self._idempotency_key_order) > self._MAX_IDEMPOTENCY_KEYS:
            old = self._idempotency_key_order.popleft()
            self._used_idempotency_keys.discard(old)

        return {
            "ok": True,
            "alpha_id": alpha_id,
            "approval_ticket": approval,
            "idempotency_key": key,
            "evidence": self.get_evidence(),
        }

    def get_evidence(self) -> ExecutionEvidence:
        """Collect all browser interaction evidence."""
        raw = self.runner.get_evidence()
        return ExecutionEvidence(
            transport=raw.get("transport", "browser"),
            screenshots=list(raw.get("screenshots", [])),
            dom_snapshots=list(raw.get("dom_snapshots", [])),
            har_path=raw.get("har_path"),
            console_logs=list(raw.get("console_logs", [])),
            network_logs=list(raw.get("network_logs", [])),
        )

    def _submit_failure(
        self,
        alpha_id: str,
        step: str,
        error: str,
        *,
        error_code: str = "BROWSER_SUBMIT_FAILED",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            evidence = self.get_evidence()
        except (AttributeError, RuntimeError):  # pragma: no cover - defensive evidence fallback
            evidence = ExecutionEvidence(
                transport="browser",
                screenshots=[],
                dom_snapshots=[],
                console_logs=[],
                network_logs=[],
                har_path=None,
            )
        payload: dict[str, Any] = {
            "ok": False,
            "alpha_id": alpha_id,
            "step": step,
            "error_code": error_code,
            "error": error,
            "evidence": evidence,
        }
        if details is not None:
            payload["details"] = details
        return payload
