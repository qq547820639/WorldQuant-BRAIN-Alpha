from __future__ import annotations

import json

from scripts.check_prod_defect_tracking import (
    DEFAULT_CONFIG,
    DEFAULT_REPORT,
    check_prod_defect_tracking,
)


def _readiness_payload(**overrides):
    payload = {
        "ok": True,
        "ready_to_submit": False,
        "eligible_count": 0,
        "ledger_eligible_count": 0,
        "job_family_eligible_count": 0,
    }
    payload.update(overrides)
    return payload


def test_prod_defect_tracking_accepts_current_report():
    result = check_prod_defect_tracking(readiness_validation=_readiness_payload())

    assert result["ok"] is True
    assert result["schema_version"] == "prod_defect_tracking_check.v1"
    assert result["tracked_prod_count"] == 25
    assert result["config_summary"]["min_sharpe"] == 1.25
    assert result["config_summary"]["require_official_pass"] is True
    assert result["config_summary"]["max_expression_similarity"] == 0.9
    assert result["config_summary"]["max_generation_attempts"] == 5
    assert result["readiness"]["ready_to_submit"] is False
    assert result["readiness"]["eligible_count"] == 0
    assert result["findings"] == []


def test_prod_defect_tracking_requires_prod_007_local_backtest_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(text.replace("local_backtest_failed", "local backtest blocker missing"), encoding="utf-8")

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_007_evidence" and finding["expected"] == "local_backtest_failed"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_012_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(text.replace("bad_signal_slots=0", "bad_signal_slots missing", 1), encoding="utf-8")

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_012_evidence" and finding["expected"] == "bad_signal_slots=0"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_013_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(text.replace("bad_std=[]", "bad_std missing", 1), encoding="utf-8")

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_013_evidence" and finding["expected"] == "bad_std=[]"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_014_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(text.replace("decision_band_submit_candidate", "decision_band_check_missing", 1), encoding="utf-8")

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_014_evidence" and finding["expected"] == "decision_band_submit_candidate"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_015_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(text.replace("max_generation_attempts=5", "max_generation_attempts missing", 1), encoding="utf-8")

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_015_evidence" and finding["expected"] == "max_generation_attempts=5"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_016_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(text.replace("prod_stub_alpha", "prod stub alpha missing", 1), encoding="utf-8")

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_016_evidence" and finding["expected"] == "prod_stub_alpha"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_017_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace("_reject_high_cloud_similarity_before_official", "validation preflight missing", 1),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_017_evidence"
        and finding["expected"] == "_reject_high_cloud_similarity_before_official"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_018_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace("duplicate_expression_skipped", "duplicate skip evidence missing", 1),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_018_evidence"
        and finding["expected"] == "duplicate_expression_skipped"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_019_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace("expression_similarity", "expression similarity missing"),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_019_evidence"
        and finding["expected"] == "expression_similarity"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_020_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace(
            "test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity",
            "hypothesis forbidden evidence missing",
            1,
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_020_evidence"
        and finding["expected"] == "test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_021_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace(
            "test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview",
            "readiness compact evidence missing",
            1,
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_021_evidence"
        and finding["expected"] == "test_live_submit_readiness_uses_submission_evidence_outside_compacted_preview"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_022_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace(
            "test_live_submit_readiness_reports_production_gap_summary",
            "production gap summary evidence missing",
            1,
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_022_evidence"
        and finding["expected"] == "test_live_submit_readiness_reports_production_gap_summary"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_023_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace(
            "test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage",
            "direct returns delta evidence missing",
            1,
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_023_evidence"
        and finding["expected"] == "test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_024_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace(
            "test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence",
            "candidate audit evidence coverage missing",
            1,
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_024_evidence"
        and finding["expected"] == "test_live_submit_readiness_reports_truncated_candidate_preview_with_incomplete_evidence"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_prod_025_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace(
            "test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation",
            "readiness gate invariant evidence missing",
            1,
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "prod_025_evidence"
        and finding["expected"] == "test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_rejects_stale_tracker_claimable_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602.md"
    report.write_text(
        text.replace("completion_claimable=true", "completion_claimable=false").replace(
            "completion_blockers=[]",
            "completion_blockers=[active_queue:Official context refresh, official_context_freshness]",
        ),
        encoding="utf-8",
    )

    result = check_prod_defect_tracking(report, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "validation_evidence_missing"
        and finding["expected"] == "completion_claimable=true"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "validation_evidence_missing"
        and finding["expected"] == "completion_blockers=[]"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_rejects_lowered_official_threshold(tmp_path):
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    config["ops"]["thresholds"]["require_official_pass"] = False
    config["ops"]["thresholds"]["min_sharpe"] = 0.8
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = check_prod_defect_tracking(config_path=config_path, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "threshold_mismatch" and finding["expected"] == "require_official_pass=True"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "threshold_mismatch" and finding["expected"] == "min_sharpe=1.25"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_rejects_lowered_generation_attempts(tmp_path):
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    config["ops"]["budget"]["max_generation_attempts"] = 1
    config_path = tmp_path / "run_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    result = check_prod_defect_tracking(config_path=config_path, readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "generation_config_mismatch" and finding["expected"] == "max_generation_attempts=5"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_rejects_unupdated_ready_state():
    result = check_prod_defect_tracking(
        readiness_validation=_readiness_payload(ready_to_submit=True, eligible_count=1)
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "unexpected_ready_to_submit" and finding["expected"] == "ready_to_submit=false"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "unexpected_eligible_count" and finding["expected"] == "eligible_count=0"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_requires_local_backtest_blocker_when_failed():
    result = check_prod_defect_tracking(
        readiness_validation=_readiness_payload(
            best_candidate={
                "local_backtest_passed": False,
                "blocking_reasons": ["not_submission_ready"],
            }
        )
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "missing_local_backtest_blocker"
        and finding["expected"] == "local_backtest_failed"
        for finding in result["findings"]
    )


def test_prod_defect_tracking_rejects_readiness_gate_invariant_relaxation(monkeypatch):
    def fake_readiness_ready(*args, **kwargs):
        return {
            "ok": True,
            "ready_to_submit": True,
            "eligible_count": 1,
            "ledger_eligible_count": 1,
            "job_family_eligible_count": 1,
            "best_candidate": {"blocking_reasons": []},
        }

    monkeypatch.setattr("scripts.check_prod_defect_tracking.check_live_submit_readiness", fake_readiness_ready)

    result = check_prod_defect_tracking(readiness_validation=_readiness_payload())

    assert result["ok"] is False
    assert any(
        finding["code"] == "readiness_gate_invariant_ready"
        and "blocks eligibility" in finding["expected"]
        for finding in result["findings"]
    )
