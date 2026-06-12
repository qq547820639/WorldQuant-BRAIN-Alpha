import io
from http.client import IncompleteRead, RemoteDisconnected
import http.cookiejar
import inspect
import json
import logging
import os
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain_alpha_ops.brain_api.base import BrainAPIError
import brain_alpha_ops.brain_api as brain_api_pkg
from brain_alpha_ops.brain_api import pagination_limits
from brain_alpha_ops.brain_api.official_auth import OfficialAuthProfileMixin
from brain_alpha_ops.brain_api.official_context import OfficialContextDataMixin
from brain_alpha_ops.brain_api.official_filtering import FilterRange
from brain_alpha_ops.brain_api.official import OfficialBrainAPI, build_simulation_payload, normalize_metrics
from brain_alpha_ops.brain_api.official_helpers import build_official_url, normal_field
from brain_alpha_ops.brain_api.official_request import OfficialRequestMixin
from brain_alpha_ops.brain_api.official_simulation import OfficialSimulationSubmissionMixin
from brain_alpha_ops.brain_api.official_validation import OfficialExpressionValidationMixin
from brain_alpha_ops.config import BrainSettings, OfficialAPIConfig


def _query_params(url: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)


def test_build_simulation_payload_contains_settings_and_expression():
    payload = build_simulation_payload("rank(close)", BrainSettings(region="USA", universe="TOP3000"))
    assert payload["type"] == "REGULAR"
    assert payload["regular"] == "rank(close)"
    assert payload["settings"]["region"] == "USA"
    assert payload["settings"]["language"] == "FASTEXPR"


def test_brain_api_package_exports_public_protocol_and_error():
    assert brain_api_pkg.BrainAPIError is BrainAPIError
    assert brain_api_pkg.BrainAPI.__name__ == "BrainAPI"


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
    assert "prod_correlation" not in metrics


def test_normalize_metrics_keeps_prod_correlation_separate_from_generic_correlation():
    metrics = normalize_metrics(
        {
            "is": {
                "sharpe": 1.4,
                "fitness": 1.1,
                "turnover": 0.2,
                "correlation": 0.31,
                "prodCorrelation": 0.27,
                "selfCorrelation": 0.22,
            },
            "checks": [{"name": "LOW_SHARPE", "result": "PASS"}],
        }
    )

    assert metrics["correlation"] == 0.31
    assert metrics["self_correlation"] == 0.22
    assert metrics["prod_correlation"] == 0.27


def test_normalize_metrics_documents_percentage_scale_turnover_contract():
    metrics = normalize_metrics({"is": {"turnover": 3.5}})

    assert metrics["turnover"] == 0.035


def test_normalize_metrics_preserves_sub_universe_size_fields():
    metrics = normalize_metrics(
        {
            "is": {
                "sharpe": 1.6,
                "fitness": 1.2,
                "turnover": 0.2,
                "subUniverseSharpe": 1.0,
                "subUniverseSize": 4000,
                "alphaSize": 1000,
            },
            "checks": [{"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS"}],
        }
    )

    assert metrics["sub_universe_sharpe"] == 1.0
    assert metrics["subUniverseSize"] == 4000
    assert metrics["alphaSize"] == 1000


def test_normalize_metrics_uses_low_sub_universe_check_value_when_root_metric_missing():
    metrics = normalize_metrics(
        {
            "is": {
                "sharpe": 1.9,
                "fitness": 1.06,
                "turnover": 0.5706,
            },
            "checks": [
                {"name": "LOW_SUB_UNIVERSE_SHARPE", "result": "PASS", "limit": 0.82, "value": 1.43},
            ],
        }
    )

    assert metrics["sub_universe_sharpe"] == 1.43
    assert metrics["brain_checks"]["LOW_SUB_UNIVERSE_SHARPE"]["value"] == 1.43


def test_normalize_metrics_omits_missing_sub_universe_metric_instead_of_defaulting_to_zero():
    metrics = normalize_metrics(
        {
            "is": {
                "sharpe": 1.9,
                "fitness": 1.06,
                "turnover": 0.5706,
            },
            "checks": [{"name": "LOW_SHARPE", "result": "PASS", "value": 1.9}],
        }
    )

    assert "sub_universe_sharpe" not in metrics


def test_normal_field_preserves_wqb_filter_metadata():
    field = normal_field(
        {
            "id": "close",
            "name": "Close Price",
            "description": "Daily close price.",
            "dataset": {"id": "pv1", "name": "Price Volume Data for Equity"},
            "type": "MATRIX",
            "category": {"id": "price"},
            "delay": 1,
            "coverage": "0.98",
            "userCount": 123,
            "alphaCount": 456,
        }
    )

    assert field["id"] == "close"
    assert field["name"] == "Close Price"
    assert field["description"] == "Daily close price."
    assert field["dataset_id"] == "pv1"
    assert field["dataset"]["id"] == "pv1"
    assert field["type"] == "MATRIX"
    assert field["userCount"] == 123
    assert field["alphaCount"] == 456
    assert field["category"] == "price"
    assert field["coverage"] == 0.98
    assert field["raw"]["id"] == "close"


def test_filter_range_generates_wqb_style_conditions():
    assert FilterRange.parse("[1.25, 2.5)").to_params("is.sharpe") == {
        "is.sharpe>=": "1.25",
        "is.sharpe<": "2.5",
    }
    assert FilterRange.parse("(-inf, 0.7]").to_params("is.prodCorrelation") == {
        "is.prodCorrelation<=": "0.7",
    }
    assert FilterRange.parse(["2026-01-01", "2026-02-01"]).to_params("dateCreated") == {
        "dateCreated>=": "2026-01-01",
        "dateCreated<=": "2026-02-01",
    }


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


def test_list_fields_dataset_query_key_can_match_wqb_dataset_id():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"results": [{"id": "close", "dataset": {"id": "pv1"}}]}'

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        return Response()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                data_fields_dataset_query_key="dataset.id",
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open
        fields = api.list_fields("all", "USA", dataset="pv1")

    query = _query_params(captured["url"])
    assert fields[0]["id"] == "close"
    assert query["dataset.id"] == ["pv1"]
    assert "dataset" not in query


def test_list_fields_does_not_inherit_scope_dataset_for_full_context_refresh():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"results": [{"id": "close", "dataset": {"id": "pv1"}}]}'

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        return Response()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                data_fields_dataset_query_key="dataset.id",
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api.set_market_scope(BrainSettings(region="USA", universe="TOP3000", dataset="pv1"))
        api._open = fake_open
        fields = api.list_fields("all", "USA")

    query = _query_params(captured["url"])
    assert fields[0]["id"] == "close"
    assert "dataset.id" not in query
    assert "dataset" not in query


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


def test_list_data_categories_uses_official_endpoint_and_preserves_raw():
    calls = []
    progress = []

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    def fake_request(method, path, **_kwargs):
        calls.append((method, path))
        return {
            "results": [
                {"id": "fundamental", "name": "Fundamental"},
                {"code": "analyst", "description": "Analyst Data"},
            ]
        }, {}

    api._request = fake_request

    categories = api.list_data_categories(progress_callback=progress.append)

    assert calls == [("GET", "/data-categories")]
    assert [row["id"] for row in categories] == ["fundamental", "analyst"]
    assert categories[0]["name"] == "Fundamental"
    assert categories[1]["name"] == "Analyst Data"
    assert categories[0]["raw"]["id"] == "fundamental"
    assert progress == [{
        "scanned": 2,
        "total": 2,
        "pagination_target": "single_collection",
        "pagination_complete": True,
    }]


