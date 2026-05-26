"""Optional observability helpers for market-data cache and alerting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.research.alerting import AlertDeliveryService
from brain_alpha_ops.research.market_data_cache import MarketDataCache
from brain_alpha_ops.research.market_data_vector import build_vectorized_market_data


def load_optional_observability_sources(root: str | Path, *, top_n: int) -> tuple[dict[str, Any], dict[str, Any]]:
    root_path = Path(root)
    safe_top_n = max(1, int(top_n or 1))
    return MarketDataCache(root_path).summary(), AlertDeliveryService(storage_dir=root_path).recent(limit=safe_top_n)


def optional_observability_context(snapshot: dict[str, Any] | None, *, top_n: int = 10) -> dict[str, Any]:
    snapshot = snapshot or {}
    market_cache = snapshot.get("market_data_cache") if isinstance(snapshot.get("market_data_cache"), dict) else {}
    alerts = snapshot.get("alerts") if isinstance(snapshot.get("alerts"), dict) else {}
    return {
        "market_data_cache_ready": bool(market_cache.get("ok")),
        "market_data_cache_symbols": market_cache.get("symbol_count", 0),
        "market_data_vector_ready": bool(snapshot.get("market_data_vector", {}).get("ok")) if isinstance(snapshot.get("market_data_vector"), dict) else False,
        "alert_count": alerts.get("count", 0),
    }


def optional_vector_snapshot(root: str | Path, *, top_n: int) -> dict[str, Any]:
    payload = build_vectorized_market_data(root, limit_symbols=max(1, int(top_n or 1)))
    if not payload.get("ok"):
        return payload
    return {
        "ok": True,
        "schema_version": payload.get("schema_version", "market_data_vector.v1"),
        "source": payload.get("source", ""),
        "symbol_count": payload.get("symbol_count", 0),
        "field_count": payload.get("field_count", 0),
        "row_count": payload.get("row_count", 0),
        "column_stats": list(payload.get("column_stats") or [])[:top_n],
    }


def optional_research_health_payload(
    market_cache_payload: dict[str, Any] | None,
    alert_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    market_cache_payload = market_cache_payload if isinstance(market_cache_payload, dict) else {}
    alert_payload = alert_payload if isinstance(alert_payload, dict) else {}
    market_ready = bool(market_cache_payload.get("ok"))
    symbol_count = _int_from_any(market_cache_payload.get("symbol_count"))
    alert_count = _int_from_any(alert_payload.get("count"))

    health_flags: list[str] = []
    details: dict[str, dict[str, Any]] = {}
    actions: list[str] = []

    if not market_ready:
        health_flags.append("market_data_cache_missing_optional")
        details["market_data_cache_missing_optional"] = {
            "severity": "info",
            "message": "The lightweight market-data cache has not been built.",
            "action": "Refresh the market-data cache before large parameter-search or batch-screening runs.",
            "evidence": {"error_code": market_cache_payload.get("error_code", "")},
        }
        actions.append("Refresh the market-data cache before large parameter-search or batch-screening runs.")

    if alert_count > 0:
        health_flags.append("operator_alerts_recorded")
        details["operator_alerts_recorded"] = {
            "severity": "info",
            "message": "Recent operator alerts are present in the local alert log.",
            "action": "Review recent alerts before launching another official-call batch.",
            "evidence": {"alert_count": alert_count},
        }
        actions.append("Review recent alerts before launching another official-call batch.")

    return {
        "health_flags": health_flags,
        "details": details,
        "actions": actions,
        "evidence": {
            "market_data_cache_ready": market_ready,
            "market_data_cache_symbol_count": symbol_count,
            "alert_count": alert_count,
        },
    }


def _int_from_any(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
