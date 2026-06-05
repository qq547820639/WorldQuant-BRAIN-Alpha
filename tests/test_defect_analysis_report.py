from __future__ import annotations

import sys
from pathlib import Path

from scripts.check_defect_analysis_report import DEFAULT_REPORT, check_defect_analysis_report


def _write_report(tmp_path, text: str):
    report = tmp_path / "DEFECT_ANALYSIS_REPORT_20260601.md"
    report.write_text(text, encoding="utf-8")
    return report


def test_defect_analysis_report_accepts_current_document():
    result = check_defect_analysis_report()

    assert result["ok"] is True
    assert result["schema_version"] == "defect_analysis_report_check.v1"
    assert result["detailed_count"] == 16
    assert result["status_count"] == 16
    assert result["closed_count"] == 16
    assert result["open_count"] == 0
    assert result["python_runtime"] == ".".join(str(part) for part in sys.version_info[:3])
    assert result["python_runtime_ok"] is True
    assert result["open_items"] == []
    assert result["findings"] == []


def test_defect_analysis_report_accepts_static_20260603_document():
    report = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")

    result = check_defect_analysis_report(report)

    assert result["ok"] is True
    assert result["detailed_count"] == 22
    assert result["status_count"] == 22
    assert result["closed_count"] == 21
    assert result["open_count"] == 1
    assert result["priority_counts"]["overview"] == {"P0": 4, "P1": 7, "P2": 6, "P3": 5}
    assert result["priority_counts"]["detail"] == {"P0": 4, "P1": 7, "P2": 6, "P3": 5}
    assert result["priority_counts"]["status"] == {"P0": 4, "P1": 7, "P2": 6, "P3": 5}
    assert [item["id"] for item in result["open_items"]] == ["P0-3"]
    assert result["open_items"][0]["status"] == "TRACKED_DEFERRED"
    assert result["findings"] == []


def test_defect_analysis_report_rejects_missing_status_row(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| DEFECT-003:"))
    report = _write_report(tmp_path, text.replace(f"{row}\n", "", 1))

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "missing_status_row" and finding["expected"] == "DEFECT-003"
        for finding in result["findings"]
    )


def test_defect_analysis_report_rejects_missing_static_status_row(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| P2-6 |"))
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(text.replace(f"{row}\n", "", 1), encoding="utf-8")

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "missing_status_row" and finding["expected"] == "P2-6"
        for finding in result["findings"]
    )


def test_defect_analysis_report_rejects_static_priority_distribution_drift(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(text.replace("P1×7", "P1×8", 1), encoding="utf-8")

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "priority_count_mismatch" and finding["expected"] == "detail:P1=8"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "priority_count_mismatch" and finding["expected"] == "status:P1=8"
        for finding in result["findings"]
    )


def test_defect_analysis_report_rejects_extra_static_open_item(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(text.replace("| P1-5 | FIXED |", "| P1-5 | TRACKED_OPEN |", 1), encoding="utf-8")

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "open_items_mismatch"
        and finding["expected"] == "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md:P0-3"
        for finding in result["findings"]
    )


def test_defect_analysis_report_allows_resolved_static_compat_boundary_without_next_action(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| P2-5 |"))
    cells = row.strip().strip("|").split("|")
    cells[-1] = " "
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(text.replace(row, "|" + "|".join(cells) + "|", 1), encoding="utf-8")

    result = check_defect_analysis_report(report)

    assert result["ok"] is True
    assert not any(
        finding["code"] == "missing_next_action" and finding["expected"] == "P2-5"
        for finding in result["findings"]
    )


def test_defect_analysis_report_rejects_closed_static_pagination_boundary(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(text.replace("| P0-3 | TRACKED_DEFERRED |", "| P0-3 | FIXED |", 1), encoding="utf-8")

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_status_mismatch" and finding["expected"] == "P0-3:TRACKED_DEFERRED"
        for finding in result["findings"]
    )


def test_defect_analysis_report_requires_static_pagination_callsite_cancel_evidence(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(
        text.replace(
            "tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan",
            "tests/test_web_sync_job.py::missing_cancel_evidence",
            1,
        ),
        encoding="utf-8",
    )

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_report_text_mismatch"
        and finding["expected"] == (
            "P0-3:"
            "tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan"
        )
        for finding in result["findings"]
    )


def test_defect_analysis_report_requires_static_pagination_stall_observability(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(text.replace("stalled_unique_pages", "missing_stall_observability"), encoding="utf-8")

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_report_text_mismatch"
        and finding["expected"] == "P0-3:stalled_unique_pages"
        for finding in result["findings"]
    )


def test_defect_analysis_report_requires_static_bind_smoke_command_record(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(
        text.replace(
            "python -m brain_alpha_ops.web --smoke-test --port 0",
            "python -m brain_alpha_ops.web --smoke-test",
        ),
        encoding="utf-8",
    )
    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_report_text_mismatch"
        and finding["expected"] == "P2-6:python -m brain_alpha_ops.web --smoke-test --port 0"
        for finding in result["findings"]
    )


def test_defect_analysis_report_requires_static_bind_smoke_success_evidence(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| P2-6 |"))
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(
        text.replace(
            row,
            row.replace('{"ok": true, "status": "web ready"', "web ready"),
            1,
        ),
        encoding="utf-8",
    )

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_evidence_mismatch"
        and finding["expected"] == 'P2-6:{"ok": true, "status": "web ready"'
        for finding in result["findings"]
    )


def test_defect_analysis_report_requires_static_bind_smoke_sandbox_error(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(
        text.replace("PermissionError: [Errno 1] Operation not permitted", "sandbox bind failed"),
        encoding="utf-8",
    )

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_report_text_mismatch"
        and finding["expected"] == "P2-6:PermissionError: [Errno 1] Operation not permitted"
        for finding in result["findings"]
    )


def test_defect_analysis_report_requires_static_bind_smoke_expected_output(tmp_path):
    source = Path("docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md")
    text = source.read_text(encoding="utf-8")
    report = tmp_path / "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md"
    report.write_text(
        text.replace('{"ok": true, "status": "web ready"', '{"ok": true, "status": "not ready"'),
        encoding="utf-8",
    )

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(
        finding["code"] == "boundary_report_text_mismatch"
        and finding["expected"] == 'P2-6:{"ok": true, "status": "web ready"'
        for finding in result["findings"]
    )


def test_defect_analysis_report_rejects_stale_tracking_facts(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8") + "\nPARTIAL_CLOSED_CURRENT\n"
    report = _write_report(tmp_path, text)

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(finding["code"] == "stale_report_fact" for finding in result["findings"])