def test_search_limited_methods_use_official_collection_params():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_open(req, timeout):
        calls.append(req.full_url)
        if req.full_url.startswith("https://example.test/data-fields?"):
            return Response({"count": 1, "results": [{"id": "close", "dataset": {"id": "pv1"}}]})
        return Response({"count": 1, "results": [{"id": "pv1", "fieldCount": 100}]})

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                data_fields_dataset_query_key="dataset.id",
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open

        fields = api.search_fields_limited(
            "close",
            "USA",
            dataset="pv1",
            field_type="MATRIX",
            category="price",
            coverage="[0.8, 1.0]",
            value_score="[2, inf)",
            alpha_count="[10, inf)",
            user_count="[5, 20]",
            order="-alphaCount",
            limit=25,
            offset=50,
        )
        datasets = api.search_datasets_limited(
            "price",
            "USA",
            category="fundamental",
            universe="TOP1000",
            delay=0,
            coverage="[0.75, inf)",
            value_score="[1.5, inf)",
            alpha_count="[10, 99]",
            user_count="[3, inf)",
            order="-userCount",
            limit=10,
            offset=20,
        )

    field_query = _query_params(calls[0])
    dataset_query = _query_params(calls[1])
    assert fields["count"] == 1
    assert fields["items"][0]["id"] == "close"
    assert field_query["search"] == ["close"]
    assert field_query["dataset.id"] == ["pv1"]
    assert field_query["type"] == ["MATRIX"]
    assert field_query["category"] == ["price"]
    assert field_query["coverage>="] == ["0.8"]
    assert field_query["coverage<="] == ["1.0"]
    assert field_query["valueScore>="] == ["2"]
    assert field_query["alphaCount>="] == ["10"]
    assert field_query["userCount>="] == ["5"]
    assert field_query["userCount<="] == ["20"]
    assert field_query["order"] == ["-alphaCount"]
    assert field_query["limit"] == ["25"]
    assert field_query["offset"] == ["50"]
    assert datasets["items"][0]["id"] == "pv1"
    assert dataset_query["search"] == ["price"]
    assert dataset_query["category"] == ["fundamental"]
    assert dataset_query["universe"] == ["TOP1000"]
    assert dataset_query["delay"] == ["0"]
    assert dataset_query["coverage>="] == ["0.75"]
    assert dataset_query["valueScore>="] == ["1.5"]
    assert dataset_query["alphaCount>="] == ["10"]
    assert dataset_query["alphaCount<="] == ["99"]
    assert dataset_query["userCount>="] == ["3"]
    assert dataset_query["order"] == ["-userCount"]
    assert dataset_query["limit"] == ["10"]
    assert dataset_query["offset"] == ["20"]


def test_search_methods_page_until_api_filter_window_count():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_open(req, timeout):
        calls.append(req.full_url)
        path = urllib.parse.urlsplit(req.full_url).path
        query = _query_params(req.full_url)
        limit = int(query["limit"][0])
        offset = int(query["offset"][0])
        if path.endswith("/data-fields"):
            items = [{"id": f"field_{index}", "dataset": {"id": "pv1"}} for index in range(offset, min(offset + limit, 3))]
            return Response({"count": 3, "results": items})
        items = [{"id": f"dataset_{index}", "fieldCount": 10 + index} for index in range(offset, min(offset + limit, 3))]
        return Response({"count": 3, "results": items})

    progress = []
    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                data_fields_dataset_query_key="dataset.id",
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open

        datasets = api.search_datasets("price", "USA", limit=2, progress_callback=progress.append)
        fields = api.search_fields("close", "USA", dataset="pv1", limit=2)

    assert [row["id"] for row in datasets] == ["dataset_0", "dataset_1", "dataset_2"]
    assert [row["id"] for row in fields] == ["field_0", "field_1", "field_2"]
    assert [urllib.parse.urlsplit(url).path for url in calls] == [
        "/data-sets",
        "/data-sets",
        "/data-sets",
        "/data-fields",
        "/data-fields",
        "/data-fields",
    ]
    dataset_queries = [_query_params(url) for url in calls[:3]]
    assert [(query["limit"][0], query["offset"][0]) for query in dataset_queries] == [
        ("1", "0"),
        ("2", "0"),
        ("1", "2"),
    ]
    field_count_query = _query_params(calls[3])
    assert field_count_query["dataset.id"] == ["pv1"]
    assert progress[-1]["api_reported_total"] == 3
    assert progress[-1]["filter_window_count"] == 3
    assert progress[-1]["pagination_complete"] is True
    assert progress[-1]["stop_reason"] == "api_total_reached"


def test_dataset_search_does_not_inherit_data_fields_dataset_key():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 1, "results": [{"id": "pv1", "fieldCount": 100}]}'

    def fake_open(req, timeout):
        calls.append(req.full_url)
        return Response()

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                data_fields_dataset_query_key="dataset.id",
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api.set_market_scope(BrainSettings(region="USA", universe="TOP3000", dataset="pv1"))
        api._open = fake_open

        datasets = api.search_datasets_limited("price", "USA", limit=10, offset=0)

    query = _query_params(calls[0])
    assert datasets["items"][0]["id"] == "pv1"
    assert "dataset.id" not in query
    assert "dataset" not in query


