from __future__ import annotations

from brain_alpha_ops import web


def test_submit_readiness_payload_compacts_local_gate_result(monkeypatch):
    monkeypatch.setattr(
        web,
        "_run_live_submit_readiness_check",
        lambda: {
            "ok": True,
            "ready_to_submit": False,
            "ledger_ready_to_submit": False,
            "job_family_ready_to_submit": False,
            "candidate_count": 2,
            "ledger_candidate_count": 3,
            "job_family_candidate_count": 5,
            "eligible_count": 0,
            "ledger_eligible_count": 0,
            "job_family_eligible_count": 0,
            "latest_job_id": "job_1",
            "latest_job_status": "stopped",
            "summary_counts": {
                "official_validation_passed": 1,
                "officially_simulated": 0,
                "submission_ready": 0,
                "submitted_this_run": 0,
            },
            "latest_blocking_reason_counts": {
                "missing_official_alpha_id": 2,
                "missing_official_metrics": 2,
                "local_backtest_failed": 1,
            },
            "job_family_blocking_reason_counts": {
                "missing_official_alpha_id": 5,
                "missing_cloud_similarity": 3,
            },
            "findings": [
                {"code": "no_submit_ready_candidate", "message": "no candidate is ready"},
                {"code": "candidate_family_missing_official_metrics", "message": "missing metrics"},
            ],
            "production_gap_summary": {
                "gaps": [
                    {"code": "official_validation_without_simulation", "message": "missing official simulation"}
                ]
            },
            "best_candidate": {
                "alpha_id": "alpha_1",
                "official_alpha_id": "",
                "lifecycle_status": "generated",
                "score": 71.2,
                "decision_band": "optimize_before_submit",
                "local_backtest_passed": False,
                "max_similarity": 0.91,
                "risk_level": "high",
                "blocking_reasons": [
                    "missing_official_alpha_id",
                    "missing_official_metrics",
                    "local_backtest_failed",
                ],
            },
            "job_audits": [{"large": "omitted"}],
        },
    )

    payload = web._submit_readiness_payload()

    assert payload["ok"] is True
    assert payload["source"] == "check_live_submit_readiness.py"
    assert payload["official_api_called"] is False
    assert payload["ready_to_submit"] is False
    assert payload["candidate_count"] == 2
    assert payload["job_family_candidate_count"] == 5
    assert payload["eligible_count"] == 0
    assert payload["summary_counts"]["officially_simulated"] == 0
    assert payload["best_candidate"]["alpha_id"] == "alpha_1"
    assert payload["top_blocking_reasons"][0] == {"reason": "missing_official_alpha_id", "count": 2}
    assert payload["top_family_blocking_reasons"][0] == {"reason": "missing_official_alpha_id", "count": 5}
    assert payload["production_gaps"][0] == {
        "code": "official_validation_without_simulation",
        "message": "missing official simulation",
    }
    assert "run official simulation/check in a trusted environment" in payload["required_next_steps"]
    assert "job_audits" not in payload


def test_submit_readiness_dispatch_route_uses_compact_payload(monkeypatch):
    monkeypatch.setattr(
        web,
        "_run_live_submit_readiness_check",
        lambda: {
            "ok": True,
            "ready_to_submit": True,
            "eligible_count": 1,
            "summary_counts": {"officially_simulated": 1, "submission_ready": 1},
        },
    )

    class Handler:
        payload = None

        def _send_json(self, payload, status=200):
            self.payload = payload
            self.status = status

    handler = Handler()
    web.dispatch_get(handler, "/api/submit_readiness", {})

    assert handler.status == 200
    assert handler.payload["ready_to_submit"] is True
    assert handler.payload["eligible_count"] == 1
