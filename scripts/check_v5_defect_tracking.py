"""Validate the v5 defect implementation tracking table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
SCHEMA_VERSION = "v5_defect_tracking_check.v1"
VALID_STATUSES = {"CLOSED_CURRENT", "NEEDS_AUDIT", "TRACKED_DEFERRED", "TRACKED_OPEN"}
REQUIRED_P1_IDS = tuple(f"V5-{index:03d}" for index in range(1, 10))
REQUIRED_CLOSED_IDS = {"V5-002", "V5-006", "V5-007"}
REQUIRED_METRICS = {"实际待修复": "1"}
REQUIRED_STATUS_SUBSTRINGS = {
    "V5-001": {"v6_status": "TRACKED_DEFERRED", "evidence": "stalled_unique_pages"},
    "V5-012": {"v6_status": "FIXED", "evidence": "缓存"},
    "V5-013": {"v6_status": "FIXED", "evidence": "OfficialBrainAPI"},
    "V5-014": {"v6_status": "FIXED", "evidence": "pagination_limits.py"},
    "V5-015": {"v6_status": "FIXED", "evidence": "sys.modules"},
    "V5-016": {"v6_status": "FIXED", "evidence": "_credentials"},
    "V5-017": {"v6_status": "FIXED", "evidence": "prepare_run_config_for_runtime"},
    "V5-018": {"v6_status": "FIXED", "evidence": "fail closed"},
    "V5-019": {"v6_status": "FIXED", "evidence": "printf"},
    "V5-020": {"v6_status": "FIXED", "evidence": "125 → 1.25"},
    "V5-021": {"v6_status": "FIXED", "evidence": "requireAsyncJobResult"},
    "V5-022": {"v6_status": "FIXED", "evidence": "runStartup"},
    "V5-023": {"v6_status": "FIXED", "evidence": "AppState"},
    "V5-024": {"v6_status": "FIXED", "evidence": "_cached_paginated_context"},
    "V5-025~V5-031": {"v6_status": "FIXED", "evidence": "React mirror-only"},
}
REQUIRED_DETAIL_SNIPPETS = {
    "V5-013": ("OfficialBrainAPI.__mro__", "组合委托"),
    "V5-025": ("React mirror-only", "production_surface=inline_html_js", "react_surface=mirror"),
}
REQUIRED_VALIDATION_SNIPPETS = {
    "V5-001": (
        "tests/test_official_adapter.py::test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping",
        "duplicate_unique_items",
        "stalled_unique_pages",
        "tests/test_official_adapter.py::test_list_user_alphas_can_be_cancelled_by_progress_callback_without_page_cap",
        "tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan",
        "tests/test_web_sync_job.py::test_run_sync_job_service_stops_alpha_scan_on_elapsed_limit",
        "tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows",
        "tests/test_pipeline.py::test_pipeline_cloud_sync_elapsed_limit_does_not_merge_partial_rows",
    ),
    "V5-012": (
        "tests/test_dynamic_research_components.py::test_template_registry_field_type_matching_is_dataset_specific",
    ),
    "V5-013": (
        "tests/test_official_adapter.py::test_official_api_uses_composed_api_components",
    ),
    "V5-014/V5-015": (
        "tests/test_official_adapter.py::test_list_fields_stops_at_max_pages_limit",
        "tests/test_official_adapter.py::test_list_user_alphas_has_no_default_page_limit",
    ),
    "V5-016": (
        "tests/test_official_adapter.py::test_official_api_keeps_credentials_out_of_plain_instance_fields",
    ),
    "V5-017/V5-018": (
        "tests/test_config.py::test_validate_run_config_resolves_dataset_without_mutating_input",
        "tests/test_config.py::test_validate_run_config_rejects_empty_default_dataset_resolution",
    ),
    "V5-019": (
        "tests/test_infrastructure_modules.py::TestSecureCredentials::test_redaction_filter_tuple_args_redacts_only_sensitive_positions",
        "tests/test_infrastructure_modules.py::TestSecureCredentials::test_redaction_filter_tuple_args_redacts_nested_values",
    ),
    "V5-020": (
        "tests/test_comprehensive_scoring_edge_cases.py::TestExtremeValues::test_ratio_normalizes_values_above_100_as_percentages",
    ),
    "V5-021": (
        "tests/test_web_frontend_v2.py::test_app_submit_selected_candidates_handles_missing_async_job_result",
    ),
    "V5-022": (
        "tests/test_web_frontend_v2.py::test_loading_feedback_runstartup_launches_all_tasks_concurrently",
    ),
    "V5-023": (
        "tests/test_web_frontend_v2.py::test_app_apply_preset_reads_presets_from_app_state",
        "tests/test_web_frontend_v2.py::test_spinner_component",
    ),
    "V5-024": (
        "tests/test_official_adapter.py::test_context_collection_methods_share_paginated_context_helper",
    ),
    "V5-026/V5-027": (
        "tests/test_dynamic_research_components.py::test_template_registry_seed_does_not_mutate_global_random_state",
        "tests/test_dynamic_research_components.py::test_template_registry_unknown_and_empty_field_cases",
    ),
    "V5-030": (
        "tests/test_web_frontend_v2.py::test_spinner_component",
    ),
    "V5-031": (
        "tests/test_web_progress.py::test_progress_payload_documents_unified_fields",
    ),
    "V6-NEW-003": (
        "tests/test_official_scoring_system.py::test_official_scoring_in_memory_history_is_bounded",
    ),
    "V6-NEW-004": (
        "tests/test_scoring_gate.py::test_build_scorecard_does_not_mutate_candidate_scorecard",
    ),
}


def check_v5_defect_tracking(report_path: str | Path = DEFAULT_REPORT) -> dict[str, Any]:
    path = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(path),
            "findings": [_finding("missing_report", str(path), "v5 defect report does not exist")],
        }

    rows = _tracking_rows(text, findings)
    rows_by_id = {row["id"]: row for row in rows}
    metrics = _metric_rows(text, findings)
    status_rows = _status_rows(text, findings)
    for defect_id in REQUIRED_P1_IDS:
        if defect_id not in rows_by_id:
            findings.append(_finding("missing_p1_tracking_row", defect_id, "P1 defect is missing from current tracking table"))
            continue
        row = rows_by_id[defect_id]
        if row["status"] not in VALID_STATUSES:
            findings.append(_finding("invalid_status", f"{defect_id}:{row['status']}", "unknown tracking status"))
        if not row["evidence"]:
            findings.append(_finding("missing_evidence", defect_id, "tracking row needs current evidence"))
        if row["status"] != "CLOSED_CURRENT" and not row["next_action"]:
            findings.append(_finding("missing_next_action", defect_id, "open/deferred/audit rows need a next action"))

    for defect_id in REQUIRED_CLOSED_IDS:
        row = rows_by_id.get(defect_id)
        if row and row["status"] != "CLOSED_CURRENT":
            findings.append(_finding("required_closure_missing", defect_id, "implemented v5 fix must be tracked as CLOSED_CURRENT"))

    for metric, expected in REQUIRED_METRICS.items():
        actual = metrics.get(metric, {}).get("v6", "")
        if actual != expected:
            findings.append(_finding("metric_mismatch", f"{metric}={expected}", "defect report summary metric is stale"))

    for defect_id, expectations in REQUIRED_STATUS_SUBSTRINGS.items():
        row = status_rows.get(defect_id)
        if row is None:
            findings.append(_finding("missing_status_row", defect_id, "expected defect status row is missing"))
            continue
        expected_status = expectations["v6_status"]
        if expected_status not in row["v6_status"]:
            findings.append(_finding("status_mismatch", f"{defect_id}:{expected_status}", "defect status row is stale"))
        expected_evidence = expectations["evidence"]
        if expected_evidence not in row["evidence"]:
            findings.append(_finding("status_evidence_mismatch", f"{defect_id}:{expected_evidence}", "defect status evidence is stale"))

    for defect_id, snippets in REQUIRED_DETAIL_SNIPPETS.items():
        detail = _detail_section(text, defect_id)
        if not detail:
            findings.append(_finding("missing_detail_section", defect_id, "expected defect detail section is missing"))
            continue
        for snippet in snippets:
            if snippet not in detail:
                findings.append(_finding("detail_fact_missing", f"{defect_id}:{snippet}", "defect detail section is missing current evidence"))

    for defect_id, snippets in REQUIRED_VALIDATION_SNIPPETS.items():
        for snippet in snippets:
            if snippet not in text:
                findings.append(_finding("validation_evidence_missing", f"{defect_id}:{snippet}", "defect lacks explicit verification evidence"))

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(path),
        "tracked_count": len(rows),
        "p1_tracked_count": sum(1 for defect_id in REQUIRED_P1_IDS if defect_id in rows_by_id),
        "closed_ids": sorted(row["id"] for row in rows if row["status"] == "CLOSED_CURRENT"),
        "metrics": metrics,
        "status_rows": status_rows,
        "required_validation_count": sum(len(snippets) for snippets in REQUIRED_VALIDATION_SNIPPETS.values()),
        "findings": findings,
    }


def _tracking_rows(text: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    section = _section(text, "当前实施追踪")
    if not section:
        findings.append(_finding("missing_tracking_section", "当前实施追踪", "current implementation tracking section is missing"))
        return []
    rows: list[dict[str, str]] = []
    in_table = False
    for line in section.splitlines():
        if not line.startswith("|"):
            in_table = False
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0] == "ID" and cells[1] == "当前状态":
            in_table = True
            continue
        if in_table and cells and set(cells[0]) <= {"-", ":"}:
            continue
        if not in_table:
            continue
        if len(cells) < 4:
            findings.append(_finding("malformed_tracking_row", line, "tracking row has too few cells"))
            continue
        defect_id = cells[0]
        if not re.fullmatch(r"V5-\d{3}", defect_id):
            continue
        rows.append({
            "id": defect_id,
            "status": cells[1],
            "evidence": cells[2],
            "next_action": "|".join(cells[3:]).strip(),
        })
    return rows


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    next_heading = text.find("\n## ", start + len(marker))
    return text[start:] if next_heading < 0 else text[start:next_heading]


def _metric_rows(text: str, findings: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    section = _section(text, "一、执行摘要")
    if not section:
        findings.append(_finding("missing_summary_section", "一、执行摘要", "summary section is missing"))
        return {}
    rows: dict[str, dict[str, str]] = {}
    for cells in _markdown_table_rows(section):
        if len(cells) < 4 or cells[0] in {"指标", "维度"}:
            continue
        rows[cells[0]] = {"v5": cells[1], "v6": cells[2], "change": "|".join(cells[3:]).strip()}
    return rows


def _status_rows(text: str, findings: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    section = _section(text, "二、当前修复状态追踪（基于实际代码审查）")
    if not section:
        findings.append(_finding("missing_status_section", "二、当前修复状态追踪（基于实际代码审查）", "status section is missing"))
        return {}
    rows: dict[str, dict[str, str]] = {}
    for cells in _markdown_table_rows(section):
        if len(cells) < 4 or cells[0] == "ID":
            continue
        defect_id = _plain_cell(cells[0])
        if defect_id.startswith("V5-"):
            rows[defect_id] = {
                "v5_status": _plain_cell(cells[1]),
                "v6_status": _plain_cell(cells[2]),
                "evidence": "|".join(cells[3:]).strip(),
            }
    return rows


def _detail_section(text: str, defect_id: str) -> str:
    pattern = re.compile(rf"^###\s+{re.escape(defect_id)}\b.*$", flags=re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return ""
    next_heading = text.find("\n### ", match.end())
    return text[match.start():] if next_heading < 0 else text[match.start():next_heading]


def _markdown_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and set(cells[0]) <= {"-", ":"}:
            continue
        rows.append(cells)
    return rows


def _plain_cell(value: str) -> str:
    return re.sub(r"[*`]", "", value).strip()


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v5 defect implementation tracking.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to DEFECT_ANALYSIS_REPORT_20260602_v6.md")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args(argv)

    result = check_v5_defect_tracking(args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"v5 defect tracking check {state}: {result['report']}")
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['expected']} ({finding['message']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