def test_discovery_compat_facade_maps_wqb_options_to_existing_search_params():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(self.payload).encode()

    def fake_open(req, timeout):
        calls.append(req.full_url)
        if req.full_url.startswith("https://example.test/data-fields?"):
            return Response({"count": 1, "results": [{"id": "close", "dataset": {"id": "pv1"}}]})
        return Response({"count": 1, "results": [{"id": "pv1", "fieldCount": 100}]})

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                data_fields_dataset_query_key="dataset.id",
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api._open = fake_open

        fields = api.discover_fields_limited(
            "close",
            options={"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1},
            dataset_id="pv1",
            type="MATRIX",
            coverage="[0.8, inf)",
            limit=25,
        )
        datasets = api.discover_datasets_limited(
            "price",
            options={"instrument_type": "EQUITY", "region": "USA", "universe": "TOP1000", "delay": 0},
            category="fundamental",
            limit=10,
        )

    field_query = _query_params(calls[0])
    dataset_query = _query_params(calls[1])
    assert fields["items"][0]["id"] == "close"
    assert field_query["instrumentType"] == ["EQUITY"]
    assert field_query["region"] == ["USA"]
    assert field_query["universe"] == ["TOP3000"]
    assert field_query["delay"] == ["1"]
    assert field_query["dataset.id"] == ["pv1"]
    assert field_query["type"] == ["MATRIX"]
    assert field_query["coverage>="] == ["0.8"]
    assert field_query["limit"] == ["25"]
    assert datasets["items"][0]["id"] == "pv1"
    assert dataset_query["instrumentType"] == ["EQUITY"]
    assert dataset_query["region"] == ["USA"]
    assert dataset_query["universe"] == ["TOP1000"]
    assert dataset_query["delay"] == ["0"]
    assert dataset_query["category"] == ["fundamental"]
    assert dataset_query["limit"] == ["10"]


def test_discovery_compat_facade_rejects_conflicting_or_unknown_options():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    try:
        api.discover_fields_limited("close", region="USA", options={"region": "EUR"})
    except BrainAPIError as exc:
        assert "conflicting region" in str(exc)
    else:
        raise AssertionError("expected conflicting discovery option to fail closed")

    try:
        api.discover_datasets_limited("price", options={"dataset_id": "pv1"})
    except BrainAPIError as exc:
        assert "dataset option is only supported for field discovery" in str(exc)
    else:
        raise AssertionError("expected dataset-scoped dataset discovery to fail closed")

    try:
        api.discover_fields_limited("close", options={"language": "FASTEXPR"})
    except BrainAPIError as exc:
        assert "unsupported options key" in str(exc)
    else:
        raise AssertionError("expected unsupported discovery option to fail closed")


def test_locate_methods_use_official_detail_paths():
    calls = []
    payloads = {
        "/data-sets/pv1": {"id": "pv1", "name": "Price Volume", "fieldCount": 100},
        "/data-fields/close": {"id": "close", "dataset": {"id": "pv1"}, "type": "MATRIX"},
        "/alphas/prodAlpha123": {
            "id": "prodAlpha123",
            "regular": "rank(close)",
            "settings": {"region": "USA"},
        },
    }

    def fake_request(method, path, **_kwargs):
        calls.append((method, path))
        return payloads[path], {}

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = fake_request

    dataset = api.locate_dataset("pv1")
    field = api.locate_field("close")
    alpha = api.locate_alpha("prodAlpha123")

    assert calls == [
        ("GET", "/data-sets/pv1"),
        ("GET", "/data-fields/close"),
        ("GET", "/alphas/prodAlpha123"),
    ]
    assert dataset["id"] == "pv1"
    assert field["dataset_id"] == "pv1"
    assert alpha["id"] == "prodAlpha123"
    assert alpha["expression"] == "rank(close)"


def test_locate_compat_aliases_use_existing_normalized_detail_contracts():
    calls = []
    payloads = {
        "/data-sets/pv1": {"id": "pv1", "name": "Price Volume", "fieldCount": 100},
        "/data-fields/close": {"id": "close", "dataset": {"id": "pv1"}, "type": "MATRIX"},
        "/alphas/prodAlpha123": {
            "id": "prodAlpha123",
            "regular": "rank(close)",
            "settings": {"region": "USA"},
        },
    }

    def fake_request(method, path, **_kwargs):
        calls.append((method, path))
        return payloads[path], {}

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = fake_request

    dataset = api.get_dataset(id="pv1")
    field = api.get_field(id="close")
    alpha = api.get_alpha(id="prodAlpha123")

    assert calls == [
        ("GET", "/data-sets/pv1"),
        ("GET", "/data-fields/close"),
        ("GET", "/alphas/prodAlpha123"),
    ]
    assert dataset["id"] == "pv1"
    assert dataset["field_count"] == 100
    assert field["dataset_id"] == "pv1"
    assert alpha["expression"] == "rank(close)"


def test_filter_alphas_limited_uses_wqb_filter_query_keys():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 1, "results": [{"id": "prodAlpha123", "regular": "rank(close)"}]}'

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        return Response()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._open = fake_open

    result = api.filter_alphas_limited(
        name="mean-reversion",
        competition="brain",
        alpha_type="REGULAR",
        status="UNSUBMITTED",
        date_created="(2026-01-01, 2026-02-01]",
        instrument_type="EQUITY",
        region="USA",
        universe="TOP3000",
        sharpe="[1.25, inf)",
        fitness="[1.0, inf)",
        turnover="[0.01, 0.7]",
        prod_correlation="(-inf, 0.7]",
        self_correlation="(-inf, 0.65]",
        returns="[0.02, inf)",
        pnl="[1000, inf)",
        drawdown="(-inf, 0.2]",
        margin="[0.01, 0.1]",
        book_size="[1000000, inf)",
        long_count="[10, 200]",
        short_count="[10, 200]",
        os_sharpe="[0.9, inf)",
        os_fitness="[0.8, inf)",
        os_turnover="[0.02, 0.6]",
        os_returns="[0.01, inf)",
        os_pnl="[500, inf)",
        os_drawdown="(-inf, 0.25]",
        os_margin="[0.01, 0.09]",
        os_long_count="[8, 190]",
        os_short_count="[8, 190]",
        date_submitted="[2026-02-01, 2026-03-01]",
        start_date="[2026-01-15, 2026-04-15]",
        language="FASTEXPR",
        decay=8,
        neutralization="SUBINDUSTRY",
        pasteurization="ON",
        truncation="[0.01, 0.08]",
        unit_handling="VERIFY",
        nan_handling="ON",
        hidden=False,
        favorite=True,
        category="price",
        color="blue",
        tag="robust",
        stage="IS\x1fOS",
        order="-dateCreated",
        limit=100,
        offset=0,
    )

    query = _query_params(captured["url"])
    assert result["count"] == 1
    assert result["items"][0]["id"] == "prodAlpha123"
    assert query["name"] == ["mean-reversion"]
    assert query["competition"] == ["brain"]
    assert query["type"] == ["REGULAR"]
    assert query["status"] == ["UNSUBMITTED"]
    assert query["settings.instrumentType"] == ["EQUITY"]
    assert query["settings.region"] == ["USA"]
    assert query["settings.universe"] == ["TOP3000"]
    assert query["dateCreated>"] == ["2026-01-01"]
    assert query["dateCreated<="] == ["2026-02-01"]
    assert query["dateSubmitted>="] == ["2026-02-01"]
    assert query["dateSubmitted<="] == ["2026-03-01"]
    assert query["startDate>="] == ["2026-01-15"]
    assert query["startDate<="] == ["2026-04-15"]
    assert query["is.sharpe>="] == ["1.25"]
    assert query["is.fitness>="] == ["1.0"]
    assert query["is.turnover>="] == ["0.01"]
    assert query["is.turnover<="] == ["0.7"]
    assert query["is.prodCorrelation<="] == ["0.7"]
    assert query["is.selfCorrelation<="] == ["0.65"]
    assert query["is.returns>="] == ["0.02"]
    assert query["is.pnl>="] == ["1000"]
    assert query["is.drawdown<="] == ["0.2"]
    assert query["is.margin>="] == ["0.01"]
    assert query["is.margin<="] == ["0.1"]
    assert query["is.bookSize>="] == ["1000000"]
    assert query["is.longCount>="] == ["10"]
    assert query["is.longCount<="] == ["200"]
    assert query["is.shortCount>="] == ["10"]
    assert query["is.shortCount<="] == ["200"]
    assert query["os.sharpe>="] == ["0.9"]
    assert query["os.fitness>="] == ["0.8"]
    assert query["os.turnover>="] == ["0.02"]
    assert query["os.turnover<="] == ["0.6"]
    assert query["os.returns>="] == ["0.01"]
    assert query["os.pnl>="] == ["500"]
    assert query["os.drawdown<="] == ["0.25"]
    assert query["os.margin>="] == ["0.01"]
    assert query["os.margin<="] == ["0.09"]
    assert query["os.longCount>="] == ["8"]
    assert query["os.longCount<="] == ["190"]
    assert query["os.shortCount>="] == ["8"]
    assert query["os.shortCount<="] == ["190"]
    assert query["settings.decay"] == ["8"]
    assert query["settings.language"] == ["FASTEXPR"]
    assert query["settings.neutralization"] == ["SUBINDUSTRY"]
    assert query["settings.pasteurization"] == ["ON"]
    assert query["settings.truncation>="] == ["0.01"]
    assert query["settings.truncation<="] == ["0.08"]
    assert query["settings.unitHandling"] == ["VERIFY"]
    assert query["settings.nanHandling"] == ["ON"]
    assert query["hidden"] == ["false"]
    assert query["favorite"] == ["true"]
    assert query["category"] == ["price"]
    assert query["color"] == ["blue"]
    assert query["tag"] == ["robust"]
    assert query["stage"] == ["IS\x1fOS"]
    assert query["order"] == ["-dateCreated"]
    assert query["limit"] == ["100"]
    assert query["offset"] == ["0"]


