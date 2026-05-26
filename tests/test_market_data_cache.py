from pathlib import Path

from brain_alpha_ops.research.market_data_cache import MarketDataCache


def test_market_data_cache_refresh_and_summary(tmp_path):
    cache = MarketDataCache(tmp_path)
    payload = cache.refresh_from_records(
        [
            {"symbol": "AAA", "timestamp": "2026-05-25T00:00:00Z", "close": 10.0, "volume": 100.0},
            {"symbol": "AAA", "timestamp": "2026-05-25T01:00:00Z", "close": 11.0, "volume": 120.0},
            {"symbol": "BBB", "timestamp": "2026-05-25T00:30:00Z", "close": 20.0},
        ],
        source="unit_test",
    )

    summary = cache.summary()

    assert payload["ok"] is True
    assert payload["symbol_count"] == 2
    assert summary["ok"] is True
    assert summary["symbol_count"] == 2
    assert summary["symbol_stats"][0]["symbol"] == "AAA"
    assert (Path(tmp_path) / "market_data_cache.json").is_file()


def test_market_data_cache_load_missing_file(tmp_path):
    cache = MarketDataCache(tmp_path)

    payload = cache.load()

    assert payload["ok"] is False
    assert payload["error_code"] == "CACHE_NOT_BUILT"

