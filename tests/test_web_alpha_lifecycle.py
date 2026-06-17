from __future__ import annotations

import json

from brain_alpha_ops.web_alpha_lifecycle import alpha_lifecycle_history_payload


def test_alpha_lifecycle_history_filters_and_summarizes_local_rows():
    calls = []

    def read_storage_jsonl(name, *, limit=None):
        calls.append((name, limit))
        return [
            {
                "timestamp": "2026-06-12T01:00:00Z",
                "run_id": "run_1",
                "alpha_id": "alpha_a",
                "official_alpha_id": "",
                "simulation_id": "sim_1",
                "stage": "generated",
                "status": "READY",
                "expression": "rank(close)",
                "note": "initial candidate",
                "family": "momentum",
                "score": 81.5,
            },
            {
                "timestamp": "2026-06-12T01:05:00Z",
                "run_id": "run_1",
                "alpha_id": "alpha_a",
                "official_alpha_id": "brain_alpha_a",
                "simulation_id": "sim_1",
                "stage": "official_validation",
                "status": "PASSED",
                "expression": "rank(close)",
                "note": "official metrics complete",
                "decision_band": "submit_candidate",
            },
            {
                "timestamp": "2026-06-12T01:10:00Z",
                "run_id": "run_2",
                "alpha_id": "alpha_b",
                "simulation_id": "sim_2",
                "stage": "submission_blocked",
                "status": "BLOCKED",
                "expression": "rank(open)",
                "note": "missing official metrics",
            },
        ]

    payload = alpha_lifecycle_history_payload(
        read_storage_jsonl=read_storage_jsonl,
        alpha_id="alpha_a",
        query="official",
        limit=20,
    )

    assert calls == [("lifecycle.jsonl", None)]
    assert payload["ok"] is True
    assert payload["official_api_called"] is False
    assert payload["submit_allowed"] is False
    assert payload["source"] == "lifecycle_jsonl"
    assert payload["count"] == 1
    assert payload["records"][0]["alpha_id"] == "alpha_a"
    assert payload["records"][0]["official_alpha_id"] == "brain_alpha_a"
    assert payload["records"][0]["status_category"] == "passed"
    assert payload["records"][0]["expression_digest"].startswith("expr_")
    assert payload["summary"]["record_count"] == 1
    assert payload["summary"]["alpha_count"] == 1
    assert payload["summary"]["passed_count"] == 1
    assert payload["summary"]["replay_ready"] is True
    assert payload["alpha_traces"][0]["trace_key"] == "alpha_a"
    assert payload["alpha_traces"][0]["next_action"] == "continue_validation"


def test_alpha_lifecycle_history_redacts_sensitive_fields_and_caps_limit():
    def read_storage_jsonl(_name, *, limit=None):
        assert limit is None
        return [
            {
                "timestamp": "2026-06-12T02:00:00Z",
                "alpha_id": "alpha_secret",
                "stage": "generated",
                "status": "FAILED",
                "expression": "rank(close)",
                "note": "user secret@example.test password=hunter2 token=secret-token-1",
                "username": "secret@example.test",
                "password": "hunter2",
                "token": "secret-token-1",
            }
        ]

    payload = alpha_lifecycle_history_payload(
        read_storage_jsonl=read_storage_jsonl,
        limit=99999,
    )

    encoded = json.dumps(payload, ensure_ascii=False)
    assert payload["display_limit"] == 2000
    assert payload["summary"]["failed_count"] == 1
    assert payload["alpha_traces"][0]["failed"] is True
    assert "secret@example.test" not in encoded
    assert "hunter2" not in encoded
    assert "secret-token-1" not in encoded
    assert "username" not in encoded
    assert "password" not in encoded
    assert "token" not in encoded


def test_alpha_lifecycle_history_redacts_compound_session_labels_from_notes():
    def read_storage_jsonl(_name, *, limit=None):
        return [
            {
                "timestamp": "2026-06-12T02:05:00Z",
                "alpha_id": "alpha_session_secret",
                "stage": "generated",
                "status": "READY",
                "note": (
                    "csrf_token=csrf-secret session_id=session-secret "
                    "auth_token=auth-secret access_token=access-secret"
                ),
            }
        ]

    payload = alpha_lifecycle_history_payload(read_storage_jsonl=read_storage_jsonl)

    encoded = json.dumps(payload, ensure_ascii=False)
    for raw in (
        "csrf_token",
        "csrf-secret",
        "session_id",
        "session-secret",
        "auth_token",
        "auth-secret",
        "access_token",
        "access-secret",
    ):
        assert raw not in encoded
    assert "sensitive detail redacted" in encoded