def test_filter_compat_facade_maps_wqb_options_to_existing_alpha_filter_params():
    captured = {}

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 1, "results": [{"id": "prodAlpha123", "regular": "rank(close)"}]}'

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        return Response()

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._open = fake_open

    result = api.query_alphas_limited(
        options={"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000", "delay": 1},
        type="REGULAR",
        sharpe="[1.25, inf)",
        limit=100,
    )

    query = _query_params(captured["url"])
    assert result["items"][0]["id"] == "prodAlpha123"
    assert query["settings.instrumentType"] == ["EQUITY"]
    assert query["settings.region"] == ["USA"]
    assert query["settings.universe"] == ["TOP3000"]
    assert query["settings.delay"] == ["1"]
    assert query["type"] == ["REGULAR"]
    assert query["is.sharpe>="] == ["1.25"]
    assert query["limit"] == ["100"]


def test_filter_compat_facade_rejects_conflicting_options():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    try:
        api.query_alphas_limited(region="USA", options={"region": "EUR"})
    except BrainAPIError as exc:
        assert "conflicting region" in str(exc)
    else:
        raise AssertionError("expected conflicting filter option to fail closed")


def test_filter_alphas_limited_enforces_wqb_page_window():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    for kwargs in ({"limit": 101}, {"limit": 100, "offset": 10_000}, {"limit": 0}):
        try:
            api.filter_alphas_limited(**kwargs)
        except BrainAPIError as exc:
            assert "user alpha" in str(exc)
        else:
            raise AssertionError(f"expected filter_alphas_limited to reject {kwargs}")


def test_filter_alphas_paginates_to_filter_window_count():
    calls = []
    progress = []

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            offset = int(query.get("offset", 0))
            calls.append(query)
            if offset == 0:
                return {
                    "count": 3,
                    "results": [
                        {"id": "a1", "regular": "rank(close)"},
                        {"id": "a2", "regular": "rank(open)"},
                    ],
                }, {}
            if offset == 2:
                return {"count": 3, "results": [{"id": "a3", "regular": "rank(volume)"}]}, {}
            raise AssertionError(f"unexpected offset {offset}")

        api._request = fake_request
        rows = api.filter_alphas(
            status="UNSUBMITTED",
            sharpe="[1.25, inf)",
            limit=2,
            progress_callback=progress.append,
        )

    assert [row["id"] for row in rows] == ["a1", "a2", "a3"]
    assert [call["offset"] for call in calls] == [0, 2]
    assert all(call["status"] == "UNSUBMITTED" for call in calls)
    assert all(call["is.sharpe>="] == "1.25" for call in calls)
    assert progress[-1]["api_reported_total"] == 3
    assert progress[-1]["filter_window_count"] == 3
    assert progress[-1]["pagination_target"] == "api_filter_window"
    assert progress[-1]["pagination_complete"] is True


def test_filter_alphas_accepts_wqb_type_alias():
    calls = []

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_request(_method, _path, *, query=None, **_kwargs):
            calls.append(dict(query or {}))
            return {"count": 1, "results": [{"id": "a1", "regular": "rank(close)"}]}, {}

        api._request = fake_request
        rows = api.filter_alphas(type="REGULAR", limit=100)

    assert rows[0]["id"] == "a1"
    assert calls[0]["type"] == "REGULAR"


def test_filter_alphas_stops_at_wqb_filter_window_boundary():
    calls = []
    progress = []

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            offset = int(query.get("offset", 0))
            calls.append(offset)
            if offset != 9900:
                raise AssertionError(f"filter_alphas must not request offset {offset}")
            return {
                "count": 12000,
                "results": [
                    {"id": f"a{offset + index}", "regular": f"rank(field_{index})"}
                    for index in range(100)
                ],
            }, {}

        api._request = fake_request
        rows = api.filter_alphas(status="UNSUBMITTED", limit=100, offset=9900, progress_callback=progress.append)

    assert len(rows) == 100
    assert calls == [9900]
    assert progress[-1]["api_reported_total"] == 12_000
    assert progress[-1]["filter_window_count"] == 10_000
    assert progress[-1]["stop_reason"] == "filter_window_exhausted"


def test_filter_alphas_adjusts_final_limit_at_wqb_window_boundary():
    calls = []

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            offset = int(query.get("offset", 0))
            limit = int(query.get("limit", 0))
            calls.append((offset, limit))
            if offset + limit > 10_000:
                raise AssertionError(f"invalid WQB window request offset={offset} limit={limit}")
            return {
                "count": 10000,
                "results": [
                    {"id": f"a{offset + index}", "regular": f"rank(field_{offset + index})"}
                    for index in range(limit)
                ],
            }, {}

        api._request = fake_request
        rows = api.filter_alphas(status="UNSUBMITTED", limit=30, offset=9900)

    assert len(rows) == 100
    assert calls == [(9900, 30), (9930, 30), (9960, 30), (9990, 10)]


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


