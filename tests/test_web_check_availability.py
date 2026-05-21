from pathlib import Path

from brain_alpha_ops.web_check_availability import (
    check_candidate_availability,
    cloud_row_expression,
    cloud_similarity_risk,
    cloud_status_for,
)


class Ledger:
    def __init__(self, path, rows=None):
        self.path = Path(path)
        self._rows = list(rows or [])

    def records(self):
        return list(self._rows)


class Api:
    def __init__(self, status="PASSED"):
        self.status = status
        self.calls = 0

    def check_alpha(self, alpha_id):
        self.calls += 1
        return {"status": self.status}


def test_cloud_row_status_and_similarity_helpers():
    candidate = {"official_alpha_id": "off_1", "expression": "rank(close)"}
    rows = [
        {"id": "other", "expression": {"code": "rank(open)"}, "status": "UNSUBMITTED"},
        {"id": "off_1", "regular": {"code": "rank(close)"}, "status": "ACTIVE"},
    ]

    assert cloud_row_expression(rows[0]) == "rank(open)"
    assert cloud_status_for(candidate, rows)["match"] == "official_id"
    risk = cloud_similarity_risk({"expression": "rank(open)"}, rows)
    assert risk["level"] == "high"
    assert risk["matched_alpha_id"] == "other"


def test_check_candidate_availability_detects_duplicate_expression(tmp_path):
    candidate = {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "expression": "rank(ts_delta(close, 20))",
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
        "scorecard": {"total_score": 80},
    }
    ledger = Ledger(tmp_path / "ledger.jsonl", [{"official_alpha_id": "old", "expression": " rank ( ts_delta ( close , 20 ) ) "}])

    result = check_candidate_availability(
        candidate,
        "quick",
        Api(),
        ledger,
        [],
        "",
        safe_error_message=str,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
    )

    duplicate = next(item for item in result["checks"] if item["name"] == "not_submitted_before")
    assert duplicate["passed"] is False
    assert result["status"] == "BLOCKED"


def test_check_candidate_availability_frontloads_cloud_self_correlation_risk(tmp_path):
    candidate = {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "expression": "rank(open)",
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
        "scorecard": {"total_score": 80},
    }
    api = Api()
    result = check_candidate_availability(
        candidate,
        "quick",
        api,
        Ledger(tmp_path / "ledger.jsonl"),
        [{"id": "cloud_1", "expression": {"code": "rank(open)"}, "status": "UNSUBMITTED"}],
        "",
        {
            "requires_confirmation": True,
            "risk_level": "blocked",
            "blocking_flags": ["cloud_self_correlation_saturation"],
            "warning_flags": ["cloud_self_correlation_saturation"],
            "health_flags": ["cloud_self_correlation_saturation"],
            "actions": ["Diversify expression templates."],
            "flag_details": {
                "cloud_self_correlation_saturation": {
                    "evidence": {
                        "check_total": 150,
                        "blocked_count": 150,
                        "cloud_self_correlation_failed_count": 150,
                        "cloud_self_correlation_block_rate": 1.0,
                    }
                }
            },
        },
        safe_error_message=str,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
    )

    cloud_check = next(item for item in result["checks"] if item["name"] == "cloud_self_correlation")
    context_check = next(item for item in result["checks"] if item["name"] == "context_health_preflight")
    official_check = next(item for item in result["checks"] if item["name"] == "official_pre_submit_check")

    assert result["status"] == "BLOCKED"
    assert result["local_preflight_passed"] is False
    assert cloud_check["passed"] is False
    assert cloud_check["risk_explanation"]["rule"] == "cloud_self_correlation"
    assert context_check["passed"] is False
    assert official_check["detail"].startswith("Skipped")
    assert result["state_navigation"]["reason_code"] == "CLOUD_SELF_CORRELATION_BLOCKED"
    assert api.calls == 0
