import io
import inspect
import json
import logging
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api import pagination_limits
from brain_alpha_ops.brain_api.official_auth import OfficialAuthProfileMixin
from brain_alpha_ops.brain_api.official_context import OfficialContextDataMixin
from brain_alpha_ops.brain_api.official import OfficialBrainAPI, build_simulation_payload, normalize_metrics
from brain_alpha_ops.brain_api.official_helpers import build_official_url
from brain_alpha_ops.brain_api.official_request import OfficialRequestMixin
from brain_alpha_ops.brain_api.official_simulation import OfficialSimulationSubmissionMixin
from brain_alpha_ops.brain_api.official_validation import OfficialExpressionValidationMixin
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


def test_official_api_can_disable_proxy_handlers(monkeypatch):
    captured = {}

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers

        class Opener:
            def open(self, _req, timeout=None):
                raise AssertionError("open should not be called in this test")

        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)

    OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test"),
        token="token",
        disable_proxy=True,
    )

    proxy_handlers = [handler for handler in captured["handlers"] if isinstance(handler, urllib.request.ProxyHandler)]
    assert len(proxy_handlers) == 1
    assert getattr(proxy_handlers[0], "proxies", None) == {}


def test_official_api_keeps_credentials_out_of_plain_instance_fields():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test"),
        username="researcher@example.com",
        password="plain-password",
        token="plain-token",
    )

    assert "username" not in api.__dict__
    assert "password" not in api.__dict__
    assert "token" not in api.__dict__
    assert api.username == "researcher@example.com"
    assert api.password == "plain-password"
    assert api.token == "plain-token"

    api.token = "rotated-token"
    assert api.token == "rotated-token"
    assert api._credentials.token == "rotated-token"
    instance_repr = repr(api.__dict__)
    assert "plain-password" not in instance_repr
    assert "plain-token" not in instance_repr
    assert "rotated-token" not in instance_repr


def test_context_collection_methods_share_paginated_context_helper():
    for method_name in ("list_fields", "list_datasets", "list_operators", "list_user_alphas"):
        method_source = inspect.getsource(getattr(OfficialContextDataMixin, method_name))
        assert "_cached_paginated_context(" in method_source
        assert "_paginate_collection(" not in method_source

    helper_source = inspect.getsource(OfficialContextDataMixin._cached_paginated_context)
    assert "_paginate_collection(" in helper_source


def test_official_api_uses_composed_api_components():
    direct_mixins = {
        OfficialAuthProfileMixin,
        OfficialContextDataMixin,
        OfficialRequestMixin,
        OfficialSimulationSubmissionMixin,
        OfficialExpressionValidationMixin,
    }
    assert not direct_mixins.intersection(OfficialBrainAPI.__mro__)

    api = OfficialBrainAPI(OfficialAPIConfig(base_url="https://example.test"), token="token")
    assert api._auth_profile is not None
    assert api._context_data is not None
    assert api._request_client is not None
    assert api._simulation_submission is not None
    assert api._expression_validator is not None

    result = api.validate_expression(
        "rank(close)",
        {},
        known_operators={"rank"},
        known_fields={"close"},
    )

    assert result["status"] == "PASS"
    assert result["errors"] == []


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


