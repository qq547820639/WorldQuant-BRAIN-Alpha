import io
import json
import os
import sys
import tempfile
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.official import OfficialBrainAPI, build_simulation_payload, normalize_metrics
from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig


def test_build_simulation_payload_contains_settings_and_expression():
    payload = build_simulation_payload("rank(close)", BrainSettings(region="USA", universe="TOP3000"))
    assert payload["type"] == "REGULAR"
    assert payload["regular"] == "rank(close)"
    assert payload["settings"]["region"] == "USA"
    assert payload["settings"]["language"] == "FASTEXPR"


def test_normalize_metrics_extracts_checks():
    metrics = normalize_metrics(
        {
            "is": {
                "sharpe": 1.4,
                "fitness": 1.1,
                "turnover": 0.2,
                "returns": 0.05,
                "drawdown": -0.08,
                "subUniverseSharpe": 1.0,
                "selfCorrelation": 0.3,
            },
            "checks": [{"name": "LOW_SHARPE", "result": "PASS"}],
        }
    )
    assert metrics["sharpe"] == 1.4
    assert metrics["pass_fail"] == "PASS"
    assert metrics["correlation"] == 0.3


def test_request_retries_after_429():
    calls = {"count": 0}
    original_sleep = time.sleep

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status": "ok"}'

    def fake_open(_req, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                "https://example.test",
                429,
                "Too Many Requests",
                {"Retry-After": "0"},
                io.BytesIO(b'{"message": "API rate limit exceeded"}'),
            )
        return Response()

    try:
        time.sleep = lambda _seconds: None
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                min_request_interval_seconds=0,
                rate_limit_retry_attempts=1,
                rate_limit_backoff_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open
        data, _headers = api._request("GET", "/ok")
        assert data["status"] == "ok"
        assert calls["count"] == 2
    finally:
        time.sleep = original_sleep


def test_request_retries_after_transient_5xx():
    calls = {"count": 0}
    original_sleep = time.sleep

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status": "ok"}'

    def fake_open(_req, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.HTTPError(
                "https://example.test",
                503,
                "Service Unavailable",
                {"Retry-After": "0"},
                io.BytesIO(b'{"message": "temporarily unavailable"}'),
            )
        return Response()

    try:
        time.sleep = lambda _seconds: None
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                min_request_interval_seconds=0,
                rate_limit_retry_attempts=1,
                rate_limit_backoff_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open
        data, _headers = api._request("GET", "/ok")
        assert data["status"] == "ok"
        assert calls["count"] == 2
    finally:
        time.sleep = original_sleep


def test_request_retries_after_urlerror():
    calls = {"count": 0}
    original_sleep = time.sleep

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status": "ok"}'

    def fake_open(_req, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("timed out")
        return Response()

    try:
        time.sleep = lambda _seconds: None
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                min_request_interval_seconds=0,
                rate_limit_retry_attempts=1,
                rate_limit_backoff_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open
        data, _headers = api._request("GET", "/ok")
        assert data["status"] == "ok"
        assert calls["count"] == 2
    finally:
        time.sleep = original_sleep


def test_list_fields_uses_stale_cache_on_429():
    original_sleep = time.sleep

    def fake_open(_req, timeout):
        raise urllib.error.HTTPError(
            "https://example.test",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"message": "API rate limit exceeded"}'),
        )

    with tempfile.TemporaryDirectory() as tmp:
        config = OfficialAPIConfig(
            base_url="https://example.test",
            cache_dir=tmp,
            context_cache_ttl_seconds=0,
            allow_stale_context_on_rate_limit=True,
            min_request_interval_seconds=0,
            rate_limit_retry_attempts=0,
        )
        api = OfficialBrainAPI(config, token="token")
        cache_name = api._cache_key(
            "fields",
            {
                "instrumentType": "EQUITY",
                "region": "USA",
                "delay": 1,
                "universe": "TOP3000",
                "limit": 50,
                "offset": 0,
            },
        )
        api._cache_path(cache_name).write_text(
            json.dumps({"created_at": 1, "items": [{"name": "close", "category": "price"}]}),
            encoding="utf-8",
        )
        try:
            time.sleep = lambda _seconds: None
            api._open = fake_open
            fields = api.list_fields("all", "USA")
            assert fields[0]["name"] == "close"
        finally:
            time.sleep = original_sleep


def test_429_error_exposes_status_code():
    original_sleep = time.sleep

    def fake_open(_req, timeout):
        raise urllib.error.HTTPError(
            "https://example.test",
            429,
            "Too Many Requests",
            {"Retry-After": "3"},
            io.BytesIO(b'{"message": "API rate limit exceeded"}'),
        )

    try:
        time.sleep = lambda _seconds: None
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                min_request_interval_seconds=0,
                rate_limit_retry_attempts=0,
            ),
            token="token",
        )
        api._open = fake_open
        try:
            api._request("GET", "/limited")
        except BrainAPIError as exc:
            assert exc.status_code == 429
            assert exc.retry_after == 3
        else:
            raise AssertionError("expected BrainAPIError")
    finally:
        time.sleep = original_sleep


