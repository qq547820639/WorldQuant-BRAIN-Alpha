from brain_alpha_ops.research.alerting import AlertDeliveryService
from brain_alpha_ops.research.market_data_cache import MarketDataCache
from brain_alpha_ops.research.observability import build_research_observability_snapshot, diagnose_research_health, observability_context


def test_observability_includes_cache_and_alerts(tmp_path):
    MarketDataCache(tmp_path).refresh_from_records([{"symbol": "AAA", "timestamp": "2026-05-25T00:00:00Z", "close": 10.0}])
    AlertDeliveryService(storage_dir=tmp_path).alert("cache stale", "refresh required")

    snapshot = build_research_observability_snapshot(tmp_path, limit=10, top_n=3, include_cloud=False)
    context = observability_context(snapshot, top_n=3)
    health = diagnose_research_health(
        snapshot,
        market_data_cache=snapshot.get("market_data_cache"),
        alerts=snapshot.get("alerts"),
    )

    assert snapshot["market_data_cache"]["ok"] is True
    assert snapshot["market_data_vector"]["ok"] is True
    assert snapshot["alerts"]["count"] == 1
    assert context["market_data_cache_ready"] is True
    assert context["market_data_vector_ready"] is True
    assert context["alert_count"] == 1
    assert health["evidence"]["market_data_cache_ready"] is True
    assert health["evidence"]["alert_count"] == 1