def test_read_cache_warns_on_invalid_cache_file(caplog):
    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp),
            token="token",
        )
        cache_name = "fields_bad.json"
        api._cache_path(cache_name).write_text("{not-json", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = api._read_cache(cache_name)

    assert result["items"] == []
    assert result["fresh"] is False
    assert "error" in result
    assert "failed to read official API cache" in caplog.text


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


def test_list_user_alphas_dedupes_items_across_pages_without_page_cap(monkeypatch):
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
            if self.offset == 0:
                rows = [{"id": f"a{index}", "regular": f"rank(field_{index})"} for index in range(100)]
            else:
                rows = [
                    {"id": "a99", "regular": "rank(field_99)"},
                    {"id": "a100", "regular": "rank(field_100)"},
                ]
            return json.dumps({"count": 101, "results": rows}).encode()

    monkeypatch.setattr(pagination_limits, "MAX_USER_ALPHAS_PAGES", None)

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

    assert len(rows) == 101
    assert [row["id"] for row in rows][-2:] == ["a99", "a100"]
    assert len({row["id"] for row in rows}) == 101
    assert len(calls) == 2


def test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping(monkeypatch, caplog):
    calls = []
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, offset: int):
            self.offset = offset

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            if self.offset == 0:
                rows = [{"id": f"a{index}", "regular": f"rank(field_{index})"} for index in range(100)]
            elif self.offset == 100:
                rows = [{"id": f"a{index}", "regular": f"rank(alt_field_{index})"} for index in range(100)]
            else:
                rows = [{"id": "a100", "regular": "rank(field_100)"}]
            return json.dumps({"count": 101, "results": rows}).encode()

    monkeypatch.setattr(pagination_limits, "MAX_USER_ALPHAS_PAGES", None)

    with tempfile.TemporaryDirectory() as tmp, caplog.at_level(logging.WARNING):
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            offset = int(req.full_url.rsplit("offset=", 1)[-1].split("&", 1)[0])
            return Response(offset)

        api._open = fake_open
        rows = api.list_user_alphas("3d", progress_callback=progress.append)

    assert len(rows) == 101
    assert rows[-1]["id"] == "a100"
    assert len(calls) == 3
    assert [event.get("page_number") for event in progress] == [1, 2, 3]
    assert progress[0]["new_unique_items"] == 100
    assert progress[0]["duplicate_unique_items"] == 0
    assert progress[0]["unique_items"] == 100
    assert progress[0]["stalled_unique_pages"] == 0
    assert progress[1]["warning"] == "no_new_unique_items"
    assert progress[1]["new_unique_items"] == 0
    assert progress[1]["duplicate_unique_items"] == 100
    assert progress[1]["unique_items"] == 100
    assert progress[1]["stalled_unique_pages"] == 1
    assert progress[2]["new_unique_items"] == 1
    assert progress[2]["duplicate_unique_items"] == 0
    assert progress[2]["unique_items"] == 101
    assert progress[2]["stalled_unique_pages"] == 0
    assert "user_alphas pagination page added no new unique items" in caplog.text
    assert "user_alphas pagination reached max pages limit" not in caplog.text


def test_list_user_alphas_can_be_cancelled_by_progress_callback_without_page_cap(monkeypatch, caplog):
    calls = []
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, offset: int):
            self.offset = offset

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            rows = [
                {"id": f"a{self.offset + index}", "regular": f"rank(field_{self.offset + index})"}
                for index in range(100)
            ]
            return json.dumps({"count": 10_000, "results": rows}).encode()

    def cancel_after_second_page(event):
        progress.append(event)
        return len(progress) < 2

    monkeypatch.setattr(pagination_limits, "MAX_USER_ALPHAS_PAGES", None)

    with tempfile.TemporaryDirectory() as tmp, caplog.at_level(logging.WARNING):
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            offset = int(req.full_url.rsplit("offset=", 1)[-1].split("&", 1)[0])
            return Response(offset)

        api._open = fake_open
        rows = api.list_user_alphas("3d", progress_callback=cancel_after_second_page)

    assert len(rows) == 200
    assert [event["offset"] for event in progress] == [0, 100]
    assert len(calls) == 2
    assert "user_alphas pagination stopped by progress callback" in caplog.text
    assert "user_alphas pagination reached max pages limit" not in caplog.text


