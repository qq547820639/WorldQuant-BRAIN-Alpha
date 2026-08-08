from __future__ import annotations

"""Validate the v6 BRAIN Alpha Ops defect tracking report.

``docs/DEFECT_ANALYSIS_REPORT_20260602_v6.md`` carries the current
fix-status tracking table (v5 vs v6 status and evidence), the v5/v6 metric
comparison, and the per-defect validation evidence matrix.  This check locks
the P1 tracked row set, the required closures, the remaining-work metric, a
few locked status/evidence facts, and the validation evidence so that tracking
drift is caught in CI.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260602_v6.md"
SCHEMA_VERSION = "v5_defect_tracking_check.v1"

# P1 defect ids that must appear in the current-status tracking table.
REQUIRED_P1_IDS = tuple(f"V5-00{index}" for index in range(1, 10))

# Defect ids whose v5 status must be CLOSED_CURRENT.
REQUIRED_CLOSURES = (
    "V5-002",
    "V5-003",
    "V5-004",
    "V5-005",
    "V5-006",
    "V5-007",
    "V5-008",
)

# Locked v6 status facts: id -> expected v6 status.
STATUS_EXPECTED = {
    "V5-013": "FIXED",
}

# Locked evidence facts: (id, required snippet) -> finding code.
EVIDENCE_REQUIRED = (
    ("V5-025~V5-031", "React mirror-only", "status_evidence_mismatch"),
)

# Expected metric v6 values (the metric table's third column).
EXPECTED_METRICS = {
    "实际待修复": "1",
}

# Validation evidence required per defect (from section 六.1).
REQUIRED_VALIDATION = {
    "V5-001": (
        "tests/test_official_adapter.py::test_list_user_alphas_warns_on_page_with_no_new_unique_items_without_stopping",
        "tests/test_official_adapter.py::test_list_user_alphas_can_be_cancelled_by_progress_callback_without_page_cap",
        "tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan",
        "tests/test_web_sync_job.py::test_run_sync_job_service_ignores_elapsed_limit_and_scans_all_pages",
        "tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows",
        "tests/test_pipeline.py::test_pipeline_cloud_sync_ignores_elapsed_limit_and_merges_all_rows",
        "duplicate_unique_items",
        "stalled_unique_pages",
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

_ID_RE = re.compile(r"^(V5-\d+(?:~V5-\d+)?)\b")
_UNBOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(set(cell) <= {"-", ":"} for cell in cells)


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = text.splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header = _cells(lines[i])
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            tables.append((header, rows))
            continue
        i += 1
    return tables


def _clean(value: str) -> str:
    value = _UNBOLD_RE.sub(r"\1", value)
    return value.strip()


def _status_rows(text: str) -> dict[str, dict[str, str]]:
    for header, rows in _tables(text):
        if not any("v5状态" in cell for cell in header):
            continue
        if not any("v6状态" in cell for cell in header):
            continue
        try:
            v5_col = header.index("v5状态")
            v6_col = header.index("v6状态")
            evidence_col = header.index("实际证据")
        except ValueError:
            continue
        parsed: dict[str, dict[str, str]] = {}
        for cells in rows:
            if len(cells) <= evidence_col:
                continue
            match = _ID_RE.match(_clean(cells[0]))
            if not match:
                continue
            defect_id = match.group(1)
            parsed[defect_id] = {
                "id": defect_id,
                "v5_status": _clean(cells[v5_col]),
                "v6_status": _clean(cells[v6_col]),
                "evidence": " | ".join(_clean(cell) for cell in cells[evidence_col:]),
            }
        return parsed
    return {}


def _metrics(text: str) -> dict[str, dict[str, str]]:
    for header, rows in _tables(text):
        if not any("指标" in cell for cell in header):
            continue
        parsed: dict[str, dict[str, str]] = {}
        for cells in rows:
            if len(cells) < 3:
                continue
            parsed[cells[0]] = {"v5": cells[1], "v6": cells[2]}
        return parsed
    return {}


def _p1_rows(text: str) -> dict[str, dict[str, str]]:
    for header, rows in _tables(text):
        if not any("当前状态" in cell for cell in header):
            continue
        if not any(cell in header for cell in ("ID", "缺陷")):
            continue
        status_col = header.index("当前状态")
        parsed: dict[str, dict[str, str]] = {}
        for cells in rows:
            if len(cells) <= status_col:
                continue
            match = _ID_RE.match(_clean(cells[0]))
            if not match:
                continue
            parsed[match.group(1)] = {"id": match.group(1), "status": _clean(cells[status_col])}
        return parsed
    return {}


def check_v5_defect_tracking(report_path: str | Path = DEFAULT_REPORT) -> dict[str, object]:
    report = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(report),
            "findings": [_finding("missing_report", str(report), "v5 defect tracking report does not exist")],
        }

    status_rows = _status_rows(text)
    p1_rows = _p1_rows(text)

    for defect_id in REQUIRED_P1_IDS:
        if defect_id not in p1_rows:
            findings.append(_finding("missing_p1_tracking_row", defect_id, "P1 tracking row is missing"))

    for defect_id in REQUIRED_CLOSURES:
        row = p1_rows.get(defect_id)
        if row is None or row["status"] != "CLOSED_CURRENT":
            findings.append(_finding("required_closure_missing", defect_id, "required closure is not tracked as CLOSED_CURRENT"))

    for defect_id, expected_status in STATUS_EXPECTED.items():
        row = status_rows.get(defect_id)
        if row is None or row["v6_status"] != expected_status:
            findings.append(_finding("status_mismatch", f"{defect_id}:{expected_status}", "locked v6 status changed"))

    for defect_id, snippet, code in EVIDENCE_REQUIRED:
        row = status_rows.get(defect_id)
        if row is None or snippet not in row["evidence"]:
            findings.append(_finding(code, f"{defect_id}:{snippet}", "locked evidence snippet changed"))

    metrics = _metrics(text)
    for metric_id, expected in EXPECTED_METRICS.items():
        actual = metrics.get(metric_id, {}).get("v6")
        if actual != expected:
            findings.append(_finding("metric_mismatch", f"{metric_id}={expected}", "tracked metric drifted"))

    required_validation_count = sum(len(snippets) for snippets in REQUIRED_VALIDATION.values())
    for defect_id, snippets in REQUIRED_VALIDATION.items():
        for snippet in snippets:
            if snippet not in text:
                findings.append(_finding("validation_evidence_missing", f"{defect_id}:{snippet}", "validation evidence is missing"))

    closed_ids = sorted(
        row["id"] for row in status_rows.values() if row["v6_status"] in {"FIXED", "CLOSED_CURRENT"}
    )

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(report),
        "p1_tracked_count": sum(1 for defect_id in REQUIRED_P1_IDS if defect_id in p1_rows),
        "metrics": metrics,
        "status_rows": status_rows,
        "required_validation_count": required_validation_count,
        "closed_ids": closed_ids,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check v5 defect tracking evidence.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to the v5 defect tracking report.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_v5_defect_tracking(args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"v5 defect tracking {status}: {result['report']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['expected']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())