def test_official_context_collections_refresh_full_page_boundary_cache():
    cases = [
        (
            "fields",
            lambda api: api.list_fields("all", "USA"),
            {
                "instrumentType": "EQUITY",
                "region": "USA",
                "delay": 1,
                "universe": "TOP3000",
                "limit": 50,
                "offset": 0,
            },
            50,
            lambda offset, index: {"name": f"field_{offset + index}", "category": "pv"},
            lambda index: {"name": f"cached_field_{index}", "category": "pv"},
            lambda row: row["name"],
        ),
        (
            "datasets",
            lambda api: api.list_datasets("all", "USA"),
            {
                "instrumentType": "EQUITY",
                "region": "USA",
                "delay": 1,
                "universe": "TOP3000",
                "limit": 50,
                "offset": 0,
            },
            50,
            lambda offset, index: {"id": f"dataset_{offset + index}", "name": f"Dataset {offset + index}", "fieldCount": 1},
            lambda index: {"id": f"cached_dataset_{index}", "name": f"Cached Dataset {index}", "fieldCount": 1},
            lambda row: row["id"],
        ),
        (
            "operators",
            lambda api: api.list_operators("all"),
            {"search": "", "limit": 100, "offset": 0},
            100,
            lambda offset, index: {"name": f"op_{offset + index}", "category": "ts"},
            lambda index: {"name": f"cached_op_{index}", "category": "ts"},
            lambda row: row["name"],
        ),
    ]

    for cache_kind, call_method, cache_params, page_limit, row_factory, cached_row_factory, identity in cases:
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
                    if self.offset >= page_limit * 2
                    else [row_factory(self.offset, index) for index in range(page_limit)]
                )
                return json.dumps({"count": page_limit, "results": rows}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            api = OfficialBrainAPI(
                OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
                token="token",
            )
            cache_name = api._cache_key(cache_kind, cache_params)
            api._cache_path(cache_name).write_text(
                json.dumps({
                    "created_at": time.time(),
                    "items": [cached_row_factory(index) for index in range(page_limit)],
                    "total": page_limit,
                }),
                encoding="utf-8",
            )

            def fake_open(req, timeout=None):
                calls.append(req.full_url)
                query = req.full_url.split("?", 1)[1]
                offset = int(next(part.split("=", 1)[1] for part in query.split("&") if part.startswith("offset=")))
                return Response(offset)

            api._open = fake_open
            rows = call_method(api)

        assert len(rows) == page_limit * 2, cache_kind
        assert not identity(rows[0]).startswith("cached_"), cache_kind
        assert len(calls) == 3, cache_kind
        assert any(f"offset={page_limit}" in url for url in calls), cache_kind
        assert any(f"offset={page_limit * 2}" in url for url in calls), cache_kind


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


def test_official_context_collections_confirm_full_page_when_total_is_underreported():
    cases = [
        ("fields", lambda api: api.list_fields("all", "USA"), 50, lambda offset, index: {"name": f"field_{offset + index}", "category": "pv"}),
        ("datasets", lambda api: api.list_datasets("all", "USA"), 50, lambda offset, index: {"id": f"dataset_{offset + index}", "name": f"Dataset {offset + index}", "fieldCount": 1}),
        ("operators", lambda api: api.list_operators("all"), 100, lambda offset, index: {"name": f"op_{offset + index}", "category": "ts"}),
    ]

    for label, call_method, page_limit, row_factory in cases:
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
                    if self.offset >= page_limit * 2
                    else [row_factory(self.offset, index) for index in range(page_limit)]
                )
                return json.dumps({"count": page_limit, "results": rows}).encode()

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
            rows = call_method(api)

        assert len(rows) == page_limit * 2, label
        assert len(calls) == 3, label
        assert any(f"offset={page_limit}" in url for url in calls), label
        assert any(f"offset={page_limit * 2}" in url for url in calls), label


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


def test_list_user_alphas_defaults_to_all_without_days_filter():
    calls = []
    progress = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 1, "results": [{"id": "a1"}]}'

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(
                base_url="https://example.test",
                cache_dir=tmp,
                min_request_interval_seconds=0,
            ),
            token="token",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()
        rows = api.list_user_alphas(progress_callback=progress.append)

    assert [row["id"] for row in rows] == ["a1"]
    assert progress[-1]["range"] == "all"
    assert calls
    assert "days=" not in calls[0]


def test_list_user_alphas_force_refresh_bypasses_fresh_user_alpha_cache():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 1, "results": [{"id": "remote_a1"}]}'

    with tempfile.TemporaryDirectory() as tmp:
        config = OfficialAPIConfig(
            base_url="https://example.test",
            cache_dir=tmp,
            min_request_interval_seconds=0,
            context_cache_ttl_seconds=3600,
        )
        api = OfficialBrainAPI(config, token="token")
        cache_name = api._cache_key("user_alphas", {"limit": 100, "offset": 0})
        api._cache_path(cache_name).write_text(
            json.dumps({"created_at": time.time(), "total": 1, "items": [{"id": "cached_a1"}]}),
            encoding="utf-8",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()

        rows = api.list_user_alphas(force_refresh=True)

    assert [row["id"] for row in rows] == ["remote_a1"]
    assert calls


def test_list_user_alphas_refreshes_fresh_partial_user_alpha_cache():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"count": 1, "results": [{"id": "remote_a1"}]}'

    with tempfile.TemporaryDirectory() as tmp:
        config = OfficialAPIConfig(
            base_url="https://example.test",
            cache_dir=tmp,
            min_request_interval_seconds=0,
            context_cache_ttl_seconds=3600,
        )
        api = OfficialBrainAPI(config, token="token")
        cache_name = api._cache_key("user_alphas", {"limit": 100, "offset": 0})
        api._cache_path(cache_name).write_text(
            json.dumps({"created_at": time.time(), "total": 3, "items": [{"id": "cached_a1"}]}),
            encoding="utf-8",
        )
        api._open = lambda req, timeout=None: calls.append(req.full_url) or Response()

        rows = api.list_user_alphas()

    assert [row["id"] for row in rows] == ["remote_a1"]
    assert calls


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
            json.dumps({"created_at": time.time(), "total": 2, "items": [{"id": "a1"}, {"id": "a2"}]}),
            encoding="utf-8",
        )

        rows = api.list_user_alphas("3d", progress_callback=progress.append)

    assert len(rows) == 2
    assert progress[-1]["scanned"] == 2
    assert progress[-1]["total"] == 2
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


def test_list_fields_has_no_default_page_or_item_limit(caplog):
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
                if self.offset >= 250
                else [{"id": f"field_{self.offset + index}", "name": f"field_{self.offset + index}"} for index in range(50)]
            )
            return json.dumps({"count": 250, "results": rows}).encode()

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

    assert len(rows) == 250
    assert len(calls) == 6
    assert "fields pagination reached max pages limit" not in caplog.text
    assert "fields pagination reached max item limit" not in caplog.text


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


def test_list_user_alphas_retries_transient_page_504_without_truncating(monkeypatch):
    calls = []
    progress = []
    sleeps = []
    attempts_by_offset: dict[int, int] = {}

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        monkeypatch.setattr("brain_alpha_ops.brain_api.pagination.time.sleep", lambda seconds: sleeps.append(seconds))

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            offset = int(query.get("offset", 0))
            calls.append(offset)
            attempts_by_offset[offset] = attempts_by_offset.get(offset, 0) + 1
            if offset == 100 and attempts_by_offset[offset] == 1:
                raise BrainAPIError("HTTP 504: gateway timeout", status_code=504)
            rows = (
                []
                if offset >= 300
                else [{"id": f"a{offset + index}", "regular": f"rank(field_{offset + index})"} for index in range(100)]
            )
            return {"count": 10000, "results": rows}, {}

        api._request = fake_request
        rows = api.list_user_alphas("all", progress_callback=progress.append)

    assert len(rows) == 300
    assert calls == [0, 100, 100, 200, 300]
    assert sleeps == [5.0]
    retry_progress = [row for row in progress if row.get("warning") == "transient_page_retry"]
    assert retry_progress == [
        {
            "range": "all",
            "scanned": 100,
            "total": 10000,
            "pagination_target": "api_filter_window",
            "page_size": 0,
            "offset": 100,
            "warning": "transient_page_retry",
            "retry_attempt": 1,
            "retry_after_seconds": 5.0,
            "error_status": 504,
        }
    ]


