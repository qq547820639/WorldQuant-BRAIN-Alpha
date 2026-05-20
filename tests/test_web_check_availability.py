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

    def check_alpha(self, alpha_id):
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
