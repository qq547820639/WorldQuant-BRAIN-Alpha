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
    def __init__(self, status="PASSED", fail_check=False):
        self.status = status
        self.fail_check = fail_check
        self.calls = 0

    def check_alpha(self, alpha_id):
        self.calls += 1
        if self.fail_check:
            raise RuntimeError("official failed")
        return {"status": self.status}


def complete_official_metrics():
    return {
        "pass_fail": "PASS",
        "sharpe": 1.5,
        "fitness": 1.1,
        "turnover": 0.2,
        "self_correlation": 0.1,
        "prod_correlation": 0.2,
        "weight_concentration": 0.03,
    }


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


def test_check_candidate_availability_logs_official_check_failure(tmp_path, caplog):
    candidate = {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "official_metrics": complete_official_metrics(),
        "expression": "rank(close)",
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
        "scorecard": {"total_score": 91, "decision_band": "submit_candidate"},
    }
    api = Api(fail_check=True)

    with caplog.at_level("WARNING"):
        result = check_candidate_availability(
            candidate,
            "quick",
            api,
            Ledger(tmp_path / "ledger.jsonl"),
            [],
            "",
            safe_error_message=str,
            observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
        )

    official_check = next(item for item in result["checks"] if item["name"] == "official_pre_submit_check")

    assert result["status"] == "CHECK_PASSED_NEEDS_OFFICIAL"
    assert result["local_preflight_passed"] is True
    assert official_check["passed"] is False
    assert official_check["detail"] == "official failed"
    assert api.calls == 1
    assert any("official pre-submit check failed" in record.getMessage() for record in caplog.records)


def test_check_candidate_availability_blocks_non_submit_candidate_band(tmp_path):
    candidate = {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "official_metrics": complete_official_metrics(),
        "expression": "rank(close)",
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
        "scorecard": {"total_score": 78, "decision_band": "optimize_before_submit"},
    }
    api = Api()

    result = check_candidate_availability(
        candidate,
        "quick",
        api,
        Ledger(tmp_path / "ledger.jsonl"),
        [],
        "",
        safe_error_message=str,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
    )

    band_check = next(item for item in result["checks"] if item["name"] == "decision_band_submit_candidate")
    official_check = next(item for item in result["checks"] if item["name"] == "official_pre_submit_check")

    assert result["status"] == "BLOCKED"
    assert result["submittable"] is False
    assert result["local_preflight_passed"] is False
    assert band_check["passed"] is False
    assert band_check["detail"] == "optimize_before_submit"
    assert official_check["detail"].startswith("Skipped")
    assert api.calls == 0


def test_check_candidate_availability_blocks_sparse_official_metrics_before_official_call(tmp_path):
    candidate = {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "official_metrics": {"pass_fail": "PASS"},
        "expression": "rank(close)",
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
        "scorecard": {"total_score": 91, "decision_band": "submit_candidate"},
    }
    api = Api()

    result = check_candidate_availability(
        candidate,
        "quick",
        api,
        Ledger(tmp_path / "ledger.jsonl"),
        [],
        "",
        safe_error_message=str,
        observability_submission_preflight=lambda storage_dir: {"requires_confirmation": False},
    )

    metric_fields_check = next(item for item in result["checks"] if item["name"] == "official_metric_fields_complete")
    official_check = next(item for item in result["checks"] if item["name"] == "official_pre_submit_check")

    assert result["status"] == "BLOCKED"
    assert result["local_preflight_passed"] is False
    assert metric_fields_check["passed"] is False
    assert "sharpe" in metric_fields_check["missing_fields"]
    assert official_check["detail"].startswith("Skipped")
    assert api.calls == 0