def test_list_user_alphas_narrows_by_date_after_repeated_transient_504(monkeypatch):
    calls: list[dict[str, object]] = []
    progress: list[dict[str, object]] = []
    sleeps: list[float] = []
    attempts_by_key: dict[tuple[int, str], int] = {}

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        monkeypatch.setattr("brain_alpha_ops.brain_api.pagination.time.sleep", lambda seconds: sleeps.append(seconds))

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            calls.append(query)
            offset = int(query.get("offset", 0))
            cursor = str(query.get("dateCreated<") or "")
            attempts_key = (offset, cursor)
            attempts_by_key[attempts_key] = attempts_by_key.get(attempts_key, 0) + 1
            if offset == 100 and not cursor:
                raise BrainAPIError("HTTP 504: gateway timeout", status_code=504)
            if not cursor:
                return {
                    "count": 10000,
                    "results": [
                        {
                            "id": f"new_{index}",
                            "regular": "rank(close)",
                            "dateCreated": f"2026-01-02T00:{index:02d}:00-04:00",
                        }
                        for index in range(100)
                    ],
                }, {}
            return {
                "count": 2,
                "results": [
                    {"id": "old_1", "regular": "rank(open)", "dateCreated": "2026-01-01T00:00:00-04:00"},
                    {"id": "old_2", "regular": "rank(volume)", "dateCreated": "2025-12-31T00:00:00-04:00"},
                ],
            }, {}

        api._request = fake_request
        rows = api.list_user_alphas("all", progress_callback=progress.append)

    assert len(rows) == 102
    assert [int(call.get("offset", 0) or 0) for call in calls] == [0, 100, 100, 100, 100, 0]
    assert calls[-1]["dateCreated<"] == "2026-01-02T00:99:00-04:00"
    assert sleeps == [5.0, 5.0, 5.0, 5.0]
    retry_progress = [row for row in progress if row.get("warning") == "transient_page_retry"]
    assert [row["retry_attempt"] for row in retry_progress] == [1, 2, 3]
    narrowed_progress = [row for row in progress if row.get("warning") == "transient_page_retry_narrowed_by_date"]
    assert narrowed_progress == [
        {
            "range": "all",
            "scanned": 100,
            "total": 10000,
            "pagination_target": "api_filter_window",
            "page_size": 0,
            "offset": 0,
            "cursor_before": "2026-01-02T00:99:00-04:00",
            "warning": "transient_page_retry_narrowed_by_date",
            "retry_attempt": 3,
            "retry_exhausted": True,
            "retry_after_seconds": 5.0,
            "error_status": 504,
        }
    ]
    assert rows[-1]["id"] == "old_2"


def test_list_user_alphas_retries_transport_page_errors_without_truncating(monkeypatch):
    def wrapped_ssl_eof_error() -> BrainAPIError:
        cause = urllib.error.URLError(
            ssl.SSLEOFError("UNEXPECTED_EOF_WHILE_READING")
        )
        error = BrainAPIError(f"network error: {cause}")
        error.__cause__ = cause
        return error

    transient_errors = (
        IncompleteRead(b'{"count": 10000, "results": [', 4096),
        RemoteDisconnected("Remote end closed connection without response"),
        TimeoutError("The read operation timed out"),
        wrapped_ssl_eof_error(),
    )

    for transient_error in transient_errors:
        calls = []
        progress = []
        sleeps = []
        attempts_by_offset: dict[int, int] = {}

        with tempfile.TemporaryDirectory() as tmp:
            api = OfficialBrainAPI(
                OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
                token="token",
            )

            monkeypatch.setattr("brain_alpha_ops.brain_api.pagination.time.sleep", lambda seconds: sleeps.append(seconds))

            def fake_request(_method, _path, *, query=None, **_kwargs):
                query = dict(query or {})
                offset = int(query.get("offset", 0))
                calls.append(offset)
                attempts_by_offset[offset] = attempts_by_offset.get(offset, 0) + 1
                if offset == 100 and attempts_by_offset[offset] == 1:
                    raise transient_error
                rows = (
                    []
                    if offset >= 300
                    else [{"id": f"a{offset + index}", "regular": f"rank(field_{offset + index})"} for index in range(100)]
                )
                return {"count": 10000, "results": rows}, {}

            api._request = fake_request
            rows = api.list_user_alphas("all", progress_callback=progress.append)

        assert len(rows) == 300
        assert calls == [0, 100, 100, 200, 300]
        assert sleeps == [5.0]
        retry_progress = [row for row in progress if row.get("warning") == "transient_page_retry"]
        assert retry_progress == [
            {
                "range": "all",
                "scanned": 100,
                "total": 10000,
                "pagination_target": "api_filter_window",
                "page_size": 0,
                "offset": 100,
                "warning": "transient_page_retry",
                "retry_attempt": 1,
                "retry_after_seconds": 5.0,
                "error_status": None,
            }
        ]


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


def test_list_user_alphas_does_not_stop_on_full_api_filter_window_total():
    calls = []
    progress = []

    with tempfile.TemporaryDirectory() as tmp:
        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", cache_dir=tmp, min_request_interval_seconds=0),
            token="token",
        )

        def fake_request(_method, _path, *, query=None, **_kwargs):
            query = dict(query or {})
            offset = int(query.get("offset", 0))
            calls.append(offset)
            if offset == 0:
                return {
                    "count": 100,
                    "results": [
                        {"id": f"a{index}", "regular": "rank(close)", "dateCreated": f"2026-01-02T00:{index:02d}:00-04:00"}
                        for index in range(100)
                    ],
                }, {}
            if offset == 100:
                return {
                    "count": 100,
                    "results": [
                        {"id": "a100", "regular": "rank(open)", "dateCreated": "2026-01-01T00:00:00-04:00"}
                    ],
                }, {}
            raise AssertionError(f"unexpected offset {offset}")

        api._request = fake_request
        rows = api.list_user_alphas("all", progress_callback=progress.append)

    assert calls == [0, 100]
    assert len(rows) == 101
    assert progress[0]["pagination_target"] == "api_filter_window"
    assert progress[0]["has_more"] is True
    assert progress[0]["pagination_complete"] is False
    assert "stop_reason" not in progress[0]
    assert progress[-1]["stop_reason"] == "short_page"


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
    api._auth_profile._has_session_cookie = lambda: True
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


def test_basic_401_authenticates_once_then_retries_request():
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, raw: bytes):
            self._raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._raw

    def fake_open(req, timeout):
        calls.append((req.get_method(), req.full_url, req.headers.get("Authorization", "")))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                req.full_url,
                401,
                "Unauthorized",
                {},
                io.BytesIO(b'{"detail": "session expired"}'),
            )
        if req.full_url.endswith("/authentication"):
            return Response(b'{"token": "fresh-token"}')
        return Response(b'{"status": "ok"}')

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0, rate_limit_retry_attempts=0),
        username="user",
        password="pass",
    )
    api._open = fake_open

    data, _headers = api._request("GET", "/data-fields")

    assert data["status"] == "ok"
    assert calls[0][0] == "GET"
    assert calls[0][2].startswith("Basic ")
    assert calls[1][0] == "POST"
    assert calls[1][1] == "https://example.test/authentication"
    assert calls[2][0] == "GET"
    assert calls[2][2] == "Bearer fresh-token"


