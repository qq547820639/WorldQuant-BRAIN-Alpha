from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from brain_alpha_ops.data import ashare_adapter as ashare
from brain_alpha_ops.data.ashare_adapter import (
    AKShareAdapter,
    AShareDataProvider,
    BaoStockAdapter,
    CacheStore,
    _baostock_code,
    _safe_float,
)


class _BaoResult:
    def __init__(self, rows, *, error_code="0", error_msg=""):
        self.rows = list(rows)
        self.error_code = error_code
        self.error_msg = error_msg
        self.index = -1

    def next(self):
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self):
        return self.rows[self.index]


class _Frame:
    def __init__(self, rows=None, *, empty=False):
        self.rows = rows or []
        self.empty = empty

    def iterrows(self):
        return iter(enumerate(self.rows))


def test_cache_store_json_fallback_roundtrip_and_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(ashare, "_PARQUET_AVAILABLE", False)
    cache = CacheStore(tmp_path)

    assert cache.get("missing") is None
    cache.put("daily_000001", [{"date": "2024-01-01", "close": 10}])
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")

    assert cache.get("daily_000001") == [{"date": "2024-01-01", "close": 10}]
    assert cache.get("broken") is None
    assert cache.list_keys() == ["broken", "daily_000001"]
    assert cache.clear() == 2
    assert cache.list_keys() == []


def test_helpers_normalize_symbols_and_numbers():
    assert _baostock_code("600000") == "sh.600000"
    assert _baostock_code("000001") == "sz.000001"
    assert _baostock_code("830000") == "bj.830000"
    assert _baostock_code("123") == "sz.000123"
    assert _safe_float(" 1.25 ") == 1.25
    assert _safe_float("", default=9.0) == 0.0
    assert _safe_float(None, default=9.0) == 9.0


def test_baostock_adapter_fetch_daily_success_fallback_and_stock_list(monkeypatch):
    calls = []

    def query_history(_code, fields, **_kwargs):
        calls.append(fields)
        if "adjfactor" in fields:
            return _BaoResult([], error_code="1", error_msg="unsupported field")
        return _BaoResult([
            ["2024-01-01", "10", "11", "9", "10.5", "1000", "10500", "0.5"],
        ])

    fake_bs = SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0", error_msg=""),
        logout=lambda: calls.append("logout"),
        query_history_k_data_plus=query_history,
        query_stock_basic=lambda: _BaoResult([
            ["000001", "Ping An", "1991-04-03", "1", "1"],
        ]),
    )
    monkeypatch.setitem(sys.modules, "baostock", fake_bs)
    monkeypatch.setattr(ashare, "_BAOSTOCK_AVAILABLE", False)

    adapter = BaoStockAdapter()
    rows = adapter.fetch_daily("000001", start_date="2024-01-01", end_date="2024-01-02")

    assert adapter.available is True
    assert calls[0].endswith("adjfactor")
    assert calls[1] == "date,open,high,low,close,volume,amount,turn"
    assert rows == [{
        "date": "2024-01-01",
        "symbol": "000001",
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.5,
        "volume": 1000.0,
        "amount": 10500.0,
        "turnover_rate": 0.5,
        "adj_factor": 1.0,
    }]
    assert adapter.fetch_stock_list()[0]["name"] == "Ping An"
    adapter.logout()
    assert calls[-1] == "logout"


def test_baostock_adapter_reports_unavailable_and_query_errors(monkeypatch):
    monkeypatch.delitem(sys.modules, "baostock", raising=False)
    monkeypatch.setattr(ashare, "_BAOSTOCK_AVAILABLE", False)
    assert BaoStockAdapter().available is False
    with pytest.raises(ImportError):
        BaoStockAdapter().fetch_daily("000001")

    fake_bs = SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0", error_msg=""),
        query_history_k_data_plus=lambda *_args, **_kwargs: _BaoResult([], error_code="2", error_msg="bad"),
    )
    monkeypatch.setitem(sys.modules, "baostock", fake_bs)
    monkeypatch.setattr(ashare, "_BAOSTOCK_AVAILABLE", False)
    assert BaoStockAdapter().fetch_daily("000001") == []

    bad_login = SimpleNamespace(login=lambda: SimpleNamespace(error_code="1", error_msg="denied"))
    monkeypatch.setitem(sys.modules, "baostock", bad_login)
    monkeypatch.setattr(ashare, "_BAOSTOCK_AVAILABLE", False)
    with pytest.raises(RuntimeError):
        BaoStockAdapter().fetch_stock_list()


