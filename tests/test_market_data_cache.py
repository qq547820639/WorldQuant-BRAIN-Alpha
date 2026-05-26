from pathlib import Path
import json

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
    assert payload["field_stats"][0]["field"] in {"close", "volume"}
    assert payload["cache_health"]["ready"] is True


def test_market_data_cache_load_missing_file(tmp_path):
    cache = MarketDataCache(tmp_path)

    payload = cache.load()

    assert payload["ok"] is False
    assert payload["error_code"] == "CACHE_NOT_BUILT"


def test_market_data_cache_refresh_from_json_path_and_nested_metrics(tmp_path):
    source = tmp_path / "market.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {"symbol": "AAA", "timestamp": "2026-05-25T00:00:00Z", "metrics": {"close": 10.0, "volume": 100.0}},
                    {"symbol": "BBB", "timestamp": "2026-05-25T00:00:00Z", "official_metrics": {"close": 20.0}},
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = MarketDataCache(tmp_path).refresh_from_path(source)

    assert payload["ok"] is True
    assert payload["symbol_count"] == 2
    assert payload["source_files"][0]["record_count"] == 2
    assert payload["field_stats"][0]["coverage_ratio"] >= 0.5
    assert payload["time_range"]["start"] == "2026-05-25T00:00:00Z"
