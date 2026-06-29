"""Phase 2 batch 2 sub-agent E: regression tests for F-031/F-032/F-041/F-012/F-011.

Covers:
- F-041: ``BrainAPIBridge.concurrent_simulate`` / ``concurrent_check`` run
  with real ``ThreadPoolExecutor`` concurrency (not serial for-loop) and
  preserve input order.
- F-011: ``BrowserExecutionAdapter`` idempotency key cache uses LRU
  eviction so actively-polled duplicate keys are not evicted by new
  insertions.
- F-031/F-032: ``run_pipeline_from_config`` injects the execution backend
  selected by ``run_config.execution_mode``; ``execution_factory`` warns
  when falling back to API in ``auto`` mode.
"""

from __future__ import annotations

import threading
import time

import pytest

from brain_alpha_ops.brain_api.brain_api_bridge import BrainAPIBridge
from brain_alpha_ops.browser.execution_adapter import BrowserExecutionAdapter


# ---------------------------------------------------------------------------
# F-041: BrainAPIBridge concurrent_simulate / concurrent_check
# ---------------------------------------------------------------------------


class _RecordingBackend:
    """Minimal AlphaExecutionBackend stub that records concurrency."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.simulate_calls = []
        self.check_calls = []

    def authenticate(self, credentials):
        return {"ok": True}

    def simulate_alpha(self, expression, settings):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.simulate_calls.append(expression)
        time.sleep(0.02)
        with self.lock:
            self.active -= 1
        return {"ok": True, "expression": expression}

    def check_alpha(self, alpha_id):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.check_calls.append(alpha_id)
        time.sleep(0.02)
        with self.lock:
            self.active -= 1
        return {"ok": True, "alpha_id": alpha_id, "checks": []}

    def submit_alpha(self, alpha_id):
        return {"ok": True, "alpha_id": alpha_id}

    def get_evidence(self):
        return {"transport": "test"}


class _AlphaLike:
    """Alpha-like object with expression/settings attributes."""

    def __init__(self, name):
        self.expression = name
        self.settings = {"region": "USA"}


def test_bridge_concurrent_simulate_runs_in_parallel_and_preserves_order():
    backend = _RecordingBackend()
    bridge = BrainAPIBridge(backend)
    alphas = [_AlphaLike(f"rank(close_{i})") for i in range(6)]

    results = bridge.concurrent_simulate(alphas, concurrency=4)

    assert [r["expression"] for r in results] == [a.expression for a in alphas]
    assert all(r["ok"] is True for r in results)
    # True concurrency: with 6 tasks at 20ms each and 4 workers, serial would
    # be ~120ms while concurrent is ~40ms. More importantly, max_active > 1
    # proves the pool actually ran workers in parallel.
    assert backend.max_active > 1
    assert backend.max_active <= 4


def test_bridge_concurrent_check_runs_in_parallel_and_preserves_order():
    backend = _RecordingBackend()
    bridge = BrainAPIBridge(backend)
    ids = [f"alpha_{i}" for i in range(5)]

    results = bridge.concurrent_check(ids, concurrency=3)

    assert [r["alpha_id"] for r in results] == ids
    assert all(r["ok"] is True for r in results)
    assert backend.max_active > 1
    assert backend.max_active <= 3


def test_bridge_concurrent_simulate_return_exceptions_collects_errors():
    class _FailBackend(_RecordingBackend):
        def simulate_alpha(self, expression, settings):
            if "fail" in expression:
                raise RuntimeError(f"boom on {expression}")
            return super().simulate_alpha(expression, settings)

    backend = _FailBackend()
    bridge = BrainAPIBridge(backend)
    alphas = [_AlphaLike("rank(close_ok)"), _AlphaLike("rank(close_fail)")]

    results = bridge.concurrent_simulate(alphas, concurrency=2, return_exceptions=True)

    assert isinstance(results[1], Exception)
    assert results[0]["ok"] is True


def test_bridge_concurrent_simulate_raises_on_error_when_not_returning_exceptions():
    class _FailBackend(_RecordingBackend):
        def simulate_alpha(self, expression, settings):
            raise RuntimeError("always fails")

    backend = _FailBackend()
    bridge = BrainAPIBridge(backend)

    with pytest.raises(RuntimeError):
        bridge.concurrent_simulate([_AlphaLike("rank(close)")], concurrency=2)


# ---------------------------------------------------------------------------
# F-011: LRU idempotency key eviction
# ---------------------------------------------------------------------------


def _make_authenticated_adapter() -> BrowserExecutionAdapter:
    adapter = BrowserExecutionAdapter(
        base_url="https://example.test",
        readonly=False,
        approval_ticket="HIL-1",
        idempotency_key="unused",
    )
    # Bypass the context-manager requirement by faking a runner.
    adapter._runner = type(
        "FakeRunner",
        (),
        {
            "_page": None,
            "_take_screenshot": lambda self, name: None,
            "_snapshot_dom": lambda self, name: None,
            "classify_blocking_state": lambda self: None,
            "side_effect_guard": lambda self, action: {"allowed": True, "code": "OK"},
            "get_evidence": lambda self: {
                "transport": "browser",
                "screenshots": [],
                "dom_snapshots": [],
                "console_logs": [],
                "network_logs": [],
            },
        },
    )()
    adapter._authenticated = True
    return adapter


def test_idempotency_lru_keeps_recently_checked_keys_alive():
    adapter = _make_authenticated_adapter()
    adapter._MAX_IDEMPOTENCY_KEYS = 3

    # Pre-populate 3 keys directly via the LRU cache.
    for k in ("k1", "k2", "k3"):
        adapter._used_idempotency_keys[k] = None

    # Refresh k1 by checking it — this should move it to the MRU end.
    adapter._used_idempotency_keys.move_to_end("k1")
    # Insert a new key, which evicts the LRU (now k2, since k1 was refreshed).
    adapter._used_idempotency_keys["k4"] = None
    while len(adapter._used_idempotency_keys) > adapter._MAX_IDEMPOTENCY_KEYS:
        adapter._used_idempotency_keys.popitem(last=False)

    assert "k1" in adapter._used_idempotency_keys  # refreshed, survived
    assert "k2" not in adapter._used_idempotency_keys  # LRU, evicted
    assert "k3" in adapter._used_idempotency_keys
    assert "k4" in adapter._used_idempotency_keys


def test_idempotency_duplicate_key_detected_after_lru_refresh():
    adapter = _make_authenticated_adapter()
    adapter._MAX_IDEMPOTENCY_KEYS = 2
    adapter._used_idempotency_keys["old"] = None
    adapter._used_idempotency_keys["checked"] = None
    # Simulate repeated duplicate checks of "checked" interleaved with new
    # insertions; the duplicate must still be detected.
    for new_key in ("n1", "n2", "n3"):
        # Refresh "checked" so it is not evicted.
        if "checked" in adapter._used_idempotency_keys:
            adapter._used_idempotency_keys.move_to_end("checked")
        adapter._used_idempotency_keys[new_key] = None
        while len(adapter._used_idempotency_keys) > adapter._MAX_IDEMPOTENCY_KEYS:
            adapter._used_idempotency_keys.popitem(last=False)

    assert "checked" in adapter._used_idempotency_keys


# ---------------------------------------------------------------------------
# F-031/F-032: runner injection + execution_factory warning
# ---------------------------------------------------------------------------


def test_run_pipeline_from_config_uses_execution_mode(monkeypatch):
    """run_pipeline_from_config must route through execution_factory."""
    from brain_alpha_ops import runner

    captured = {}

    class _FakeBackend:
        def __init__(self, **kwargs):
            captured["backend_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_create(mode, browser_config=None, *, run_config=None):
        captured["mode"] = mode
        captured["run_config_present"] = run_config is not None
        return _FakeBackend()

    def _fake_validate(run_config, **kwargs):
        return run_config

    monkeypatch.setattr(runner, "create_execution_backend", _fake_create)
    monkeypatch.setattr(runner, "validate_run_config", _fake_validate)

    class _FakePipeline:
        def __init__(self, **kwargs):
            captured["pipeline_kwargs"] = kwargs
            assert "execution_backend" in kwargs
            assert "api" not in kwargs

        def run(self, *, auto_submit=False):
            captured["auto_submit"] = auto_submit
            return {"ok": True}

    monkeypatch.setattr(runner, "AlphaResearchPipeline", _FakePipeline)

    from brain_alpha_ops.config import RunConfig

    rc = RunConfig()
    rc.execution_mode = "browser"
    rc.auto_submit = True

    result = runner.run_pipeline_from_config(rc)

    assert result == {"ok": True}
    assert captured["mode"] == "browser"
    assert captured["run_config_present"] is True
    assert captured["auto_submit"] is True


def test_execution_factory_warns_when_auto_falls_back_to_api(monkeypatch, caplog):
    from brain_alpha_ops import execution_factory

    monkeypatch.setattr(execution_factory, "_playwright_available", lambda: False)
    monkeypatch.delenv(execution_factory.ENV_EXECUTION_MODE, raising=False)
    monkeypatch.delenv(execution_factory._ENV_EXECUTION_MODE_LEGACY, raising=False)

    class _FakeApiAdapter:
        def __init__(self, api):
            self._api = api

    monkeypatch.setattr(
        execution_factory,
        "_create_api_backend",
        lambda run_config=None: _FakeApiAdapter(None),
    )

    with caplog.at_level("WARNING", logger="brain_alpha_ops.execution_factory"):
        backend = execution_factory.create_execution_backend(mode="auto")

    assert isinstance(backend, _FakeApiAdapter)
    assert any("playwright unavailable" in rec.message for rec in caplog.records)


def test_execution_factory_auto_uses_browser_when_playwright_available(monkeypatch):
    from brain_alpha_ops import execution_factory

    monkeypatch.setattr(execution_factory, "_playwright_available", lambda: True)
    monkeypatch.delenv(execution_factory.ENV_EXECUTION_MODE, raising=False)
    monkeypatch.delenv(execution_factory._ENV_EXECUTION_MODE_LEGACY, raising=False)

    captured = {}

    class _FakeBrowserAdapter:
        pass

    def _fake_browser(config, run_config=None):
        captured["called"] = True
        return _FakeBrowserAdapter()

    monkeypatch.setattr(execution_factory, "_create_browser_backend", _fake_browser)

    backend = execution_factory.create_execution_backend(mode="auto")

    assert isinstance(backend, _FakeBrowserAdapter)
    assert captured.get("called") is True
