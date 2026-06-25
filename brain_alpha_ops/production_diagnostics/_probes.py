"""Probe helpers that gather live evidence for the diagnostic snapshot.

Each probe returns a small dict that feeds into the contract comparison,
gap matrix, and priority attack list.  Probes are intentionally lazy: they
import heavy dependencies at call time so that importing the diagnostics
package never triggers config loading or BRAIN API initialization.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.data.loader import OfficialDataLoader
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem
from brain_alpha_ops.ux.history import RunHistoryAnalytics
from brain_alpha_ops.web_cloud.snapshot import official_context_file_counts

from ._models import logger


def _scoring_probe(run_config: RunConfig) -> dict[str, Any]:
    candidate = Candidate(
        alpha_id="diagnostic_probe",
        expression="rank(ts_delta(close, 20)) + rank(ts_mean(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Medium-horizon price momentum can be confirmed by liquidity participation and risk scaling.",
        data_fields=["close", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_mean"],
        dataset_id="fundamental6",
        local_quality={"passed": True, "score": 85},
        official_metrics={
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "prod_correlation": 0.2,
            "weight_concentration": 0.04,
            "sub_universe_sharpe": 1.3,
            "subUniverseSize": 1000,
            "alphaSize": 1000,
            "margin": 5.0,
        },
        submission={"settings": run_config.ops.settings.to_platform_dict()["settings"]},
    )
    candidate.official_alpha_id = "diagnostic_official_probe"
    result = OfficialScoringSystem(run_config.ops).evaluate(candidate)
    return {
        "alpha_id": result.alpha_id,
        "api_status": result.simulated_api_output.get("status"),
        "zero_deviation": result.api_output_deviation == 0.0,
        "api_output_deviation": result.api_output_deviation,
        "deviation_details": result.deviation_details,
        "total_score": result.total_score,
        "decision_band": result.decision_band,
        "passed_gate": result.passed_gate,
        "hard_gate_count": len(result.hard_gates[0].check_items) if result.hard_gates else 0,
        "config_hash": result.config_hash,
        "settings_trace": getattr(result, "settings_trace", {}),
        "threshold_trace": getattr(result, "threshold_trace", {}),
        "attribution_summary": result.to_dict().get("attribution_summary", {}),
    }


def _frontend_inline_status() -> dict[str, Any]:
    try:
        from brain_alpha_ops.build_inline import check

        result = check()
        css_sources = result.get("css_sources", [])
        return {
            "ok": bool(result.get("ok")),
            "replaced": result.get("replaced", 0),
            "css_replaced": result.get("css_replaced", 0),
            "missing": result.get("missing", []),
            "css_sources": [source for source in css_sources if source == "css/app.css"] or css_sources[:1],
            "css_source_files": css_sources,
            "error": result.get("error", ""),
        }
    except Exception as exc:
        from brain_alpha_ops.redaction import redact_error_message
        logger.warning("frontend inline status check failed during production diagnosis", exc_info=True)
        return {"ok": False, "replaced": 0, "missing": [], "error": redact_error_message(exc)}


def _history_replay_status(run_config: RunConfig) -> dict[str, Any]:
    analytics = RunHistoryAnalytics(run_config.ops.storage_dir).analytics(limit=10)
    return {
        "schema_version": "history_replay_status.v1",
        "capability": "ready",
        "analytics_schema_version": analytics.get("schema_version", ""),
        "history_count": int(analytics.get("history_count") or 0),
        "latest_comparison_available": bool(analytics.get("latest_comparison")),
        "trend_status": (analytics.get("trend") or {}).get("status", "empty"),
        "latest_run_id": (analytics.get("latest") or {}).get("run_id", ""),
    }


def _official_refresh_status(run_config: RunConfig) -> dict[str, Any]:
    counts = official_context_file_counts(load_config=lambda: run_config)
    manifest = counts.get("context_cache_manifest") if isinstance(counts.get("context_cache_manifest"), dict) else {}
    status_path = Path(run_config.ops.storage_dir) / "official_context_refresh_status.json"
    attempt = _read_refresh_attempt_status(status_path)
    metadata_files = manifest.get("files") or {}
    sources = sorted(
        {
            str(meta.get("source") or "")
            for meta in metadata_files.values()
            if isinstance(meta, dict) and str(meta.get("source") or "")
        }
    )
    status = "verified" if attempt.get("ok") is True else "not_verified"
    if attempt.get("ok") is False:
        status = "failed"
    elif manifest.get("complete") and "official_api" in sources:
        status = "metadata_verified"
    return {
        "schema_version": "official_refresh_status.v1",
        "status": status,
        "source": ",".join(sources) or "metadata_missing",
        "file_count": int(manifest.get("file_count") or len(metadata_files) or 0),
        "missing_files": list(manifest.get("missing_files") or []),
        "stale_files": list(manifest.get("stale_files") or []),
        "stale_count": len(manifest.get("stale_files") or []),
        "record_counts": dict(manifest.get("record_counts") or {}),
        "complete": bool(manifest.get("complete")),
        "last_attempt_status": str(attempt.get("status") or "not_recorded"),
        "last_attempt_ok": attempt.get("ok"),
        "last_attempt_error": str(attempt.get("error") or ""),
        "last_attempt_generated_at": str(attempt.get("generated_at") or ""),
        "status_path": str(status_path),
    }


def _official_context_counts(loader: OfficialDataLoader, official_refresh: dict[str, Any]) -> dict[str, int]:
    record_counts = official_refresh.get("record_counts") or {}
    return {
        "fields": int(record_counts.get("official_fields.json") or loader.field_count),
        "operators": int(record_counts.get("official_operators.json") or loader.operator_count),
        "datasets": int(record_counts.get("official_datasets.json") or loader.dataset_count),
    }


def _read_refresh_attempt_status(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
