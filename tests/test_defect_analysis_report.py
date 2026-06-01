from __future__ import annotations

import sys

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


def test_defect_analysis_report_rejects_stale_tracking_facts(tmp_path):
    text = DEFAULT_REPORT.read_text(encoding="utf-8") + "\nPARTIAL_CLOSED_CURRENT\n"
    report = _write_report(tmp_path, text)

    result = check_defect_analysis_report(report)

    assert result["ok"] is False
    assert any(finding["code"] == "stale_report_fact" for finding in result["findings"])
