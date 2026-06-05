from __future__ import annotations

import json

from brain_alpha_ops import web
from brain_alpha_ops.config import RunConfig


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_backtest_slots_payload_includes_local_readonly_queue_summary(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.min_prior_score_for_official_simulation = 70.0
    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    _write_jsonl(
        tmp_path / "backtests.jsonl",
        [
            {
                "slot": 1,
                "alpha_id": "alpha_running",
                "simulation_id": "sim_1",
                "status": "RUNNING",
                "timestamp": "2026-06-04T01:00:00+00:00",
            }
        ],
    )
    _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "alpha_id": "alpha_ready",
                "scorecard": {"total_score": 75.0},
                "local_quality": {"passed": True},
                "quality_diagnosis": {
                    "local_candidate_valid": True,
                    "blocking_reasons": [
                        "decision_band_not_submit_candidate",
                        "missing_official_alpha_id",
                        "missing_official_metrics",
                    ],
                    "reasons": [
                        {
                            "code": "decision_band_not_submit_candidate",
                            "category": "quality_gate_failed",
                            "severity": "blocking",
                        },
                        {
                            "code": "missing_official_alpha_id",
                            "category": "official_evidence_missing",
                            "severity": "blocking",
                        },
                        {
                            "code": "missing_official_metrics",
                            "category": "official_evidence_missing",
                            "severity": "blocking",
                        },
                    ],
                },
            },
            {
                "alpha_id": "alpha_low_score",
                "scorecard": {"total_score": 65.0},
                "local_quality": {"passed": True},
                "quality_diagnosis": {"local_candidate_valid": True, "blocking_reasons": []},
            },
            {
                "alpha_id": "alpha_failed_local",
                "scorecard": {"total_score": 80.0},
                "local_quality": {
                    "passed": False,
                    "local_backtest": {"pass_local": False},
                },
                "quality_diagnosis": {
                    "local_candidate_valid": False,
                    "blocking_reasons": ["local_quality_failed"],
                },
            },
            {
                "alpha_id": "alpha_high_turnover",
                "expression": "rank(ts_delta(returns, 10))",
                "scorecard": {"total_score": 90.0},
                "local_quality": {"passed": True},
                "quality_diagnosis": {"local_candidate_valid": True, "blocking_reasons": []},
            },
        ],
    )

    payload = web._backtest_slots_payload()
    summary = payload["queue_summary"]

    assert payload["active_count"] == 1
    assert summary["official_api_called"] is False
    assert summary["official_slot_record_count"] == 1
    assert summary["open_slot_count"] == 2
    assert summary["candidate_count"] == 4
    assert summary["local_valid_count"] == 3
    assert summary["above_simulation_score_count"] == 3
    assert summary["review_candidate_count"] == 1
    assert summary["blocked_candidate_count"] == 3
    assert summary["submit_evidence_blocking_count"] == 1
    assert summary["next_action"] == "trusted_environment_official_simulation_required"
    reasons = {row["reason"]: row["count"] for row in summary["top_blocking_reasons"]}
    assert reasons["score_below_official_simulation_threshold"] == 1
    assert reasons["local_backtest_failed"] == 1
    assert reasons["local_quality_failed"] == 1
    assert reasons["high_turnover_generation_risk"] == 1
    assert "missing_official_alpha_id" not in reasons
    assert "missing_official_metrics" not in reasons
    submit_reasons = {row["reason"]: row["count"] for row in summary["top_submit_blocking_reasons"]}
    assert submit_reasons["decision_band_not_submit_candidate"] == 1
    assert submit_reasons["missing_official_alpha_id"] == 1
    assert submit_reasons["missing_official_metrics"] == 1
