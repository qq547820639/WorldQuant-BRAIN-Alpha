from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.web_submission_safety import (
    observability_submission_preflight,
    submission_preflight_advisory,
)


class Ledger:
    def __init__(self, _storage_dir, rows=None):
        self.rows = list(rows or [])

    def records(self):
        return list(self.rows)


def _candidate():
    return {
        "alpha_id": "a1",
        "official_alpha_id": "off_1",
        "expression": "rank(close)",
        "official_metrics": {
            "pass_fail": "PASS",
            "sharpe": 1.5,
            "fitness": 1.1,
            "turnover": 0.2,
            "self_correlation": 0.1,
            "prod_correlation": 0.2,
            "weight_concentration": 0.03,
            "sub_universe_sharpe": 1.2,
            "subUniverseSize": 1000,
            "alphaSize": 1000,
        },
        "scorecard": {"total_score": 91.0, "decision_band": "submit_candidate"},
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
    }


def test_submission_preflight_advisory_reports_cloud_stale(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = True

    payload = submission_preflight_advisory(
        _candidate(),
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [{"id": "other"}], "summary": {"is_stale": True}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SUBMIT_CLOUD_SYNC_STALE"


def test_submission_preflight_advisory_requires_cloud_cache_even_when_per_run_sync_disabled(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False

    payload = submission_preflight_advisory(
        _candidate(),
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {"is_stale": False}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SUBMIT_CLOUD_SYNC_REQUIRED"


def test_submission_preflight_advisory_reports_duplicate_expression(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False

    payload = submission_preflight_advisory(
        _candidate(),
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir, [{"official_alpha_id": "old", "expression": "rank(close)"}]),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SUBMIT_DUPLICATE_EXPRESSION"


def test_submission_preflight_advisory_requires_official_metrics_pass(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False
    missing_metrics = _candidate()
    missing_metrics.pop("official_metrics")
    failed_metrics = _candidate()
    failed_metrics["official_metrics"] = {"pass_fail": "FAIL"}

    missing_payload = submission_preflight_advisory(
        missing_metrics,
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )
    failed_payload = submission_preflight_advisory(
        failed_metrics,
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert missing_payload["ok"] is False
    assert missing_payload["error_code"] == "MISSING_OFFICIAL_METRICS"
    assert failed_payload["ok"] is False
    assert failed_payload["error_code"] == "OFFICIAL_ALPHA_CHECK_NOT_PASS"


def test_submission_preflight_advisory_requires_complete_official_metric_fields(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False
    sparse_metrics = _candidate()
    sparse_metrics["official_metrics"] = {"pass_fail": "PASS"}

    payload = submission_preflight_advisory(
        sparse_metrics,
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "MISSING_OFFICIAL_METRIC_FIELDS"
    assert payload["missing_fields"] == [
        "sharpe",
        "fitness",
        "turnover",
        "self_correlation",
        "prod_correlation",
        "weight_concentration",
        "sub_universe_sharpe/subUniverseSharpe",
    ]


def test_submission_preflight_advisory_blocks_official_release_gate_failure(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False
    candidate = _candidate()
    candidate["official_metrics"] = {
        **candidate["official_metrics"],
        "sharpe": 1.6,
        "sub_universe_sharpe": 0.6,
        "subUniverseSize": 1000,
        "alphaSize": 1000,
    }

    payload = submission_preflight_advisory(
        candidate,
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "OFFICIAL_RELEASE_GATE_FAILED"
    assert payload["release_gate"]["status"] == "FAIL"
    assert "sub_universe_sharpe" in payload["reasons"]


def test_submission_preflight_advisory_requires_submit_candidate_decision_band(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False
    candidate = _candidate()
    candidate["scorecard"] = {"total_score": 78.0, "decision_band": "optimize_before_submit"}

    payload = submission_preflight_advisory(
        candidate,
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SUBMIT_DECISION_BAND_NOT_READY"


def test_submission_preflight_advisory_blocks_stub_official_alpha_id(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False
    candidate = _candidate()
    candidate["official_alpha_id"] = "prod_stub_alpha_0001"
    candidate["official_metrics"]["official_alpha_id"] = "prod_stub_alpha_0001"

    payload = submission_preflight_advisory(
        candidate,
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "NON_PRODUCTION_ALPHA_ID"
    assert any("official_alpha_id" in reason for reason in payload["reasons"])


def test_submission_preflight_advisory_blocks_cloud_self_correlation_check(tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    run_config.ops.budget.require_cloud_sync = False
    (tmp_path / "checks.jsonl").write_text(
        '{"alpha_id":"a1","official_alpha_id":"off_1","status":"BLOCKED","passed":false,'
        '"cloud_correlation_risk":{"level":"high","max_similarity":0.96,"matched_alpha_id":"cloud_1","matched_status":"UNSUBMITTED"},'
        '"checks":[{"name":"cloud_self_correlation","passed":false,"detail":"high 0.9600"}]}\n',
        encoding="utf-8",
    )

    payload = submission_preflight_advisory(
        _candidate(),
        run_config,
        ledger_factory=lambda storage_dir: Ledger(storage_dir),
        cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
        cloud_status_for=lambda candidate, rows: {"status": ""},
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SUBMIT_CLOUD_SELF_CORRELATION_BLOCKED"
    assert payload["risk_explanation"]["rule"] == "cloud_self_correlation"
    assert payload["state_navigation"]["reason_code"] == "CLOUD_SELF_CORRELATION_BLOCKED"


def test_observability_submission_preflight_maps_health_and_errors():
    advisory = observability_submission_preflight(
        "data",
        observability_builder=lambda *args, **kwargs: {
            "schema_version": "research_observability.v1",
            "generated_at": "now",
            "health": {
                "risk_level": "blocked",
                "health_flags": ["rate_limit_pressure"],
                "blocking_flags": ["rate_limit_pressure"],
                "warning_flags": [],
                "actions": ["Pause."],
            },
            "official_call_guard": {"state": "blocked"},
        },
    )
    failed = observability_submission_preflight(
        "data",
        observability_builder=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom SECRET")),
        safe_error_message=lambda exc: "boom [redacted]",
    )

    assert advisory["requires_confirmation"] is True
    assert advisory["official_call_guard"]["state"] == "blocked"
    assert failed["ok"] is False
    assert failed["requires_confirmation"] is True
    assert "SECRET" not in failed["error"]
