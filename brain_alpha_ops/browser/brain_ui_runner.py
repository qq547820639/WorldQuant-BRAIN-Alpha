from __future__ import annotations
import json
import os
import threading
import time
import logging
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.browser._brain_ui_helpers import (
    _COOKIE_PAIR_RE,
    _COOKIE_VALUE_RE,
    _DEFAULT_PAGE_TIMEOUT_MS,
    _REAL_BRAIN_HOSTS,
    _SENSITIVE_HTML_FIELD_RE,
    LIVE_BROWSER_OPT_IN_ENV,
    _looks_like_login_page,
    _redact_text,
    _redact_url,
    _unexpected_modal,
)

logger = logging.getLogger(__name__)

@dataclass
class BrowserRunState:
    last_step: str = "init"
    last_heartbeat_ts: float = 0.0
    screenshots: list[str] = field(default_factory=list)
    dom_snapshots: list[str] = field(default_factory=list)
    console_logs: list[dict[str, Any]] = field(default_factory=list)
    network_logs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BrainBrowserRunner:
    """Browser-first executor for real BRAIN web interactions."""

    def __init__(
        self,
        base_url: str = "https://brain.worldquant.com",
        headless: bool = True,
        evidence_dir: str = "artifacts",
        *,
        mode: str = "readonly",
        allow_live_navigation: bool | None = None,
        readonly: bool = True,
        record_har: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.evidence_dir = evidence_dir
        self.mode = str(mode or "readonly").lower()
        self.readonly = bool(readonly)
        self.record_har = bool(record_har)
        self.har_path: str | None = None
        self.allow_live_navigation = (
            bool(allow_live_navigation)
            if allow_live_navigation is not None
            else self.mode == "live" and os.environ.get(LIVE_BROWSER_OPT_IN_ENV) == "1"
        )
        self.state = BrowserRunState()
        self._state_lock = threading.Lock()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        weakref.finalize(self, self._cleanup_resources, self._pw, self._browser, self._context)

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        guard = self.live_navigation_guard()
        if not guard["allowed"]:
            raise RuntimeError(guard["message"])
        os.makedirs(self.evidence_dir, exist_ok=True)
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=self.headless)
            context_options: dict[str, Any] = {"viewport": {"width": 1920, "height": 1080}}
            if self.record_har:
                self.har_path = os.path.join(self.evidence_dir, "brain_interactions.har")
                context_options["record_har_path"] = self.har_path
            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()
            self._page.on("console", self._on_console)
            self._page.on("pageerror", self._on_page_error)
            self._page.on("request", self._on_request)
            self._page.on("response", self._on_response)
        except Exception:
            self.__exit__(None, None, None)
            raise
        self.state.last_heartbeat_ts = time.time()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        try:
            if self._page:
                self._take_screenshot("final_state")
                self._snapshot_dom("final_state")
        except Exception as capture_exc:
            self.state.errors.append(f"final_evidence_capture_failed: {redact_error_message(capture_exc)}")
        self._cleanup_resources(self._pw, self._browser, self._context)
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    @staticmethod
    def _cleanup_resources(pw, browser, context):
        try:
            if context:
                context.close()
        except Exception:  # noqa: BLE001
            logger.debug("browser context close failed during cleanup", exc_info=True)
        try:
            if browser:
                browser.close()
        except Exception:  # noqa: BLE001
            logger.debug("browser close failed during cleanup", exc_info=True)
        try:
            if pw:
                pw.stop()
        except Exception:  # noqa: BLE001
            logger.debug("playwright stop failed during cleanup", exc_info=True)

    def _on_console(self, msg):
        text = _redact_text(msg.text)
        with self._state_lock:
            self.state.console_logs.append({"type": msg.type, "text": text, "ts": time.time()})
            if msg.type == "error":
                self.state.errors.append(f"console.error: {text}")

    def _on_page_error(self, error):
        with self._state_lock:
            self.state.errors.append(f"pageerror: {_redact_text(str(error))}")

    def _on_request(self, request):
        with self._state_lock:
            self.state.network_logs.append({"url": _redact_url(request.url), "method": request.method, "ts": time.time(), "phase": "request"})

    def _on_response(self, response):
        with self._state_lock:
            self.state.network_logs.append({"url": _redact_url(response.url), "status": response.status, "ts": time.time(), "phase": "response"})

    def _take_screenshot(self, name: str):
        path = os.path.join(self.evidence_dir, f"{name}_{int(time.time())}.png")
        self._page.screenshot(path=path)
        with self._state_lock:
            self.state.screenshots.append(path)

    def _snapshot_dom(self, name: str):
        path = os.path.join(self.evidence_dir, f"{name}_{int(time.time())}.html")
        content = _redact_text(self._page.content())
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        with self._state_lock:
            self.state.dom_snapshots.append(path)

    def live_navigation_guard(self) -> dict[str, Any]:
        """Return fail-closed status before opening a real BRAIN browser page."""
        is_real_brain = any(host in self.base_url for host in _REAL_BRAIN_HOSTS)
        if is_real_brain and not self.allow_live_navigation:
            return {
                "allowed": False,
                "code": "LIVE_BROWSER_NAVIGATION_NOT_APPROVED",
                "message": (
                    f"Live BRAIN browser navigation requires mode='live' and "
                    f"{LIVE_BROWSER_OPT_IN_ENV}=1"
                ),
            }
        return {"allowed": True, "code": "OK"}

    def side_effect_guard(self, action: str) -> dict[str, Any]:
        if self.readonly:
            return {
                "allowed": False,
                "code": "BROWSER_READONLY_MODE",
                "message": f"Browser action {action} is blocked in readonly mode",
            }
        return {"allowed": True, "code": "OK"}

    def classify_blocking_state(self) -> dict[str, Any] | None:
        page_text = ""
        try:
            page_text = self._page.inner_text("body") if self._page is not None else ""
        except Exception:
            page_text = ""
        lowered = page_text.lower()
        statuses = [
            row.get("status")
            for row in self.state.network_logs
            if isinstance(row, dict) and row.get("phase") == "response"
        ]
        if any(status == 429 for status in statuses) or any(token in lowered for token in ("rate limit", "too many requests")):
            return {"code": "BROWSER_RATE_LIMITED", "message": "Browser flow saw rate-limit evidence", "retryable": True}
        if any(isinstance(status, int) and status >= 500 for status in statuses) or any(
            token in lowered for token in ("service unavailable", "internal server error", "bad gateway")
        ):
            return {"code": "BROWSER_SERVER_ERROR", "message": "Browser flow saw server-side failure evidence", "retryable": True}
        if any(token in lowered for token in ("captcha", "two-factor", "2fa", "session expired", "session invalid")):
            return {"code": "BROWSER_INTERACTIVE_AUTH_REQUIRED", "message": "Browser flow requires interactive auth", "retryable": False}
        if _looks_like_login_page(lowered):
            return {"code": "BROWSER_LOGIN_LOOP", "message": "Browser flow returned to login/session page", "retryable": False}
        modal_text = self._modal_text()
        if modal_text and _unexpected_modal(modal_text):
            return {
                "code": "BROWSER_UNKNOWN_MODAL",
                "message": "Unexpected modal detected during browser flow",
                "retryable": False,
                "modal_text": _redact_text(modal_text)[:500],
            }
        return None

    def _modal_text(self) -> str:
        selectors = ("[role='dialog']", ".modal", ".ant-modal", ".MuiDialog-root", "[aria-modal='true']")
        for selector in selectors:
            try:
                locator = self._page.locator(selector)
                if locator.count() > 0:
                    return str(locator.first.inner_text() or "")
            except Exception as exc:
                self.state.errors.append(
                    f"modal_probe_failed:{selector}:{redact_error_message(exc, max_length=120)}"
                )
                continue
        return ""

    def heartbeat(self) -> bool:
        """Check if the browser page is still responsive."""
        try:
            page = getattr(self, "_page", None)
            if page is None:
                return False
            page.evaluate("() => document.readyState")
            self.state.last_heartbeat_ts = time.time()
            return True
        except Exception as e:
            self.state.errors.append(f"heartbeat_failed: {redact_error_message(str(e))}")
            return False

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Login to BRAIN via real browser interaction."""
        self.state.last_step = "login.navigate"
        self._page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=_DEFAULT_PAGE_TIMEOUT_MS)
        self._take_screenshot("login_page")

        self.state.last_step = "login.fill_credentials"
        self._page.fill('input[name="email"], input[type="email"], input[name="username"]', username)
        self._page.fill('input[name="password"], input[type="password"]', password)

        self.state.last_step = "login.submit"
        self._page.click('button[type="submit"], input[type="submit"]')
        self._page.wait_for_load_state("networkidle", timeout=_DEFAULT_PAGE_TIMEOUT_MS)
        self._take_screenshot("post_login")

        self.state.last_step = "login.verify"
        blocking = self.classify_blocking_state()
        if blocking:
            return {"ok": False, "step": self.state.last_step, "error": blocking["message"], "details": blocking}
        is_logged_in = self._page.locator("[data-testid='dashboard'], .dashboard, [data-testid='user-menu'], nav").count() > 0

        return {
            "ok": is_logged_in,
            "step": self.state.last_step,
            "screenshots": self.state.screenshots[-2:],
        }

    def navigate_to_alpha_creation(self) -> dict[str, Any]:
        """Navigate to alpha creation page."""
        self.state.last_step = "navigate.alpha_creation"
        self._page.goto(f"{self.base_url}/alpha/new", wait_until="domcontentloaded", timeout=_DEFAULT_PAGE_TIMEOUT_MS)
        self._take_screenshot("alpha_creation_page")
        return {"ok": True, "step": self.state.last_step}

    def fill_expression(self, expression: str) -> dict[str, Any]:
        """Fill expression into BRAIN alpha editor."""
        self.state.last_step = "fill_expression"
        editor = self._page.locator("textarea, [contenteditable='true'], .expression-editor")
        if editor.count() > 0:
            editor.first.fill(expression)
            self._take_screenshot("expression_filled")
            return {"ok": True, "step": self.state.last_step}
        return {"ok": False, "error": "Expression editor not found"}

    def trigger_simulation(self) -> dict[str, Any]:
        """Click the simulate/run button."""
        guard = self.side_effect_guard("simulate")
        if not guard["allowed"]:
            return {"ok": False, "step": "simulate.guard", **guard}
        self.state.last_step = "simulate.trigger"
        sim_button = self._page.locator("button:has-text('Simulate'), button:has-text('Run'), button:has-text('Test')")
        if sim_button.count() > 0:
            sim_button.first.click()
            self._page.wait_for_load_state("networkidle", timeout=60000)
            self._take_screenshot("post_simulation")
            return {"ok": True, "step": self.state.last_step}
        return {"ok": False, "error": "Simulation button not found"}

    def check_results(self) -> dict[str, Any]:
        """Read simulation results from the page."""
        self.state.last_step = "check_results"
        self._snapshot_dom("results_page")
        self._take_screenshot("results_page")

        page_text = self._page.inner_text("body")
        return {
            "ok": True,
            "step": self.state.last_step,
            "page_text_preview": page_text[:2000],
            "evidence": self.get_evidence(),
        }

    def write_evidence_manifest(self) -> str:
        path = Path(self.evidence_dir) / "browser_evidence_manifest.json"
        payload = {
            "schema_version": "browser_evidence_manifest.v1",
            "transport": "browser",
            "mode": self.mode,
            "readonly": self.readonly,
            "screenshots": list(self.state.screenshots),
            "dom_snapshots": list(self.state.dom_snapshots),
            "console_log_count": len(self.state.console_logs),
            "network_log_count": len(self.state.network_logs),
            "errors": [_redact_text(item) for item in self.state.errors],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def get_evidence(self) -> dict[str, Any]:
        """Collect all interaction evidence."""
        return {
            "transport": "browser",
            "screenshots": list(self.state.screenshots),
            "dom_snapshots": list(self.state.dom_snapshots),
            "console_logs": list(self.state.console_logs),
            "network_logs": list(self.state.network_logs),
            "errors": list(self.state.errors),
            "har_path": self.har_path,
        }
