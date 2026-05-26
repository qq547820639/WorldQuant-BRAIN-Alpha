from brain_alpha_ops.research.market_data_cache import MarketDataCache
from brain_alpha_ops.research.market_data_vector import VectorizedMarketDataStore


def test_vectorized_market_data_builds_symbol_feature_matrix(tmp_path):
    MarketDataCache(tmp_path).refresh_from_records(
        [
            {"symbol": "AAA", "timestamp": "2026-05-25T00:00:00Z", "close": 10.0, "volume": 100.0},
            {"symbol": "AAA", "timestamp": "2026-05-25T01:00:00Z", "close": 12.0, "volume": 120.0},
            {"symbol": "BBB", "timestamp": "2026-05-25T00:00:00Z", "close": 20.0, "volume": 200.0},
        ],
        source="unit_test",
    )

    payload = VectorizedMarketDataStore(tmp_path).build_view(fields=["close", "volume"], limit_symbols=10)

    assert payload["ok"] is True
    assert payload["schema_version"] == "market_data_vector.v1"
    assert payload["symbols"] == ["AAA", "BBB"]
    assert payload["matrix"][0] == [11.0, 110.0]
    assert payload["column_stats"][0]["field"] == "close"


def test_vectorized_market_data_reports_missing_cache(tmp_path):
    payload = VectorizedMarketDataStore(tmp_path).build_view(fields=["close"])

    assert payload["ok"] is False
    assert payload["error_code"] == "CACHE_NOT_BUILT"
