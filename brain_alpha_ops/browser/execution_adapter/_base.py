"""Base dataclass for BrowserExecutionAdapter.

Holds the ``@dataclass`` field definitions, the context-manager lifecycle
(``__enter__`` / ``__exit__`` / ``runner``), the ``authenticate`` Protocol
method, the evidence-collection helper, and the shared ``_submit_failure``
failure-payload builder.

The simulation/check and submit operations live in :mod:`_simulate` and
:mod:`_submit` as mixins and are combined with this base in the package
``__init__`` to form the final :class:`BrowserExecutionAdapter`.

Extracted from the former ``execution_adapter.py`` monolith
(deep-optimization-phase13).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.browser.brain_ui_runner import BrainBrowserRunner
from brain_alpha_ops.execution_backend import ExecutionEvidence


@dataclass
class BrowserExecutionAdapterBase:
    """Production adapter base: browser-first executor lifecycle + auth + evidence."""

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
    # F-011: LRU eviction via OrderedDict. Previously a `set` + `deque` FIFO
    # pair evicted the oldest *inserted* key, so a key that was checked
    # repeatedly (duplicate re-attempt) could still be evicted just because
    # it was old, letting the duplicate through. With LRU, any check or
    # re-insertion refreshes the key's position, so actively-polled keys
    # are never evicted.
    _used_idempotency_keys: "OrderedDict[str, None]" = field(
        default_factory=OrderedDict, init=False, repr=False
    )
    _MAX_IDEMPOTENCY_KEYS = 1000

    # Internal state — managed by context manager
    _runner: BrainBrowserRunner | None = field(default=None, init=False, repr=False)
    _authenticated: bool = field(default=False, init=False, repr=False)

    # ---- Context manager ----

    def __enter__(self) -> "BrowserExecutionAdapterBase":
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
