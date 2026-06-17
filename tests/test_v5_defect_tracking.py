from __future__ import annotations

from scripts.check_v5_defect_tracking import (
    DEFAULT_REPORT,
    check_v5_defect_tracking,
)


def test_v5_defect_tracking_accepts_current_document():
    result = check_v5_defect_tracking()

    assert result["ok"] is True
    assert result["schema_version"] == "v5_defect_tracking_check.v1"
    assert result["p1_tracked_count"] == 9
    assert result["metrics"]["实际待修复"]["v6"] == "1"
    assert result["status_rows"]["V5-013"]["v6_status"] == "FIXED"
    assert "OfficialBrainAPI" in result["status_rows"]["V5-013"]["evidence"]
    assert "React mirror-only" in result["status_rows"]["V5-025~V5-031"]["evidence"]
    assert result["required_validation_count"] >= 27
    assert "V5-002" in result["closed_ids"]
    assert "V5-006" in result["closed_ids"]
    assert "V5-007" in result["closed_ids"]
    assert result["findings"] == []


def test_v5_defect_tracking_rejects_missing_p1_row(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| V5-007 |"))
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(text.replace(f"{row}\n", "", 1), encoding="utf-8")

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "missing_p1_tracking_row" and finding["expected"] == "V5-007"
        for finding in result["findings"]
    )


def test_v5_defect_tracking_requires_implemented_closures(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(text.replace("| V5-006 | CLOSED_CURRENT |", "| V5-006 | NEEDS_AUDIT |", 1), encoding="utf-8")

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "required_closure_missing" and finding["expected"] == "V5-006"
        for finding in result["findings"]
    )


def test_v5_defect_tracking_rejects_stale_remaining_metric(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(text.replace("| 实际待修复 | 27 | 1 |", "| 实际待修复 | 27 | 2 |", 1), encoding="utf-8")

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "metric_mismatch" and finding["expected"] == "实际待修复=1"
        for finding in result["findings"]
    )


def test_v5_defect_tracking_rejects_stale_v5_013_status(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(
        text.replace(
            "| **V5-013** | open | **FIXED** |",
            "| **V5-013** | open | **PARTIAL** |",
            1,
        ),
        encoding="utf-8",
    )

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "status_mismatch" and finding["expected"] == "V5-013:FIXED"
        for finding in result["findings"]
    )


def test_v5_defect_tracking_rejects_stale_v5_025_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(text.replace("React mirror-only", "React pending decision", 1), encoding="utf-8")

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] in {"status_evidence_mismatch", "detail_fact_missing"}
        and "React mirror-only" in finding["expected"]
        for finding in result["findings"]
    )


def test_v5_defect_tracking_requires_p2_validation_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(
        text.replace(
            "tests/test_official_scoring_system.py::test_official_scoring_in_memory_history_is_bounded",
            "tests/test_official_scoring_system.py::missing_history_bound_test",
            1,
        ),
        encoding="utf-8",
    )

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "validation_evidence_missing"
        and finding["expected"] == (
            "V6-NEW-003:"
            "tests/test_official_scoring_system.py::test_official_scoring_in_memory_history_is_bounded"
        )
        for finding in result["findings"]
    )


def test_v5_defect_tracking_requires_v5_001_validation_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(
        text.replace(
            "tests/test_official_adapter.py::test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping",
            "tests/test_official_adapter.py::missing_no_new_unique_items_warning_test",
            1,
        ),
        encoding="utf-8",
    )

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "validation_evidence_missing"
        and finding["expected"] == (
            "V5-001:"
            "tests/test_official_adapter.py::test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping"
        )
        for finding in result["findings"]
    )


def test_v5_defect_tracking_requires_v5_001_stall_observability_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(text.replace("duplicate_unique_items", "missing_duplicate_count"), encoding="utf-8")

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "validation_evidence_missing"
        and finding["expected"] == "V5-001:duplicate_unique_items"
        for finding in result["findings"]
    )


def test_v5_defect_tracking_requires_v5_001_callsite_cancel_evidence(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
    report.write_text(
        text.replace(
            "tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows",
            "tests/test_pipeline.py::missing_callsite_cancel_test",
            1,
        ),
        encoding="utf-8",
    )

    result = check_v5_defect_tracking(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "validation_evidence_missing"
        and finding["expected"] == (
            "V5-001:"
            "tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows"
        )
        for finding in result["findings"]
    )
