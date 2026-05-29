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
    assert metrics["self_correlation"] == 0.3


def test_normalize_metrics_preserves_self_correlation_check_status():
    metrics = normalize_metrics(
        {
            "is": {
                "sharpe": 1.4,
                "fitness": 1.1,
                "turnover": 0.2,
                "checks": [{"name": "SELF_CORRELATION", "result": "PENDING"}],
            },
        }
    )

    assert metrics["self_correlation_status"] == "PENDING"
    assert "self_correlation" not in metrics


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


def test_list_datasets_uses_official_data_sets_endpoint():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "count": 2,
                    "results": [
                        {"id": "fundamental6", "name": "Company Fundamental Data", "fieldCount": 886},
                        {"code": "pv1", "title": "Price Volume Data", "fields": [{"id": "close"}, {"id": "volume"}]},
                    ],
                }
            ).encode()

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
        datasets = api.list_datasets("all", "")
        assert [row["id"] for row in datasets] == ["fundamental6", "pv1"]
        assert datasets[0]["field_count"] == 886
        assert datasets[1]["field_count"] == 2
        assert captured["url"].startswith("https://example.test/data-sets?")
        assert "region=EUR" in captured["url"]
        assert "universe=TOP1000" in captured["url"]
        assert "delay=0" in captured["url"]


def test_list_datasets_uses_stale_cache_on_429():
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
            "datasets",
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
            json.dumps({"created_at": 1, "items": [{"id": "fundamental6", "name": "Fundamental"}]}),
            encoding="utf-8",
        )
        try:
            time.sleep = lambda _seconds: None
            api._open = fake_open
            datasets = api.list_datasets("all", "USA")
            assert datasets[0]["id"] == "fundamental6"
        finally:
            time.sleep = original_sleep


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


def test_list_user_alphas_cached_progress_preserves_cached_total():
    progress = []

    with tempfile.TemporaryDirectory() as tmp:
        config = OfficialAPIConfig(
            base_url="https://example.test",
            cache_dir=tmp,
            min_request_interval_seconds=0,
            context_cache_ttl_seconds=3600,
        )
        api = OfficialBrainAPI(config, token="token")
        cache_name = api._cache_key("user_alphas", {"limit": 100, "offset": 0, "days": 3})
        api._cache_path(cache_name).write_text(
            json.dumps({"created_at": time.time(), "total": 25549, "items": [{"id": "a1"}, {"id": "a2"}]}),
            encoding="utf-8",
        )

        rows = api.list_user_alphas("3d", progress_callback=progress.append)

    assert len(rows) == 2
    assert progress[-1]["scanned"] == 2
    assert progress[-1]["total"] == 25549
    assert progress[-1]["cached"] is True


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


def test_list_user_alphas_fetches_past_previous_10000_cap():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, offset: int):
            self.offset = offset

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            rows = (
                []
                if self.offset >= 10100
                else [{"id": f"a{self.offset + index}", "regular": f"rank(field_{self.offset + index})"} for index in range(100)]
            )
            return json.dumps({"count": 10100, "results": rows}).encode()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            offset = int(req.full_url.rsplit("offset=", 1)[-1].split("&", 1)[0])
            return Response(offset)

        api._open = fake_open
        rows = api.list_user_alphas("3d")
        assert len(rows) == 10100
        assert len(calls) == 102
        assert rows[-1]["id"] == "a10099"


def test_list_user_alphas_ignores_reported_10000_total_when_pages_continue():
    calls = []
    pages = {
        0: [{"id": f"a{index}", "regular": f"rank(field_{index})"} for index in range(100)],
        100: [{"id": f"a{100 + index}", "regular": f"rank(field_{100 + index})"} for index in range(100)],
        200: [],
    }

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, offset: int):
            self.offset = offset

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"count": 100, "results": pages[self.offset]}).encode()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            offset = int(req.full_url.rsplit("offset=", 1)[-1].split("&", 1)[0])
            return Response(offset)

        api._open = fake_open
        rows = api.list_user_alphas("all")
        assert len(rows) == 200
        assert len(calls) == 3
        assert rows[-1]["id"] == "a199"


