"""Submit operation mixin for BrowserExecutionAdapter.

Holds the ``submit_alpha`` Protocol method, which drives the real BRAIN
submit flow behind an approval-ticket + idempotency-key guard. This is the
largest single operation and is isolated in its own module so the base
adapter and the read-only simulate/check flows stay compact.

Combined with :class:`BrowserExecutionAdapterBase` in the package
``__init__`` to form the final :class:`BrowserExecutionAdapter`.

Extracted from the former ``execution_adapter.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.redaction import redact_error_message

from ._state import _DEFAULT_NAV_TIMEOUT_MS, logger


class _SubmitMixin:
    """``submit_alpha`` Protocol method."""

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
            # F-011: refresh LRU position so actively-polled duplicate keys
            # are never evicted by new insertions.
            self._used_idempotency_keys.move_to_end(key)
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
        # F-011: LRU eviction. Insert at the most-recently-used end; if the
        # cache exceeds the cap, evict the least-recently-used key. Repeated
        # duplicate checks (move_to_end above) keep a key fresh so it cannot
        # be evicted while still being actively re-attempted.
        self._used_idempotency_keys[key] = None
        while len(self._used_idempotency_keys) > self._MAX_IDEMPOTENCY_KEYS:
            self._used_idempotency_keys.popitem(last=False)

        return {
            "ok": True,
            "alpha_id": alpha_id,
            "approval_ticket": approval,
            "idempotency_key": key,
            "evidence": self.get_evidence(),
        }
