from __future__ import annotations

from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter
from brain_alpha_ops.browser.brain_ui_runner import BrainBrowserRunner, _redact_text
from brain_alpha_ops.browser.monitor import BrowserMonitor


class _FakeLocator:
    def __init__(self, count: int = 0):
        self._count = count
        self.clicked = False

    def count(self) -> int:
        return self._count

    @property
    def first(self):
        return self

    def click(self):
        self.clicked = True

    def inner_text(self):
        return "unknown challenge"


class _FakePage:
    def __init__(self, *, confirm_count: int = 0, body: str = "Alpha submit page"):
        self.goto_calls = []
        self.confirm = _FakeLocator(confirm_count)
        self.body = body

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))

    def locator(self, selector):
        if "Submit" in selector or "Confirm" in selector or "submit" in selector:
            return self.confirm
        return _FakeLocator(0)

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def inner_text(self, _selector):
        return self.body


class _FakeRunner:
    def __init__(self, page: _FakePage):
        self._page = page
        self.state = type(
            "State",
            (),
            {
                "screenshots": [],
                "dom_snapshots": [],
                "console_logs": [],
                "network_logs": [],
                "errors": [],
            },
        )()

    def _take_screenshot(self, name):
        self.state.screenshots.append(name)

    def _snapshot_dom(self, name):
        self.state.dom_snapshots.append(name)

    def classify_blocking_state(self):
        if "rate limit" in self._page.body.lower():
            return {"code": "BROWSER_RATE_LIMITED", "message": "rate limit", "retryable": True}
        return None

    def side_effect_guard(self, _action):
        return {"allowed": True, "code": "OK"}

    def get_evidence(self):
        return {
            "transport": "browser",
            "screenshots": list(self.state.screenshots),
            "dom_snapshots": list(self.state.dom_snapshots),
            "console_logs": [],
            "network_logs": list(self.state.network_logs),
        }


def _adapter(page: _FakePage) -> BrowserExecutionAdapter:
    adapter = BrowserExecutionAdapter(base_url="https://example.test", readonly=False)
    adapter._runner = _FakeRunner(page)
    adapter._authenticated = True
    return adapter


def test_browser_submit_requires_guard_values_before_page_touch():
    page = _FakePage(confirm_count=1)
    adapter = _adapter(page)

    result = adapter.submit_alpha("alpha123")

    assert result["ok"] is False
    assert result["error_code"] == "BROWSER_SUBMIT_GUARD_MISSING"
    assert set(result["missing"]) == {"approval_ticket", "idempotency_key"}
    assert page.goto_calls == []


def test_browser_submit_missing_confirmation_fails_closed():
    page = _FakePage(confirm_count=0)
    adapter = _adapter(page)

    result = adapter.submit_alpha(
        "alpha123",
        approval_ticket="HIL-123",
        idempotency_key="submit-alpha123-1",
    )

    assert result["ok"] is False
    assert result["error_code"] == "BROWSER_SUBMIT_CONFIRMATION_MISSING"
    assert page.goto_calls


def test_browser_submit_blocks_rate_limit_state_before_click():
    page = _FakePage(confirm_count=1, body="rate limit: too many requests")
    adapter = _adapter(page)

    result = adapter.submit_alpha(
        "alpha123",
        approval_ticket="HIL-123",
        idempotency_key="submit-alpha123-2",
    )

    assert result["ok"] is False
    assert result["error_code"] == "BROWSER_RATE_LIMITED"
    assert page.confirm.clicked is False


def test_browser_monitor_classifies_429_as_fail_closed():
    runner = _FakeRunner(_FakePage())
    runner.state.network_logs.append({"phase": "response", "status": 429})
    monitor = BrowserMonitor(runner)

    result = monitor.classify_fail_closed()

    assert result["status"] == "blocked"
    assert result["code"] == "BROWSER_RATE_LIMITED"
    assert result["retryable"] is True


def test_real_brain_runner_live_navigation_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("BRAIN_BROWSER_E2E_LIVE", raising=False)
    runner = BrainBrowserRunner(base_url="https://brain.worldquant.com")

    guard = runner.live_navigation_guard()

    assert guard["allowed"] is False
    assert guard["code"] == "LIVE_BROWSER_NAVIGATION_NOT_APPROVED"


def test_browser_runner_redacts_evidence_text(tmp_path):
    runner = BrainBrowserRunner(base_url="https://example.test", evidence_dir=str(tmp_path))

    runner._on_console(
        type(
            "Msg",
            (),
            {
                "type": "error",
                "text": (
                    "token=secret password = mypass "
                    "Authorization: Bearer abc123 analyst@example.test"
                ),
            },
        )()
    )
    runner._on_request(type("Req", (), {"url": "https://example.test/path?token=secret", "method": "GET"})())

    redacted = runner.state.console_logs[0]["text"]
    assert "secret" not in runner.state.console_logs[0]["text"]
    assert "mypass" not in redacted
    assert "abc123" not in redacted
    assert "analyst@example.test" not in redacted
    assert runner.state.network_logs[0]["url"].endswith("?[redacted-query]")


def test_browser_redaction_removes_cookie_session_and_csrf_values():
    redacted = _redact_text(
        "Cookie: session=abc123; csrf=def456; theme=light; token=ghi789"
    )

    assert "abc123" not in redacted
    assert "def456" not in redacted
    assert "ghi789" not in redacted
    assert "theme=light" in redacted


def test_browser_redaction_removes_sensitive_dom_input_values():
    redacted = _redact_text(
        '<form><input name="password" value="mypass">'
        '<input id="csrfToken" value="csrf-secret">'
        '<input name="search" value="rank(close)"></form>'
    )

    assert "mypass" not in redacted
    assert "csrf-secret" not in redacted
    assert 'value="<redacted>"' in redacted
    assert 'name="search" value="rank(close)"' in redacted