def test_akshare_adapter_constituents_and_industry_mapping(monkeypatch):
    fake_ak = SimpleNamespace(
        index_stock_cons_weight_csindex=lambda _code: _Frame([
            {"成分券代码": "000001"},
            {"constituent_code": "600000"},
        ]),
        stock_board_industry_name_em=lambda: _Frame([
            {"代码": "000001", "名称": "Bank"},
            {"代码": "600000", "名称": "Finance"},
        ]),
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    monkeypatch.setattr(ashare, "_AKSHARE_AVAILABLE", False)

    adapter = AKShareAdapter()
    constituents = adapter.fetch_index_constituents("000300")
    assert constituents.index_name == "沪深300"
    assert constituents.constituents == ["000001", "600000"]
    assert adapter.fetch_industry_classification() == {"000001": "Bank", "600000": "Finance"}
    assert adapter.fetch_index_constituents("999999").constituents == []


def test_akshare_adapter_handles_missing_package_empty_frames_and_exceptions(monkeypatch):
    monkeypatch.delitem(sys.modules, "akshare", raising=False)
    monkeypatch.setattr(ashare, "_AKSHARE_AVAILABLE", False)
    adapter = AKShareAdapter()
    assert adapter.available is False
    with pytest.raises(ImportError):
        adapter.fetch_industry_classification()

    fake_ak = SimpleNamespace(
        index_stock_cons_weight_csindex=lambda _code: _Frame(empty=True),
        stock_board_industry_name_em=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)
    monkeypatch.setattr(ashare, "_AKSHARE_AVAILABLE", False)
    adapter = AKShareAdapter()
    assert adapter.fetch_index_constituents("000300").constituents == []
    assert adapter.fetch_industry_classification() == {}


def test_provider_loads_batch_from_cache_fetches_and_converts_to_backtest_format(tmp_path, monkeypatch):
    monkeypatch.setattr(ashare, "_PARQUET_AVAILABLE", False)
    provider = AShareDataProvider(cache_dir=tmp_path)
    provider._baostock = SimpleNamespace(
        available=True,
        fetch_daily=lambda symbol, **_kwargs: [{"date": "2024-01-01", "symbol": symbol, "close": "10", "volume": 100}],
        logout=lambda: None,
    )

    fetched = provider.load_daily_batch(["000001"], start="2024-01-01", end="2024-01-02")
    cached = provider.load_daily_batch(["000001"], start="2024-01-01", end="2024-01-02")
    converted = provider.to_backtest_format(cached, fields=["close", "volume"])

    assert fetched == cached
    assert converted["close"] == [[10.0]]
    assert converted["volume"] == [[100.0]]
    stats = provider.cache_stats()
    assert stats["keys"] == 1
    assert stats["parquet_available"] is False
    assert provider.clear_cache() == 1


def test_provider_handles_fetch_failures_and_index_universe_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(ashare, "_PARQUET_AVAILABLE", False)
    provider = AShareDataProvider(cache_dir=tmp_path)
    provider._baostock = SimpleNamespace(
        available=True,
        fetch_daily=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("network")),
        fetch_stock_list=lambda: [{"symbol": "000001"}, {"symbol": "000002"}],
        logout=lambda: None,
    )
    provider._akshare = SimpleNamespace(
        available=False,
        fetch_index_constituents=lambda _index: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert provider.available is True
    assert provider.load_daily_batch(["000001"], start="2024-01-01", end="2024-01-02") == {"000001": []}

    provider._baostock.fetch_daily = lambda symbol, **_kwargs: [{"date": "2024-01-01", "symbol": symbol, "close": 1}]
    fallback = provider.load_index_universe("000300", start="2024-01-01", end="2024-01-02", force_refresh=True)
    assert sorted(fallback) == ["000001", "000002"]

    provider._akshare = SimpleNamespace(
        available=True,
        fetch_index_constituents=lambda _index: SimpleNamespace(constituents=["600000"]),
    )
    akshare_result = provider.load_index_universe("000300", start="2024-01-01", end="2024-01-02", force_refresh=True)
    assert list(akshare_result) == ["600000"]

    cached_flat = [{"date": "2024-01-01", "symbol": "600000", "close": 2}]
    provider.cache.put("index_universe_000300_2024-01-01_2024-01-02", cached_flat)
    rebuilt = provider.load_index_universe("000300", start="2024-01-01", end="2024-01-02")
    assert rebuilt == {"600000": cached_flat}