def test_cookie_auth_failure_authenticates_once_then_retries_request():
    for status_code in (401, 403):
        _assert_cookie_auth_failure_reauthenticates(status_code)


def _assert_cookie_auth_failure_reauthenticates(status_code: int):
    calls = []

    class Response:
        headers = {"Content-Type": "application/json"}

        def __init__(self, raw: bytes):
            self._raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self._raw

    def fake_open(req, timeout):
        calls.append((req.get_method(), req.full_url, req.headers.get("Authorization", "")))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                req.full_url,
                status_code,
                "Unauthorized" if status_code == 401 else "Forbidden",
                {},
                io.BytesIO(b'{"detail": "session expired"}'),
            )
        if req.full_url.endswith("/authentication"):
            return Response(b'{"status": "ok"}')
        return Response(b'{"status": "ok"}')

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0, rate_limit_retry_attempts=0),
        username="user",
        password="pass",
    )
    api._prefer_cookie_auth = True
    api._cookie_jar.set_cookie(http.cookiejar.Cookie(
        version=0,
        name="session",
        value="cookie-value",
        port=None,
        port_specified=False,
        domain="example.test",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    ))
    api._open = fake_open

    data, _headers = api._request("GET", "/data-fields")

    assert data["status"] == "ok"
    assert calls[0] == ("GET", "https://example.test/data-fields", "")
    assert calls[1][0] == "POST"
    assert calls[1][1] == "https://example.test/authentication"
    assert calls[1][2].startswith("Basic ")
    assert calls[2] == ("GET", "https://example.test/data-fields", "")


def test_auth_retry_does_not_recurse_on_authentication_endpoint():
    calls = []

    def fake_open(req, timeout):
        calls.append((req.get_method(), req.full_url))
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"detail": "bad credentials"}'),
        )

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0, rate_limit_retry_attempts=0),
        username="user",
        password="pass",
    )
    api._open = fake_open

    try:
        api._request("POST", "/authentication", headers={"Authorization": f"Basic {api._basic_auth()}"})
    except BrainAPIError as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected authentication endpoint failure")

    assert calls == [("POST", "https://example.test/authentication")]


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


def test_check_alpha_fails_closed_for_pending_unknown_and_empty_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    responses = iter([
        {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}, {"name": "SELF_CORRELATION", "status": "PENDING"}]},
        {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}, {"name": "UNSHAPED"}]},
        {},
    ])
    api._request = lambda method, path, **kwargs: (next(responses), {})

    pending = api.check_alpha("prodAlpha123")
    assert pending["status"] == "PENDING"
    assert pending["complete"] is False
    assert [row["name"] for row in pending["pending_checks"]] == ["SELF_CORRELATION"]

    unknown = api.check_alpha("prodAlpha123")
    assert unknown["status"] == "UNKNOWN"
    assert unknown["complete"] is False
    assert [row["name"] for row in unknown["unknown_checks"]] == ["UNSHAPED"]

    empty = api.check_alpha("prodAlpha123")
    assert empty["status"] == "UNKNOWN"
    assert empty["complete"] is False
    assert empty["checks"] == []


def test_check_alpha_passes_only_when_all_checks_explicitly_pass():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: (
        {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}, {"name": "PROD_CORRELATION", "status": "PASSED"}]},
        {},
    )

    result = api.check_alpha("prodAlpha123")

    assert result["status"] == "PASSED"
    assert result["complete"] is True
    assert len(result["passed_checks"]) == 2
    assert result["failed_checks"] == []
    assert result["pending_checks"] == []
    assert result["unknown_checks"] == []


def test_check_alpha_reads_wqb_nested_is_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: (
        {"is": {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}, {"name": "LOW_FITNESS", "status": "PASSED"}]}},
        {},
    )

    result = api.check_alpha("prodAlpha123")

    assert result["status"] == "PASSED"
    assert result["complete"] is True
    assert [row["name"] for row in result["passed_checks"]] == ["LOW_SHARPE", "LOW_FITNESS"]


def test_check_alpha_merges_all_nested_check_groups_fail_closed():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: (
        {
            "is": {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}]},
            "os": {"checks": [{"name": "OUT_SAMPLE_DECAY", "result": "FAIL"}]},
        },
        {},
    )

    result = api.check_alpha("prodAlpha123")

    assert result["status"] == "FAILED"
    assert result["complete"] is True
    assert [row["name"] for row in result["checks"]] == ["LOW_SHARPE", "OUT_SAMPLE_DECAY"]
    assert [row["name"] for row in result["failed_checks"]] == ["OUT_SAMPLE_DECAY"]


def test_check_alpha_merges_top_level_and_nested_checks_fail_closed():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: (
        {
            "checks": [{"name": "LOW_SHARPE", "result": "PASS"}],
            "is": {"checks": [{"name": "LOW_FITNESS", "result": "PASS"}]},
            "os": {"checks": [{"name": "OUT_SAMPLE_DECAY", "result": "FAIL"}]},
        },
        {},
    )

    result = api.check_alpha("prodAlpha123")

    assert result["status"] == "FAILED"
    assert result["complete"] is True
    assert [row["name"] for row in result["checks"]] == [
        "LOW_SHARPE",
        "LOW_FITNESS",
        "OUT_SAMPLE_DECAY",
    ]
    assert [row["name"] for row in result["failed_checks"]] == ["OUT_SAMPLE_DECAY"]


def test_check_alpha_does_not_trust_top_level_status_without_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: ({"status": "PASSED"}, {})

    result = api.check_alpha("prodAlpha123")

    assert result["status"] == "UNKNOWN"
    assert result["complete"] is False
    assert result["checks"] == []


def test_poll_until_complete_respects_retry_after_on_running_response(monkeypatch):
    sleeps: list[float] = []
    responses = iter([
        ({"status": "RUNNING"}, {"Retry-After": "0.25"}),
        ({"alpha": "prodAlpha123"}, {}),
    ])

    api = OfficialBrainAPI(
        OfficialAPIConfig(
            base_url="https://example.test",
            min_request_interval_seconds=0,
            poll_attempts=3,
            poll_interval_seconds=9.0,
        ),
        token="token",
    )
    api._request = lambda method, path, **kwargs: next(responses)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))

    result = api.poll_until_complete("/simulations/sim-123")

    assert result == "COMPLETED"
    assert sleeps == [0.25]


def test_official_api_exposes_wqb_style_concurrent_helpers():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    assert callable(api.concurrent_simulate)
    assert callable(api.concurrent_check)


