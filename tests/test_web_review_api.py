import json

from brain_alpha_ops.web_review_api import anti_overfit_snapshot, assistant_cross_review_payload, rolling_validation_snapshot


def test_anti_overfit_snapshot_finds_candidate_in_latest_result():
    candidate = {
        "alpha_id": "a1",
        "expression": "rank(ts_delta(close, 20))",
        "official_metrics": {"ic_series": [0.03, 0.035, 0.04, 0.025] * 20},
        "submission": {},
    }

    payload = anti_overfit_snapshot(
        candidate_id="a1",
        latest_result_snapshot=lambda: {"ok": True, "result": {"summary": {"candidates": [candidate]}}},
    )

    assert payload["ok"] is True
    assert payload["candidate_id"] == "a1"
    assert payload["anti_overfit_report"]["schema_version"] == "anti_overfit_report.v1"


def test_anti_overfit_snapshot_reports_missing_candidate():
    payload = anti_overfit_snapshot(
        candidate_id="missing",
        latest_result_snapshot=lambda: {
            "ok": True,
            "result": {"summary": {"candidates": [{"alpha_id": "a1", "expression": "rank(close)"}]}},
        },
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "CANDIDATE_NOT_FOUND"
    assert payload["available_candidate_ids"] == ["a1"]


def test_rolling_validation_snapshot_finds_candidate_in_latest_result():
    candidate = {
        "alpha_id": "a1",
        "expression": "rank(ts_delta(close, 20))",
        "official_metrics": {"rolling_fitness": [1.0, 1.1, 1.0, 0.9, 0.85, 0.8, 0.75, 0.7]},
        "submission": {},
    }

    payload = rolling_validation_snapshot(
        candidate_id="a1",
        windows=4,
        latest_result_snapshot=lambda: {"ok": True, "result": {"summary": {"candidates": [candidate]}}},
    )

    assert payload["ok"] is True
    assert payload["candidate_id"] == "a1"
    assert payload["rolling_validation_report"]["schema_version"] == "rolling_validation_report.v1"


def test_rolling_validation_snapshot_reports_missing_candidate():
    payload = rolling_validation_snapshot(
        candidate_id="missing",
        latest_result_snapshot=lambda: {
            "ok": True,
            "result": {"summary": {"candidates": [{"alpha_id": "a1", "expression": "rank(close)"}]}},
        },
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "CANDIDATE_NOT_FOUND"
    assert payload["available_candidate_ids"] == ["a1"]


def test_assistant_cross_review_payload_normalizes_request():
    response = json.dumps(
        {
            "summary": "ok",
            "recommended_next_actions": ["refresh cloud cache"],
            "risk_flags": ["cloud_sync_required"],
            "candidate_adjustments": [],
            "follow_up_questions": [],
            "confidence": 0.9,
        }
    )

    payload = assistant_cross_review_payload(
        {
            "request_pack": {"prompt_digest": "pd_1"},
            "primary_response": response,
            "reviewer_response": response,
            "min_confidence": "0.7",
        },
        bounded_query_float=lambda value, low, high: max(low, min(high, float(value))),
    )

    assert payload["ok"] is True
    assert payload["decision"] == "accept"
    assert payload["min_confidence"] == 0.7