def test_list_fields_uses_market_scope_params():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"results": [{"id": "close", "category": "price"}]}'

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        return Response()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api.set_market_scope(BrainSettings(region="EUR", universe="TOP1000", delay=0))
        api._open = fake_open
        fields = api.list_fields("all", "")
        assert fields[0]["name"] == "close"
        assert "region=EUR" in captured["url"]
        assert "universe=TOP1000" in captured["url"]
        assert "delay=0" in captured["url"]


def test_list_fields_refreshes_partial_fresh_cache():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.body

    def fake_open(req, timeout):
        calls.append(req.full_url)
        if "offset=50" in req.full_url:
            return Response(json.dumps({"count": 60, "results": [{"id": f"field_{i}"} for i in range(50, 60)]}).encode())
        return Response(json.dumps({"count": 60, "results": [{"id": f"field_{i}"} for i in range(50)]}).encode())

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )
        cache_name = api._cache_key(
            "fields",
            {
                "instrumentType": "EQUITY",
                "region": "USA",
                "delay": 1,
                "universe": "TOP3000",
                "limit": 50,
                "offset": 0,
            },
        )
        api._cache_path(cache_name).write_text(
            json.dumps({"created_at": time.time(), "items": [{"name": f"cached_{i}"} for i in range(50)]}),
            encoding="utf-8",
        )
        api._open = fake_open
        fields = api.list_fields("all", "USA")
        assert len(fields) == 60
        assert any("offset=50" in url for url in calls)


def test_list_fields_stops_on_repeated_full_page():
    calls = []
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"count": 1000, "results": [{"id": f"field_{i}"} for i in range(50)]}).encode()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()
        fields = api.list_fields("all", "USA", progress_callback=progress.append)
        assert len(fields) == 50
        assert len(calls) == 2
        assert progress[-1]["warning"] == "repeated_page"
        assert progress[-1]["truncated"] is True


def test_list_operators_stops_on_repeated_full_page():
    calls = []
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"count": 1000, "results": [{"name": f"op_{i}"} for i in range(100)]}).encode()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()
        operators = api.list_operators("all", progress_callback=progress.append)
        assert len(operators) == 100
        assert len(calls) == 2
        assert progress[-1]["warning"] == "repeated_page"
        assert progress[-1]["truncated"] is True


def test_list_user_alphas_progress_includes_total():
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 3, "results": [{"id": "a1"}, {"id": "a2"}]}'

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api._open = lambda _req, timeout=None: Response()
        rows = api.list_user_alphas("3d", progress_callback=progress.append)
        assert len(rows) == 2
        assert progress[-1]["scanned"] == 2
        assert progress[-1]["total"] == 3


def test_list_user_alphas_stops_when_total_reached():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 2, "results": [{"id": "a1"}, {"id": "a2"}]}'

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()
        rows = api.list_user_alphas("3d")
        assert [row["id"] for row in rows] == ["a1", "a2"]
        assert len(calls) == 1


def test_list_user_alphas_stops_on_repeated_full_page():
    calls = []
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"count": 1000, "results": [{"id": f"a{i}", "regular": f"rank(field_{i})"} for i in range(100)]}).encode()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()
        rows = api.list_user_alphas("3d", progress_callback=progress.append)
        assert len(rows) == 100
        assert len(calls) == 2
        assert progress[-1]["warning"] == "repeated_page"
        assert progress[-1]["truncated"] is True


def test_cookie_auth_preferred_over_bearer_when_available():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status": "ok"}'

    def fake_open(req, timeout):
        captured["authorization"] = req.headers.get("Authorization")
        return Response()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        username="user",
        password="pass",
        token="stale-token",
    )
    api._prefer_cookie_auth = True
    api._has_session_cookie = lambda: True
    api._open = fake_open
    api._request("GET", "/data-fields")
    assert captured["authorization"] is None


def test_bearer_401_falls_back_to_basic_auth():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status": "ok"}'

    def fake_open(req, timeout):
        authorization = req.headers.get("Authorization", "")
        calls.append(authorization)
        if authorization.startswith("Bearer "):
            raise urllib.error.HTTPError(
                "https://example.test",
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"detail": "Incorrect authentication credentials."}'),
            )
        return Response()

    api = OfficialBrainAPI(
        OfficialAPIConfig(
            base_url="https://example.test",
            min_request_interval_seconds=0,
            rate_limit_retry_attempts=0,
        ),
        username="user",
        password="pass",
        token="bad-token",
    )
    api._open = fake_open
    data, _headers = api._request("GET", "/data-fields")
    assert data["status"] == "ok"
    assert calls[0].startswith("Bearer ")
    assert calls[1].startswith("Basic ")
