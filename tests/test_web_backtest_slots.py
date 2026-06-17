from __future__ import annotations

import json

from brain_alpha_ops import web
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_backtest_slots import candidate_local_backtest_failed


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_candidate_local_backtest_failed_ignores_advisory_generation_evidence():
    candidate = {
        "local_quality": {"local_backtest": {"pass_local": False, "advisory": True}},
        "submission": {"local_backtest": {"pass_local": False, "advisory": True}},
    }

    assert candidate_local_backtest_failed(candidate) is False
    assert candidate_local_backtest_failed({"submission": {"local_backtest": {"pass_local": False}}}) is True


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


def test_backtest_slots_treats_capacity_wait_as_active_local_slot(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    _write_jsonl(
        tmp_path / "backtests.jsonl",
        [
            {
                "action": "capacity_wait",
                "slot": 1,
                "alpha_id": "alpha_waiting",
                "status": "CAPACITY_WAIT",
                "next_poll_seconds": 5.0,
                "poll_elapsed_seconds": 15.0,
                "message": "官方并发槽位已满，5 秒后重试；已等待 15.0 秒。",
                "timestamp": "2026-06-04T01:00:00+00:00",
            }
        ],
    )
    _write_jsonl(tmp_path / "candidates.jsonl", [])

    payload = web._backtest_slots_payload()
    summary = payload["queue_summary"]

    assert payload["active_count"] == 1
    assert summary["active_slot_count"] == 1
    assert summary["open_slot_count"] == 2
    assert summary["official_slot_record_count"] == 0
    assert payload["slots"][0]["status"] == "CAPACITY_WAIT"
    assert payload["slots"][0]["next_poll_seconds"] == 5.0
    assert payload["slots"][0]["status_board"]["submitted_count"] == 0


def test_backtest_slots_queue_summary_reads_all_existing_candidates(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.min_prior_score_for_official_simulation = 70.0
    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    _write_jsonl(tmp_path / "backtests.jsonl", [])
    rows = [
        {
            "alpha_id": "alpha_ready_outside_tail",
            "scorecard": {"total_score": 75.0},
            "local_quality": {"passed": True},
            "quality_diagnosis": {"local_candidate_valid": True, "blocking_reasons": []},
        }
    ]
    rows.extend(
        {
            "alpha_id": f"alpha_low_{idx}",
            "scorecard": {"total_score": 10.0},
            "local_quality": {"passed": False},
            "quality_diagnosis": {"local_candidate_valid": False, "blocking_reasons": ["local_quality_failed"]},
        }
        for idx in range(1000)
    )
    _write_jsonl(tmp_path / "candidates.jsonl", rows)

    payload = web._backtest_slots_payload()
    summary = payload["queue_summary"]

    assert summary["candidate_count"] == 1001
    assert summary["returned_candidate_count"] == 1001
    assert summary["review_candidate_count"] == 1
    assert summary["next_action"] == "trusted_environment_official_simulation_required"


def test_backtest_slots_queue_summary_keeps_all_blocking_reasons(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.min_prior_score_for_official_simulation = 70.0
    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    _write_jsonl(tmp_path / "backtests.jsonl", [])
    rows = [
        {
            "alpha_id": f"alpha_blocked_{index}",
            "scorecard": {"total_score": 80.0 + index},
            "local_quality": {"passed": True},
            "quality_diagnosis": {
                "local_candidate_valid": True,
                "blocking_reasons": [f"custom_review_reason_{index}", f"custom_submit_reason_{index}"],
                "reasons": [
                    {
                        "code": f"custom_review_reason_{index}",
                        "category": "local_quality_failed",
                        "severity": "blocking",
                    },
                    {
                        "code": f"custom_submit_reason_{index}",
                        "category": "quality_gate_failed",
                        "severity": "blocking",
                    }
                ],
            },
        }
        for index in range(8)
    ]
    _write_jsonl(tmp_path / "candidates.jsonl", rows)

    payload = web._backtest_slots_payload()
    summary = payload["queue_summary"]

    assert len(summary["top_blocking_reasons"]) >= 8
    assert len(summary["top_submit_blocking_reasons"]) == 8
    review_reasons = {row["reason"] for row in summary["top_blocking_reasons"]}
    assert review_reasons == {f"custom_review_reason_{index}" for index in range(8)}
    submit_reasons = {row["reason"] for row in summary["top_submit_blocking_reasons"]}
    assert submit_reasons == {f"custom_submit_reason_{index}" for index in range(8)}


def test_backtest_slots_payload_derives_per_slot_status_board(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    _write_jsonl(
        tmp_path / "backtests.jsonl",
        [
            {
                "action": "submitted",
                "slot": 1,
                "alpha_id": "alpha_a",
                "simulation_id": "sim_a",
                "status": "SUBMITTED",
                "timestamp": "2026-06-04T01:00:00+00:00",
            },
            {
                "action": "completed",
                "slot": 1,
                "alpha_id": "alpha_a",
                "simulation_id": "sim_a",
                "official_alpha_id": "official_a",
                "status": "COMPLETED",
                "official_metrics": {"pass_fail": "PASS"},
                "timestamp": "2026-06-04T01:01:00+00:00",
            },
            {
                "action": "submitted",
                "slot": 1,
                "alpha_id": "alpha_b",
                "simulation_id": "sim_b",
                "status": "SUBMITTED",
                "timestamp": "2026-06-04T01:02:00+00:00",
            },
            {
                "action": "failed",
                "slot": 1,
                "alpha_id": "alpha_b",
                "simulation_id": "sim_b",
                "status": "FAILED",
                "timestamp": "2026-06-04T01:03:00+00:00",
            },
            {
                "action": "completed",
                "slot": 2,
                "alpha_id": "alpha_c",
                "simulation_id": "sim_c",
                "status": "COMPLETED",
                "official_metrics": {"pass_fail": "FAIL"},
                "timestamp": "2026-06-04T01:04:00+00:00",
            },
        ],
    )

    payload = web._backtest_slots_payload()
    slot_one = payload["slots"][0]
    slot_two = payload["slots"][1]

    assert slot_one["status"] == "FAILED"
    assert slot_one["status_board"] == {
        "task_index": 1,
        "alpha_id": "alpha_b",
        "submitted_count": 2,
        "completed_count": 1,
        "failed_count": 1,
        "passed_count": 1,
        "not_passed_count": 1,
        "pass_rate": 0.5,
    }
    assert slot_two["status_board"]["submitted_count"] == 1
    assert slot_two["status_board"]["completed_count"] == 1
    assert slot_two["status_board"]["failed_count"] == 0
    assert slot_two["status_board"]["passed_count"] == 0
    assert slot_two["status_board"]["not_passed_count"] == 1
    assert slot_two["status_board"]["pass_rate"] == 0.0


def test_backtest_slots_status_board_reads_all_existing_backtest_events(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr(web, "load_run_config", lambda: run_config)
    filler_rows = [
        {
            "action": "polling",
            "slot": 3,
            "alpha_id": f"alpha_filler_{index}",
            "simulation_id": f"sim_filler_{index}",
            "status": "RUNNING",
            "timestamp": f"2026-06-04T02:{index % 60:02d}:00+00:00",
        }
        for index in range(1001)
    ]
    _write_jsonl(
        tmp_path / "backtests.jsonl",
        [
            {
                "action": "completed",
                "slot": 1,
                "alpha_id": "alpha_early",
                "simulation_id": "sim_early",
                "status": "COMPLETED",
                "official_metrics": {"pass_fail": "PASS"},
                "timestamp": "2026-06-04T01:00:00+00:00",
            },
            *filler_rows,
        ],
    )

    payload = web._backtest_slots_payload()
    slot_one = payload["slots"][0]

    assert payload["record_count"] == 1002
    assert slot_one["status"] == "COMPLETED"
    assert slot_one["status_board"]["submitted_count"] == 1
    assert slot_one["status_board"]["completed_count"] == 1
    assert slot_one["status_board"]["passed_count"] == 1
    assert slot_one["status_board"]["pass_rate"] == 1.0