def test_list_user_alphas_narrows_by_created_date_after_offset_limit():
    calls = []
    progress = []

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            calls.append(query)
            offset = int(query.get("offset", 0))
            cursor = query.get("dateCreated<")
            if not cursor and offset == 0:
                return {
                    "count": 10000,
                    "results": [
                        {"id": f"new_{index}", "regular": "rank(close)", "dateCreated": f"2026-01-02T00:{index:02d}:00-04:00"}
                        for index in range(100)
                    ],
                }, {}
            if not cursor and offset == 100:
                return {
                    "count": 10000,
                    "results": [
                        {"id": f"mid_{index}", "regular": "rank(close)", "dateCreated": f"2026-01-01T23:{index:02d}:00-04:00"}
                        for index in range(100)
                    ],
                }, {}
            if not cursor and offset == 200:
                raise BrainAPIError("HTTP 400: ['Invalid offset. Please use filters to narrow down the result.']", status_code=400)
            if cursor and offset == 0:
                return {
                    "count": 2,
                    "results": [
                        {"id": "old_1", "regular": "rank(open)", "dateCreated": "2025-12-31T00:00:00-04:00"},
                        {"id": "old_2", "regular": "rank(volume)", "dateCreated": "2025-12-30T00:00:00-04:00"},
                    ],
                }, {}
            raise AssertionError(f"unexpected query {query}")

        api._request = fake_request
        rows = api.list_user_alphas("all", progress_callback=progress.append)

        assert len(rows) == 202
        assert any(call.get("dateCreated<") for call in calls)
        assert progress[-2]["warning"] == "offset_limit_narrowed_by_date"
        assert rows[-1]["id"] == "old_2"


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


def test_request_rejects_cross_origin_absolute_url():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    try:
        api._request("GET", "https://evil.example/data-fields")
    except BrainAPIError as exc:
        assert "cross-origin" in str(exc)
    else:
        raise AssertionError("expected cross-origin URL to be rejected")


def test_request_allows_same_origin_absolute_url():
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
        captured["url"] = req.full_url
        return Response()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._open = fake_open
    data, _headers = api._request("GET", "https://example.test/data-fields", query={"limit": 1})
    assert data["status"] == "ok"
    assert captured["url"] == "https://example.test/data-fields?limit=1"


def test_submit_simulation_rejects_cross_origin_location_header():
    class Response:
        headers = {"Content-Type": "application/json", "Location": "https://evil.example/simulations/1"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"{}"

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._open = lambda _req, timeout: Response()

    try:
        api.submit_simulation("rank(close)", BrainSettings(region="USA", universe="TOP3000"))
    except BrainAPIError as exc:
        assert "cross-origin" in str(exc)
    else:
        raise AssertionError("expected cross-origin Location to be rejected")


def test_throttle_uses_shared_timestamp_across_instances(monkeypatch):
    import brain_alpha_ops.brain_api.official as official

    sleeps = []
    ticks = iter([100.1, 103.0, 103.0, 106.0])

    monkeypatch.setattr(official, "_GLOBAL_LAST_REQUEST_AT", 100.0)
    monkeypatch.setattr(official.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(official.time, "sleep", lambda seconds: sleeps.append(seconds))

    config = OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=3.0)
    first = OfficialBrainAPI(config, token="token")
    second = OfficialBrainAPI(config, token="token")

    first._throttle()
    second._throttle()

    assert len(sleeps) == 2
    assert round(sleeps[0], 6) == 2.9
    assert sleeps[1] == 3.0
    assert official._GLOBAL_LAST_REQUEST_AT == 106.0
    assert first._request_lock.__class__.__name__ == "RLock"