def test_list_fields_stops_at_max_pages_limit(monkeypatch, caplog):
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
            rows = [{"id": f"field_{self.offset + index}", "name": f"field_{self.offset + index}"} for index in range(50)]
            return json.dumps({"count": 1000, "results": rows}).encode()

    monkeypatch.setattr(pagination_limits, "MAX_FIELDS_PAGES", 2)

    with tempfile.TemporaryDirectory() as tmp, caplog.at_level(logging.WARNING):
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_open(req, timeout=None):
            calls.append(req.full_url)
            offset = int(req.full_url.rsplit("offset=", 1)[-1].split("&", 1)[0])
            return Response(offset)

        api._open = fake_open
        rows = api.list_fields("all")

    assert len(rows) == 100
    assert len(calls) == 2
    assert "fields pagination reached max pages limit (2)" in caplog.text


def test_list_user_alphas_has_no_default_page_limit(monkeypatch, caplog):
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
                if self.offset >= 600
                else [{"id": f"a{self.offset + index}", "regular": f"rank(field_{self.offset + index})"} for index in range(100)]
            )
            return json.dumps({"count": 300, "results": rows}).encode()

    monkeypatch.setattr(pagination_limits, "MAX_USER_ALPHAS_PAGES", None)

    with tempfile.TemporaryDirectory() as tmp, caplog.at_level(logging.WARNING):
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

    assert len(rows) == 600
    assert len(calls) == 7
    assert "user_alphas pagination reached max pages limit" not in caplog.text


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


def test_bearer_401_restores_token_when_fallback_auth_fails():
    calls = []

    def fake_open(req, timeout):
        authorization = req.headers.get("Authorization", "")
        calls.append(authorization)
        status = 401 if authorization.startswith("Bearer ") else 403
        raise urllib.error.HTTPError(
            "https://example.test",
            status,
            "Unauthorized",
            {},
            io.BytesIO(b'{"detail": "auth failed"}'),
        )

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

    try:
        api._request("GET", "/data-fields")
    except BrainAPIError as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("expected fallback auth failure")

    assert calls[0].startswith("Bearer ")
    assert calls[1].startswith("Basic ")
    assert api.token == "bad-token"


def test_request_rejects_cross_origin_absolute_url():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    try:
        api._request("GET", "https://evil.example/data-fields")
    except BrainAPIError as exc:
        assert "cross-origin" in str(exc) or "not a known BRAIN API endpoint" in str(exc)
    else:
        raise AssertionError("expected cross-origin URL to be rejected")


def test_request_rejects_untrusted_configured_base_url():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://evil.example", min_request_interval_seconds=0),
        token="token",
    )

    try:
        api._request("GET", "/data-fields")
    except BrainAPIError as exc:
        assert "not a known BRAIN API endpoint" in str(exc)
    else:
        raise AssertionError("expected untrusted base_url to be rejected")


def test_build_official_url_allows_reserved_offline_test_hosts():
    url = build_official_url("https://example.test", "/data-fields", {"limit": 1})

    assert url == "https://example.test/data-fields?limit=1"


def test_build_official_url_rejects_non_ascii_hostname():
    try:
        build_official_url("https://ｅxample.test", "/data-fields", None)
    except BrainAPIError as exc:
        assert "non-ASCII" in str(exc)
    else:
        raise AssertionError("expected non-ASCII host to be rejected")


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
        assert "cross-origin" in str(exc) or "not a known BRAIN API endpoint" in str(exc)
    else:
        raise AssertionError("expected cross-origin Location to be rejected")


def test_submit_simulation_normalizes_same_origin_location_header_to_path():
    captured = []

    class Response:
        headers = {
            "Content-Type": "application/json",
            "Location": "https://example.test/simulations/sim-123?progress=1",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"{}"

    def fake_open(req, timeout):
        captured.append(req.full_url)
        return Response()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._open = fake_open

    sim_id = api.submit_simulation("rank(close)", BrainSettings(region="USA", universe="TOP3000"))

    assert sim_id == "/simulations/sim-123?progress=1"
    assert captured == ["https://example.test/simulations"]


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
    assert first._last_request_at == 103.0
    assert second._last_request_at == 106.0
    assert first._request_lock.__class__.__name__ == "RLock"
