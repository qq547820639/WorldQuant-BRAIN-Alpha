from __future__ import annotations

from brain_alpha_ops.tasks import DEFAULT_RECOVERY_ERROR
from brain_alpha_ops.web_state_contract import enrich_error_payload, enrich_job_response


def _assert_actionable(payload: dict, kind: str) -> None:
    assert payload["user_error_kind"] == kind
    user_error = payload["user_error"]
    assert user_error["kind"] == kind
    assert user_error["title"]
    assert user_error["message"]
    assert user_error["impact"]
    assert user_error["suggested_action"]
    assert user_error["action_label"]
    assert isinstance(user_error["recoverable"], bool)
    assert isinstance(user_error["retryable"], bool)


def test_enrich_error_payload_maps_af018_error_experience_cases():
    cases = [
        ({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}, "session_expired"),
        ({"ok": False, "error_code": "CACHE_UNAVAILABLE", "error": "local cache unavailable"}, "cache_unavailable"),
        ({"ok": False, "error_code": "RATE_LIMITED", "error": "HTTP 429: rate limit"}, "official_rate_limited"),
        (
            {"ok": False, "error_code": "SIMULATION_ERROR", "error": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
            "official_concurrency_limit",
        ),
        ({"ok": False, "error_code": "DATASET_NOT_FOUND", "error": "dataset pv1 missing"}, "dataset_missing"),
        ({"ok": False, "error_code": "EXPRESSION_UNKNOWN_OPERATOR", "error": "unknown operator"}, "invalid_expression"),
        ({"ok": False, "error_code": "NETWORK_TIMEOUT", "error": "request timeout"}, "network_timeout"),
        ({"ok": False, "error_code": "JOB_CANCELLED", "error": "task cancelled"}, "task_cancelled"),
        ({"ok": False, "error_code": "CONFLICT_RUNNING", "error": "active async job"}, "queue_blocked"),
        ({"ok": False, "error_code": "JOB_NOT_FOUND", "error": "unknown job"}, "job_not_found"),
    ]

    for raw, kind in cases:
        payload = enrich_error_payload(raw)
        _assert_actionable(payload, kind)


def test_enrich_error_payload_redacts_sensitive_text_and_keeps_legacy_error_string():
    payload = enrich_error_payload({
        "ok": False,
        "error_code": "AUTH_FAILED",
        "error": "auth failed for reader@example.com with token=secret-token-123",
    })

    assert "reader@example.com" not in payload["error"]
    assert "secret-token-123" not in payload["error"]
    assert payload["user_error_kind"] == "session_expired"
    assert payload["user_message"] == payload["user_error"]["message"]


def test_enrich_job_response_classifies_active_terminal_and_interrupted_statuses():
    active = enrich_job_response({"ok": True, "job_id": "job_1", "status": "running", "progress": {"phase": "scan"}}, job_type="sync")
    assert active["status_kind"] == "active"
    assert active["terminal"] is False
    assert active["recoverable"] is True
    assert active["job_type"] == "sync"

    warning = enrich_job_response({"ok": True, "job_id": "job_2", "status": "completed_with_warnings"})
    assert warning["status_kind"] == "warning"
    assert warning["terminal"] is True
    assert warning["recoverable"] is True
    assert warning["user_error_kind"] == "completed_with_warnings"

    stopped = enrich_job_response({"ok": True, "job_id": "job_3", "status": "stopped"})
    assert stopped["status_kind"] == "interrupted"
    assert stopped["terminal"] is True
    assert stopped["interrupted"] is True
    assert stopped["next_action"] == "restart_flow"

    recovered = enrich_job_response({
        "ok": True,
        "job_id": "job_4",
        "status": "failed",
        "error": DEFAULT_RECOVERY_ERROR,
        "progress": {"phase": "failed"},
    })
    assert recovered["status_kind"] == "interrupted"
    assert recovered["interrupted"] is True
    assert recovered["user_error_kind"] == "task_interrupted"

    missing = enrich_job_response({"ok": False, "job_id": "job_5", "status": "missing", "error_code": "JOB_NOT_FOUND", "error": "unknown job"})
    assert missing["status_kind"] == "missing"
    assert missing["terminal"] is True
    assert missing["recoverable"] is True
    assert missing["user_error_kind"] == "job_not_found"


def test_enrich_job_response_keeps_specific_actionable_failed_job_errors():
    rate_limited = enrich_job_response({
        "ok": True,
        "job_id": "job_rate",
        "status": "failed",
        "error": "HTTP 429: rate limit",
    })
    assert rate_limited["status_kind"] == "failed"
    assert rate_limited["terminal"] is True
    assert rate_limited["user_error_kind"] == "official_rate_limited"
    assert rate_limited["next_action"] == "wait_and_retry"

    concurrency_limited = enrich_job_response({
        "ok": True,
        "job_id": "job_slots",
        "status": "failed",
        "error": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
    })
    assert concurrency_limited["status_kind"] == "failed"
    assert concurrency_limited["terminal"] is True
    assert concurrency_limited["user_error_kind"] == "official_concurrency_limit"
    assert concurrency_limited["next_action"] == "review_official_slots"