def test_concurrent_simulate_caps_workers_and_preserves_input_order():
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_request(method, path, *, body=None, query=None, headers=None):
        nonlocal active, max_active
        if method == "POST" and path == "/simulations":
            expression = str(body["regular"])
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            simulation_key = expression.replace("(", "_").replace(")", "").replace(",", "_").replace(" ", "_")
            return {"id": f"/simulations/{simulation_key}"}, {}
        if method == "GET" and str(path).startswith("/simulations/"):
            simulation_key = str(path).rsplit("/", 1)[-1]
            return {
                "status": "COMPLETE",
                "alpha": f"alpha_{simulation_key}",
                "is": {"sharpe": 1.4, "fitness": 1.1},
                "checks": [{"name": "LOW_SHARPE", "result": "PASS"}],
            }, {}
        if method == "GET" and str(path).startswith("/alphas/"):
            alpha_id = str(path).rsplit("/", 1)[-1]
            return {"id": alpha_id, "is": {"turnover": 0.2}}, {}
        raise AssertionError(f"unexpected request {method} {path}")

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = fake_request

    inputs = [
        {"expression": f"rank(close_{index})", "settings": {"region": "USA"}}
        for index in range(6)
    ]
    results = api.concurrent_simulate(inputs, concurrency=10)

    assert [row["expression"] for row in results] == [row["expression"] for row in inputs]
    assert all(row["ok"] is True for row in results)
    assert [row["index"] for row in results] == list(range(6))
    assert max_active <= 3
    assert max_active > 1


def test_concurrent_check_returns_ordered_fail_closed_results():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    def fake_request(method, path, *, body=None, query=None, headers=None):
        if method != "GET":
            raise AssertionError(f"unexpected method {method}")
        alpha_id = str(path).split("/")[-2]
        if alpha_id == "alpha_pass":
            return {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}]}, {}
        if alpha_id == "alpha_pending":
            return {"checks": [{"name": "SELF_CORRELATION", "result": "PENDING"}]}, {}
        raise BrainAPIError("network error while checking alpha", status_code=503)

    api._request = fake_request

    results = api.concurrent_check(["alpha_pass", "alpha_pending", "alpha_error"], concurrency=2)

    assert [row["alpha_id"] for row in results] == ["alpha_pass", "alpha_pending", "alpha_error"]
    assert results[0]["ok"] is True
    assert results[0]["status"] == "PASSED"
    assert results[1]["ok"] is False
    assert results[1]["status"] == "PENDING"
    assert results[1]["complete"] is False
    assert results[2]["ok"] is False
    assert results[2]["status"] == "ERROR"
    assert results[2]["complete"] is False

    exception_results = api.concurrent_check(["alpha_error"], concurrency=2, return_exceptions=True)
    assert isinstance(exception_results[0], BrainAPIError)


def test_check_prod_correlation_posts_official_body_and_parses_related_alphas():
    calls = []
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    def fake_request(method, path, *, body=None, query=None, headers=None):
        calls.append({"method": method, "path": path, "body": body})
        return {
            "maxCorrelation": -0.42,
            "relatedAlphas": [{"id": "prodAlpha123", "correlation": -0.42}],
        }, {}

    api._request = fake_request
    result = api.check_prod_correlation("rank(close)", {"region": "USA"})

    assert calls == [{
        "method": "POST",
        "path": "/alphas/correlations/check",
        "body": {"expression": "rank(close)", "settings": {"region": "USA"}},
    }]
    assert result["status"] == "ok"
    assert result["max_correlation"] == 0.42
    assert result["related_alphas"] == [{"id": "prodAlpha123", "correlation": -0.42}]
    assert result["warning"] is None


def test_check_prod_correlation_returns_warning_when_official_endpoint_unavailable():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    def fake_request(method, path, *, body=None, query=None, headers=None):
        raise BrainAPIError("HTTP 503: unavailable", status_code=503)

    api._request = fake_request
    result = api.check_prod_correlation("rank(close)")

    assert result["status"] == "error"
    assert result["max_correlation"] is None
    assert result["related_alphas"] is None
    assert "PROD_CORRELATION API check unavailable" in result["warning"]


def test_submit_alpha_uses_bodyless_post_after_explicit_check_pass():
    calls = []

    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    def fake_request(method, path, *, body=None, query=None, headers=None):
        calls.append({"method": method, "path": path, "body": body})
        if method == "GET":
            return {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}]}, {}
        if method == "POST":
            return {"status": "submitted"}, {}
        raise AssertionError(f"unexpected method {method}")

    api._request = fake_request
    result = api.submit_alpha("prodAlpha123", "rank(close)", {"region": "USA"})

    assert calls[0]["method"] == "GET"
    assert calls[1] == {
        "method": "POST",
        "path": "/alphas/prodAlpha123/submit",
        "body": None,
    }
    assert result["status"] == "SUBMITTED"
    assert result["request_body_sent"] is False


def test_submit_alpha_rejects_body_submit_shape():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )

    try:
        api.submit_alpha("prodAlpha123", "rank(close)", {"region": "USA"}, bodyless=False)
    except BrainAPIError as exc:
        assert "must be bodyless" in str(exc)
    else:
        raise AssertionError("expected non-bodyless official submit to be rejected")


def test_submit_alpha_blocks_pending_or_unknown_pre_submit_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: (
        {"checks": [{"name": "SELF_CORRELATION", "result": "PENDING"}]},
        {},
    )

    try:
        api.submit_alpha("prodAlpha123", "rank(close)", {"region": "USA"})
    except BrainAPIError as exc:
        assert "official pre-submit check failed" in str(exc)
        assert "PENDING" in str(exc)
    else:
        raise AssertionError("expected pending official check to block submit")


def test_submit_alpha_blocks_mixed_top_level_and_nested_failed_pre_submit_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    api._request = lambda method, path, **kwargs: (
        {
            "checks": [{"name": "LOW_SHARPE", "result": "PASS"}],
            "os": {"checks": [{"name": "OUT_SAMPLE_DECAY", "result": "FAIL"}]},
        },
        {},
    )

    try:
        api.submit_alpha("prodAlpha123", "rank(close)", {"region": "USA"})
    except BrainAPIError as exc:
        assert "official pre-submit check failed" in str(exc)
        assert "OUT_SAMPLE_DECAY" in str(exc)
    else:
        raise AssertionError("expected mixed failed official check to block submit")


def test_submit_alpha_blocks_failed_or_pending_submit_response_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    responses = iter([
        {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}]},
        {"is": {"checks": [{"name": "PROD_CORRELATION", "result": "FAIL"}]}},
    ])
    api._request = lambda method, path, **kwargs: (next(responses), {})

    try:
        api.submit_alpha("prodAlpha123", "rank(close)", {"region": "USA"})
    except BrainAPIError as exc:
        assert "official submit response check failed" in str(exc)
        assert "PROD_CORRELATION" in str(exc)
    else:
        raise AssertionError("expected failed submit response check to block submit")


def test_submit_alpha_records_passing_submit_response_checks():
    api = OfficialBrainAPI(
        OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0),
        token="token",
    )
    responses = iter([
        {"checks": [{"name": "LOW_SHARPE", "result": "PASS"}]},
        {"status": "submitted", "is": {"checks": [{"name": "PROD_CORRELATION", "result": "PASS"}]}},
    ])
    api._request = lambda method, path, **kwargs: (next(responses), {})

    result = api.submit_alpha("prodAlpha123", "rank(close)", {"region": "USA"})

    assert result["status"] == "SUBMITTED"
    assert result["submit_check"]["status"] == "PASSED"
    assert result["submit_check"]["complete"] is True


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
