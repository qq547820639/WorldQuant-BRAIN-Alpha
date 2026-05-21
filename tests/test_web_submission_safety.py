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
        "gate": {"submission_ready": True},
        "lifecycle_status": "submission_ready",
    }


def test_submission_preflight_advisory_reports_cloud_stale(tmp_path):
    run_config = RunConfig(environment="mock")
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


def test_submission_preflight_advisory_reports_duplicate_expression(tmp_path):
    run_config = RunConfig(environment="mock")
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


def test_submission_preflight_advisory_blocks_cloud_self_correlation_check(tmp_path):
    run_config = RunConfig(environment="mock")
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