def test_alpha_lifecycle_history_redacts_compound_session_labels_from_echoed_filters():
    payload = alpha_lifecycle_history_payload(
        read_storage_jsonl=lambda _name, limit=None: [],
        query="csrf_token=csrf-secret session_id=session-secret",
        alpha_id="auth_token=auth-secret",
        stage="access_token=access-secret",
    )

    encoded = json.dumps(payload, ensure_ascii=False)
    for raw in (
        "csrf_token",
        "csrf-secret",
        "session_id",
        "session-secret",
        "auth_token",
        "auth-secret",
        "access_token",
        "access-secret",
    ):
        assert raw not in encoded
    assert "sensitive detail redacted" in encoded


def test_alpha_lifecycle_history_filters_before_applying_display_limit():
    rows = [
        {"timestamp": "2026-06-12T02:10:00Z", "alpha_id": "alpha_old", "stage": "generated", "status": "READY"},
        {"timestamp": "2026-06-12T02:11:00Z", "alpha_id": "alpha_new_1", "stage": "generated", "status": "READY"},
        {"timestamp": "2026-06-12T02:12:00Z", "alpha_id": "alpha_new_2", "stage": "generated", "status": "READY"},
    ]

    filtered = alpha_lifecycle_history_payload(
        read_storage_jsonl=lambda _name, limit=None: rows,
        alpha_id="alpha_old",
        limit=1,
    )
    assert [row["alpha_id"] for row in filtered["records"]] == ["alpha_old"]
    assert filtered["returned_count"] == 1
    assert filtered["total_count"] == 1
    assert filtered["complete"] is True
    assert filtered["truncated"] is False

    tail = alpha_lifecycle_history_payload(
        read_storage_jsonl=lambda _name, limit=None: rows,
        limit=1,
    )
    assert [row["alpha_id"] for row in tail["records"]] == ["alpha_new_2"]
    assert tail["returned_count"] == 1
    assert tail["total_count"] == 3
    assert tail["complete"] is False
    assert tail["truncated"] is True


def test_alpha_lifecycle_history_next_action_uses_latest_event():
    rows = [
        {
            "timestamp": "2026-06-12T02:30:00Z",
            "alpha_id": "alpha_recovered",
            "stage": "submission_blocked",
            "status": "BLOCKED",
            "expression": "rank(close)",
            "note": "missing official metrics",
        },
        {
            "timestamp": "2026-06-12T02:35:00Z",
            "alpha_id": "alpha_recovered",
            "official_alpha_id": "brain_alpha_recovered",
            "stage": "official_validation",
            "status": "PASSED",
            "expression": "rank(close)",
            "note": "official metrics complete",
        },
    ]

    payload = alpha_lifecycle_history_payload(
        read_storage_jsonl=lambda _name, limit=None: rows,
    )

    trace = payload["alpha_traces"][0]
    assert trace["blocked"] is True
    assert trace["passed"] is True
    assert trace["latest_status"] == "PASSED"
    assert trace["next_action"] == "continue_validation"


def test_alpha_lifecycle_history_filters_status_category_and_stage():
    rows = [
        {"timestamp": "2026-06-12T03:00:00Z", "alpha_id": "a1", "stage": "simulation", "status": "FAILED"},
        {"timestamp": "2026-06-12T03:01:00Z", "alpha_id": "a2", "stage": "simulation", "status": "PASSED"},
        {"timestamp": "2026-06-12T03:02:00Z", "alpha_id": "a3", "stage": "submission_blocked", "status": "BLOCKED"},
    ]

    payload = alpha_lifecycle_history_payload(
        read_storage_jsonl=lambda _name, limit=None: rows,
        stage="simulation",
        status_category_filter="failed",
    )

    assert [row["alpha_id"] for row in payload["records"]] == ["a1"]
    assert payload["summary"]["by_stage"] == {"simulation": 1}
    assert payload["summary"]["by_status_category"] == {"failed": 1}
