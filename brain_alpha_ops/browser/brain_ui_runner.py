from __future__ import annotations
import os
import time
import logging
from dataclasses import dataclass, field
from typing import Any

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

    def __init__(self, base_url: str = "https://brain.worldquant.com", headless: bool = True, evidence_dir: str = "artifacts"):
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.evidence_dir = evidence_dir
        self.state = BrowserRunState()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        os.makedirs(self.evidence_dir, exist_ok=True)
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        har_path = os.path.join(self.evidence_dir, "brain_interactions.har")
        self._context = self._browser.new_context(
            record_har_path=har_path,
            viewport={"width": 1920, "height": 1080},
        )
        self._page = self._context.new_page()
        self._page.on("console", self._on_console)
        self._page.on("pageerror", self._on_page_error)
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)
        self.state.last_heartbeat_ts = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._page:
                self._take_screenshot("final_state")
                self._snapshot_dom("final_state")
        except Exception:
            pass
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def _on_console(self, msg):
        self.state.console_logs.append({"type": msg.type, "text": msg.text, "ts": time.time()})
        if msg.type == "error":
            self.state.errors.append(f"console.error: {msg.text}")

    def _on_page_error(self, error):
        self.state.errors.append(f"pageerror: {error}")

    def _on_request(self, request):
        self.state.network_logs.append({"url": request.url, "method": request.method, "ts": time.time(), "phase": "request"})

    def _on_response(self, response):
        self.state.network_logs.append({"url": response.url, "status": response.status, "ts": time.time(), "phase": "response"})

    def _take_screenshot(self, name: str):
        path = os.path.join(self.evidence_dir, f"{name}_{int(time.time())}.png")
        self._page.screenshot(path=path)
        self.state.screenshots.append(path)

    def _snapshot_dom(self, name: str):
        path = os.path.join(self.evidence_dir, f"{name}_{int(time.time())}.html")
        content = self._page.content()
        with open(path, "w") as f:
            f.write(content)
        self.state.dom_snapshots.append(path)

    def heartbeat(self) -> bool:
        """Check if the browser page is still responsive."""
        try:
            self._page.evaluate("() => document.readyState")
            self.state.last_heartbeat_ts = time.time()
            return True
        except Exception as e:
            self.state.errors.append(f"heartbeat_failed: {e}")
            return False

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Login to BRAIN via real browser interaction."""
        self.state.last_step = "login.navigate"
        self._page.goto(f"{self.base_url}/", wait_until="domcontentloaded", timeout=30000)
        self._take_screenshot("login_page")

        self.state.last_step = "login.fill_credentials"
        self._page.fill('input[name="email"], input[type="email"], input[name="username"]', username)
        self._page.fill('input[name="password"], input[type="password"]', password)
        self._take_screenshot("credentials_filled")

        self.state.last_step = "login.submit"
        self._page.click('button[type="submit"], input[type="submit"]')
        self._page.wait_for_load_state("networkidle", timeout=30000)
        self._take_screenshot("post_login")

        self.state.last_step = "login.verify"
        is_logged_in = self._page.locator("[data-testid='dashboard'], .dashboard, #root > div").count() > 0

        return {
            "ok": is_logged_in,
            "step": self.state.last_step,
            "screenshots": self.state.screenshots[-2:],
        }

    def navigate_to_alpha_creation(self) -> dict[str, Any]:
        """Navigate to alpha creation page."""
        self.state.last_step = "navigate.alpha_creation"
        self._page.goto(f"{self.base_url}/alpha/new", wait_until="domcontentloaded", timeout=30000)
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

    def get_evidence(self) -> dict[str, Any]:
        """Collect all interaction evidence."""
        return {
            "transport": "browser",
            "screenshots": list(self.state.screenshots),
            "dom_snapshots": list(self.state.dom_snapshots),
            "console_logs": list(self.state.console_logs),
            "network_logs": list(self.state.network_logs),
            "errors": list(self.state.errors),
        }
