from __future__ import annotations

from scripts.check_review_gap_closure_tracker import DEFAULT_TRACKER, check_review_gap_closure_tracker

ROOT = DEFAULT_TRACKER.parents[1]

OFFICIAL_QUEUE_ROW = (
    "| Official context refresh | Not claimable as fresh; current validation is structurally safe with "
    "`blocking_ok=True`, but reports `p1_findings=3` for expired official metadata. | BRAIN credentials "
    "and network access are available for a live official context refresh. | `.venv/bin/python "
    "fetch_official_context.py --config config/run_config.json --use-proxy --json`, then rerun "
    "`scripts/check_official_context.py`, `scripts/check_diagnostic_report.py`, and "
    "`scripts/quality_gate.py --final-release --skip-tests --json`. |"
)

def _official_context_validation(
    *,
    p1_count: int = 0,
    blocking_count: int = 0,
    fields: int = 8599,
    operators: int = 67,
    datasets: int = 20,
    dataset_field_count_sum: int = 8599,
) -> dict:
    return {
        "ok": True,
        "validation_ok": True,
        "blocking_ok": blocking_count == 0,
        "blocking_count": blocking_count,
        "p1_count": p1_count,
        "files": {
            "official_fields.json": {"record_count": fields},
            "official_operators.json": {"record_count": operators},
            "official_datasets.json": {"record_count": datasets},
        },
        "lineage": {"dataset_field_count_sum": dataset_field_count_sum},
    }

def _official_context_refresh_status(
    *,
    ok: bool = True,
    status: str = "metadata_verified",
    error_code: str = "",
    error_category: str = "",
    write_enabled: bool = True,
    manifest_stale: bool = False,
) -> dict:
    return {
        "ok": ok,
        "status": status,
        "error_code": error_code,
        "error_category": error_category,
        "write_enabled": write_enabled,
        "before": {"manifest_stale": manifest_stale},
        "after": {"manifest_stale": manifest_stale},
    }

def _react_surface_validation(
    *,
    ready: bool = True,
    production_surface: str = "inline_html_js",
    react_surface: str = "mirror",
    build_runner: str = "local_node_modules",
) -> dict:
    return {
        "ready": ready,
        "production_surface": production_surface,
        "react_surface": react_surface,
        "tooling": {"build_runner": build_runner},
    }

def _live_submit_readiness_validation(
    *,
    ready_to_submit: bool = False,
    eligible_count: int = 0,
    candidate_count: int = 1,
    job_ledgers_checked: int = 4,
    jobs_checked: int = 9,
    ledger_candidate_count: int = 2,
    ledger_eligible_count: int = 0,
    job_family_candidate_count: int = 258,
    job_family_eligible_count: int = 0,
    latest_job_id: str = "job_0009",
    max_similarity: float | None = None,
    submission_ready: int = 0,
) -> dict:
    return {
        "ok": True,
        "ready_to_submit": ready_to_submit,
        "eligible_count": eligible_count,
        "candidate_count": candidate_count,
        "job_ledgers_checked": job_ledgers_checked,
        "jobs_checked": jobs_checked,
        "ledger_candidate_count": ledger_candidate_count,
        "ledger_eligible_count": ledger_eligible_count,
        "job_family_candidate_count": job_family_candidate_count,
        "job_family_eligible_count": job_family_eligible_count,
        "job_family_ready_to_submit": bool(job_family_eligible_count),
        "latest_job_id": latest_job_id,
        "max_similarity": max_similarity,
        "summary_counts": {"submission_ready": submission_ready},
    }

def _with_official_context_queue(text: str | None = None, *, row: str = OFFICIAL_QUEUE_ROW) -> str:
    payload = text or DEFAULT_TRACKER.read_text(encoding="utf-8")
    lines = payload.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("| Official context refresh |"):
            lines[index] = row
            payload = "\n".join(lines) + "\n"
            break
    else:
        marker = (
            "## Active Work Queue\n\n"
            "| Item | Current state | Unblock condition | Minimum verification |\n"
            "|---|---|---|---|\n"
        )
        if marker in payload:
            payload = payload.replace(marker, f"{marker}{row}\n", 1)
        else:
            payload = payload.replace("|---|---|---|---|", f"|---|---|---|---|\n{row}", 1)
    marker = (
        "## Active Work Queue"
    )
    if "Official context freshness is not claimable" not in payload:
        payload = (
            payload.rstrip()
            + "\n2. Official context freshness is not claimable until the expired official metadata is refreshed from BRAIN.\n"
        )
    return payload

def _write_tracker_text(tmp_path, text: str):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(text, encoding="utf-8")
    return tracker

def test_review_gap_closure_tracker_accepts_current_document():
    result = check_review_gap_closure_tracker(
        official_context_validation=_official_context_validation(p1_count=0),
        official_context_refresh_status_validation=_official_context_refresh_status(
            ok=True,
            status="refreshed",
            error_code="",
            error_category="",
            manifest_stale=False,
        ),
        react_build_env_validation=_react_surface_validation(),
        live_submit_readiness_validation=_live_submit_readiness_validation(),
    )

    assert result["ok"] is True
    assert result["schema_version"] == "review_gap_closure_tracker_check.v1"
    baseline_by_check = {item["check"]: item["result"] for item in result["current_run_baseline"]}
    react_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "scripts/check_react_build_env.py --json" in check
    )
    assert "ready=true" in react_baseline
    assert "build_runner=local_node_modules" in react_baseline
    tracker_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "scripts/check_review_gap_closure_tracker.py --json" in check
    )
    v5_defect_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "scripts/check_v5_defect_tracking.py --json" in check
    )
    live_submit_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "scripts/check_live_submit_readiness.py --json" in check
    )
    official_context_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "fetch_official_context.py --config config/run_config.json" in check and "--json" in check
    )
    assert "PASS" in official_context_baseline
    assert "status=refreshed" in official_context_baseline
    assert "fields=8599" in official_context_baseline
    assert "operators=67" in official_context_baseline
    assert "datasets=20" in official_context_baseline
    assert "write_enabled=true" in official_context_baseline
    assert "manifest_stale=false" in official_context_baseline
    official_validation_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "scripts/check_official_context.py --config config/run_config.json" in check
    )
    assert "validation_ok=true" in official_validation_baseline
    assert "blocking_ok=true" in official_validation_baseline
    assert "blocking_count=0" in official_validation_baseline
    assert "p1_count=0" in official_validation_baseline
    assert "dataset_field_count_sum=8599" in official_validation_baseline
    assert "ready_to_submit=false" in live_submit_baseline
    assert "eligible_count=0" in live_submit_baseline
    assert "jobs_checked=9" in live_submit_baseline
    assert "job_ledgers_checked=4" in live_submit_baseline
    assert "ledger_candidate_count=2" in live_submit_baseline
    assert "ledger_eligible_count=0" in live_submit_baseline
    assert "job_family_candidate_count=258" in live_submit_baseline
    assert "job_family_eligible_count=0" in live_submit_baseline
    assert "latest_job=job_0009" in live_submit_baseline
    assert "max_similarity=null" in live_submit_baseline
    assert "required_validation_count=29" in v5_defect_baseline
    assert "findings=[]" in v5_defect_baseline
    assert "tracker_contract_ok=true" in tracker_baseline
    assert "completion_claimable=true" in tracker_baseline

    assert {
        item["review_item"]: item["current_tracking_decision"]
        for item in result["delivery_review_triage"]
    } == {
        "Review P0 hardcoded E2E credentials": "CLOSED_CURRENT",
        "Review P0 E2E screenshot ignore policy": "CLOSED_CURRENT",
        "Review P0 CI secret scan coverage": "CLOSED_CURRENT",
        "Review P1 inline HTML injection risk": "CLOSED_CURRENT",
        "Review P1 quality-gate subprocess environment": "CLOSED_CURRENT",
        "Review P1 quality-gate subprocess timeout": "CLOSED_CURRENT",
        "Review P2 quality-gate preview smoke port race": "CLOSED_CURRENT",
        "Review 2026-06-01 P0 baseUrl SSRF risk": "CLOSED_CURRENT",
        "Review 2026-06-01 P0 request body size limit": "CLOSED_CURRENT",
        "Review 2026-06-01 P1 traceback leakage": "CLOSED_CURRENT",
        "Review 2026-06-01 P1 production budget numeric limits": "CLOSED_CURRENT",
        "Review 2026-06-01 P1 silent exception swallowing": "CLOSED_CURRENT",
    }
    assert {
        item["gap"]: item["status"]
        for item in result["status_matrix"]
        if item["gap"] in {"P0-2 React strict build", "P2-6 Frontend automated tests", "P3-1 Dual frontend unification"}
    } == {
        "P0-2 React strict build": "CLOSED_CURRENT",
        "P2-6 Frontend automated tests": "CLOSED_LOCAL_WITH_TOOLCHAIN",
        "P3-1 Dual frontend unification": "CLOSED_CURRENT",
    }
    assert [row["item"] for row in result["active_queue"]] == []
    assert result["official_context"]["p1_count"] == 0
    assert result["official_context_refresh"]["status"] == "refreshed"
    assert result["official_context_refresh"]["error_code"] == ""
    assert result["official_context_refresh"]["manifest_stale"] is False
    assert result["react_surface"]["production_surface"] == "inline_html_js"
    assert result["live_submit"]["ready_to_submit"] is False
    assert result["live_submit"]["eligible_count"] == 0
    assert result["live_submit"]["jobs_checked"] == 9
    assert result["live_submit"]["job_ledgers_checked"] == 4
    assert result["live_submit"]["ledger_candidate_count"] == 2
    assert result["live_submit"]["ledger_eligible_count"] == 0
    assert result["live_submit"]["job_family_candidate_count"] == 258
    assert result["live_submit"]["job_family_eligible_count"] == 0
    assert result["live_submit"]["max_similarity"] is None
    assert result["summary"]["tracker_contract_ok"] is True
    assert result["summary"]["completion_claimable"] is True
    assert result["summary"]["completion_blockers"] == []
    assert result["summary"]["active_queue_count"] == 0
    assert result["summary"]["active_queue_items"] == []
    assert result["summary"]["official_context_fresh"] is True
    assert result["summary"]["official_context_p1_count"] == 0
    assert result["summary"]["open_status_items"] == []
    assert result["summary"]["react_ready"] is True
    assert result["summary"]["react_preview_only"] is True
    assert result["summary"]["frontend_mirror_only_decision"] is True
    assert result["summary"]["live_submit_ready"] is False
    assert result["summary"]["live_submit_eligible_count"] == 0
    assert result["summary"]["live_submit_job_ledgers_checked"] == 4
    assert result["summary"]["live_submit_jobs_checked"] == 9
    assert result["summary"]["live_submit_ledger_candidate_count"] == 2
    assert result["summary"]["live_submit_ledger_eligible_count"] == 0
    assert result["summary"]["live_submit_job_family_candidate_count"] == 258
    assert result["summary"]["live_submit_job_family_eligible_count"] == 0
    assert result["summary"]["live_submit_latest_job_id"] == "job_0009"
    assert result["summary"]["production_surface"] == "inline_html_js"
    assert result["summary"]["react_surface"] == "mirror"
    assert result["findings"] == []

def test_current_silent_exception_review_evidence_matches_source():
    guided_source = (ROOT / "brain_alpha_ops" / "ux" / "guided_pipeline.py").read_text(encoding="utf-8")
    walkthrough_source = (ROOT / "scripts" / "ux_walkthrough_local.py").read_text(encoding="utf-8")

    assert "pass  # Don't let callback failures break the pipeline" not in guided_source
    assert "guided pipeline progress callback failed" in guided_source
    assert "except: pass" not in walkthrough_source
    assert "shutdown probe failed" in walkthrough_source
    assert "shutdown request failed" in walkthrough_source

def test_review_gap_closure_tracker_rejects_missing_current_review_triage_row(tmp_path):
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    missing_item = "Review 2026-06-01 P0 baseUrl SSRF risk"
    row = next(line for line in text.splitlines() if line.startswith(f"| {missing_item} |"))
    tracker = _write_tracker_text(tmp_path, text.replace(f"{row}\n", "", 1))

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
        live_submit_readiness_validation=_live_submit_readiness_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "review_triage_item" and finding["expected"] == missing_item
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_missing_queue(tmp_path):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        """
# Review Gap Closure Tracker - fixture

## Current Run Baseline

| Check | Result |
|---|---|
| `quality_gate.py config validation` | PASS |
| `scripts/check_frontend_surface_parity.py --json` | PASS |
| `scripts/check_tracked_data_inventory.py --json` | PASS |
| `scripts/check_react_build_env.py --json` | PASS; ready=true, build_runner=local_node_modules |

## Status Matrix

| Gap | Status | Current Evidence | Remaining Evidence Needed |
|---|---|---|---|
| P0-2 React strict build | CLOSED_LOCAL_WITH_TOOLCHAIN | fixture | fixture |
| P2-6 Frontend automated tests | CLOSED_LOCAL_WITH_TOOLCHAIN | fixture | fixture |
| P3-1 Dual frontend unification | PARTIAL_LOCAL | fixture | fixture |

## Not Yet Claimable

1. Real BRAIN submit success is not claimable.
2. Frontend unification is not claimable.
3. Official context freshness is not claimable.
""",
        encoding="utf-8",
    )

    result = check_review_gap_closure_tracker(tracker)

    assert result["ok"] is False
    assert any(finding["code"] == "missing_section" and finding["expected"] == "Active Work Queue" for finding in result["findings"])
    assert any(finding["code"] == "queue_header" for finding in result["findings"])

def test_review_gap_closure_tracker_rejects_stale_delivery_audit_fact(tmp_path):
    delivery_audit = tmp_path / "delivery.md"
    delivery_audit.write_text(
        """
docs/REVIEW_GAP_CLOSURE_20260530.md records the current tracker.
The current blocker is the default local PATH because `npm` is unavailable here.
The lockfile, `node_modules`, required packages, and the React artifact are present.
Old wording: ready=false; missing `npm`, lockfile, `node_modules`, and React dependencies.
""",
        encoding="utf-8",
    )

    result = check_review_gap_closure_tracker(delivery_audit_path=delivery_audit)

    assert result["ok"] is False
    assert any(finding["code"] == "stale_delivery_audit_fact" for finding in result["findings"])

def test_review_gap_closure_tracker_rejects_stale_react_tracker_fact(tmp_path):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        """
# Review Gap Closure Tracker - fixture

## Current Run Baseline

| Check | Result |
|---|---|
| `quality_gate.py config validation` | PASS |
| `scripts/check_frontend_surface_parity.py --json` | PASS |
| `scripts/check_frontend_innerhtml.py --json` | PASS; document.writeln covered |
| `scripts/check_tracked_data_inventory.py --json` | PASS |
| `scripts/check_react_build_env.py --json` | advisory only: `ready=false`; npm is missing on the current PATH |
| `scripts/scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history` | PASS |

## 2026-05-31 Delivery Review Triage

placeholder

## Status Matrix

| Gap | Status | Current Evidence | Remaining Evidence Needed |
|---|---|---|---|
| P0-2 React strict build | CLOSED_LOCAL_WITH_TOOLCHAIN | fixture | fixture |
| P2-6 Frontend automated tests | CLOSED_LOCAL_WITH_TOOLCHAIN | fixture | fixture |
| P3-1 Dual frontend unification | PARTIAL_LOCAL | fixture | fixture |

## Active Work Queue

| Item | Current state | Unblock condition | Minimum verification |
|---|---|---|---|
| Real BRAIN submit E2E | fixture | fixture | fixture |
| Frontend production-surface promotion | fixture | fixture | fixture |
| Official context refresh | fixture | fixture | fixture |

## Not Yet Claimable

1. Real BRAIN submit success is not claimable.
2. Frontend unification is not claimable.
3. Official context freshness is not claimable.
""",
        encoding="utf-8",
    )

    result = check_review_gap_closure_tracker(tracker)

    assert result["ok"] is False
    assert any(finding["code"] == "stale_tracker_fact" for finding in result["findings"])

def test_review_gap_closure_tracker_rejects_baseline_result_fact_in_wrong_row(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace("`ready=true`, `build_runner=local_node_modules`", "`ready=false`, `build_runner=local_node_modules`", 1)
    text = text.replace(
        "| `quality_gate.py config validation` | PASS |",
        "| `quality_gate.py config validation` | PASS; ready=true belongs to the React baseline row. |",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "baseline_row_fact"
        and finding["expected"] == "scripts/check_react_build_env.py --json:ready=true"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_duplicate_baseline_check(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    baseline_row = next(
        line for line in text.splitlines() if "scripts/check_frontend_surface_parity.py --json" in line
    )
    tracker.write_text(text.replace(baseline_row, f"{baseline_row}\n{baseline_row}", 1), encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "baseline_duplicate_check"
        and finding["expected"] == "scripts/check_frontend_surface_parity.py --json"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_missing_v5_defect_tracking_baseline(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    baseline_row = next(
        line for line in text.splitlines() if "scripts/check_v5_defect_tracking.py --json" in line
    )
    tracker.write_text(text.replace(f"{baseline_row}\n", "", 1), encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "baseline_check"
        and finding["expected"] == "scripts/check_v5_defect_tracking.py --json"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_empty_queue_summary_with_active_item(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = _with_official_context_queue(
        DEFAULT_TRACKER.read_text(encoding="utf-8"),
    )
    text = text.replace(
        "| Official context refresh |",
        "No active blocking queue items remain for this closure tracker.\n| Official context refresh |",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(p1_count=3),
        official_context_refresh_status_validation=_official_context_refresh_status(
            ok=False,
            status="failed",
            error_code="MISSING_CREDENTIALS",
            error_category="auth",
            manifest_stale=True,
        ),
        react_build_env_validation=_react_surface_validation(),
        live_submit_readiness_validation=_live_submit_readiness_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "active_queue_summary_fact"
        and finding["expected"] == "No active blocking queue items remain"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_self_summary_baseline(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8").replace(
        "`completion_claimable=true`",
        "`completion_claimable=false`",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(p1_count=0),
        official_context_refresh_status_validation=_official_context_refresh_status(
            ok=True,
            status="refreshed",
            error_code="",
            error_category="",
            manifest_stale=False,
        ),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "tracker_self_summary_fact"
        and finding["expected"] == "completion_claimable=true"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_mismatched_live_submit_readiness(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    replacements = (
        (
            "`eligible_count=0`, `jobs_checked=9`, `job_ledgers_checked=4`, `ledger_candidate_count=2`, `ledger_eligible_count=0`",
            "`eligible_count=1`, `jobs_checked=9`, `job_ledgers_checked=4`, `ledger_candidate_count=2`, `ledger_eligible_count=0`",
        ),
        (
            "`jobs_checked=9`, `job_ledgers_checked=4`, `ledger_candidate_count=2`, `ledger_eligible_count=0`",
            "`jobs_checked=9`, `job_ledgers_checked=4`, `ledger_candidate_count=2`, `ledger_eligible_count=1`",
        ),
        (
            "`job_family_candidate_count=258`, `job_family_eligible_count=0`",
            "`job_family_candidate_count=258`, `job_family_eligible_count=1`",
        ),
        ("`eligible_count=0`", "`eligible_count=1`"),
        ("`ledger_eligible_count=0`", "`ledger_eligible_count=1`"),
        ("`job_family_eligible_count=0`", "`job_family_eligible_count=1`"),
    )
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new, 1)
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
        live_submit_readiness_validation=_live_submit_readiness_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "baseline_row_fact"
        and finding["expected"] == "scripts/check_live_submit_readiness.py --json:eligible_count=0"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "baseline_row_fact"
        and finding["expected"] == "scripts/check_live_submit_readiness.py --json:ledger_eligible_count=0"
        for finding in result["findings"]
    )
    # real_submit_readiness_fact checks come from the Status Matrix row,
    # which is not modified by this test. The baseline_row_fact findings
    # above are sufficient to verify mismatch detection.

def test_review_gap_closure_tracker_rejects_mismatched_review_triage_decision(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace(
        "| Review P1 quality-gate subprocess timeout | CLOSED_CURRENT |",
        "| Review P1 quality-gate subprocess timeout | PARTIAL_LOCAL |",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "review_triage_item"
        and finding["expected"] == "Review P1 quality-gate subprocess timeout:CLOSED_CURRENT"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_duplicate_review_triage_item(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    triage_row = next(
        line for line in text.splitlines() if line.startswith("| Review P0 CI secret scan coverage |")
    )
    tracker.write_text(text.replace(triage_row, f"{triage_row}\n{triage_row}", 1), encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "review_triage_duplicate_item"
        and finding["expected"] == "Review P0 CI secret scan coverage"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_mismatched_status_matrix_row(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace(
        "| P0-2 React strict build | CLOSED_CURRENT |",
        "| P0-2 React strict build | PARTIAL_LOCAL |",
        1,
    )
    text = text.replace(
        "| P2-6 Frontend automated tests |",
        "| P2-6 Frontend automated tests | P0-2 React strict build is CLOSED_CURRENT elsewhere; ",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "status_matrix_fact"
        and finding["expected"] == "P0-2 React strict build:CLOSED_CURRENT"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_duplicate_status_matrix_gap(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    status_row = next(line for line in text.splitlines() if line.startswith("| P3-1 Dual frontend unification |"))
    tracker.write_text(text.replace(status_row, f"{status_row}\n{status_row}", 1), encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "status_matrix_duplicate_gap"
        and finding["expected"] == "P3-1 Dual frontend unification"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_requires_queue_item_in_first_cell(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = _with_official_context_queue(DEFAULT_TRACKER.read_text(encoding="utf-8"))
    official_row = next(line for line in text.splitlines() if line.startswith("| Official context refresh |"))
    wrong_row = (
        "| Official context stale note | Official context refresh is mentioned outside the item cell. | "
        "BRAIN credentials and network access are available. | Rerun the official refresh checks. |"
    )
    text = text.replace(official_row, wrong_row, 1)
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(p1_count=3),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "queue_item" and finding["expected"] == "Official context refresh"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "queue_unexpected_item" and finding["expected"] == "Official context stale note"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_duplicate_real_submit_boundary(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    real_submit_row = next(
        line for line in text.splitlines() if line.startswith("| Real BRAIN submit E2E |")
    )
    tracker.write_text(text.replace(real_submit_row, f"{real_submit_row}\n{real_submit_row}", 1), encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "real_submit_duplicate_item" and finding["expected"] == "Real BRAIN submit E2E"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_official_context_queue_when_fresh(tmp_path):
    tracker_text = _with_official_context_queue()
    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(p1_count=0),
    )

    assert result["ok"] is False
    assert result["summary"]["tracker_contract_ok"] is False
    assert result["summary"]["finding_count"] > 0
    assert any(finding["code"] == "stale_official_context_queue_fact" for finding in result["findings"])

def test_review_gap_closure_tracker_rejects_stale_official_context_not_yet_p1_text(tmp_path):
    tracker_text = (
        DEFAULT_TRACKER.read_text(encoding="utf-8").rstrip()
        + "\n2. Official context freshness is not claimable until refresh returns `p1_findings=0`.\n"
    )

    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(p1_count=0),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "stale_official_context_queue_fact"
        and finding["expected"] == "p1_findings="
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_mismatched_official_context_p1_count(tmp_path):
    tracker_text = _with_official_context_queue()
    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(p1_count=2),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "official_context_queue_fact" and finding["expected"] == "p1_findings=2"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_mismatched_official_context_blocking_count(tmp_path):
    tracker_text = _with_official_context_queue()
    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(p1_count=0, blocking_count=2),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "official_context_queue_fact" and finding["expected"] == "blocking_count=2"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_official_context_refresh_baseline(tmp_path):
    tracker_text = DEFAULT_TRACKER.read_text(encoding="utf-8").replace(
        "status=metadata_verified",
        "status=OLD_STATUS",
        1,
    )
    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(),
        official_context_refresh_status_validation=_official_context_refresh_status(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "official_context_refresh_baseline_fact"
        and finding["expected"] == "status=metadata_verified"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_official_context_counts(tmp_path):
    tracker_text = DEFAULT_TRACKER.read_text(encoding="utf-8").replace("fields=8599", "fields=7780", 1)

    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(),
        official_context_refresh_status_validation=_official_context_refresh_status(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "official_context_refresh_baseline_fact"
        and finding["expected"] == "fields=8599"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_dataset_field_sum(tmp_path):
    tracker_text = DEFAULT_TRACKER.read_text(encoding="utf-8").replace(
        "dataset_field_count_sum=8599",
        "dataset_field_count_sum=7780",
        1,
    )

    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "official_context_baseline_fact"
        and finding["expected"] == "dataset_field_count_sum=8599"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_official_context_refresh_queue(tmp_path):
    tracker_text = _with_official_context_queue(
        row=(
            "| Official context refresh | Not claimable as fresh; current validation is structurally safe with "
            "`blocking_ok=True`, but reports `p1_findings=3` for expired official metadata. Latest refresh "
            "status is `status=failed`, `error_code=MISSING_CREDENTIALS`, `error_category=auth`, "
            "`write_enabled=true`, and `manifest_stale=false`. | BRAIN credentials and network access "
            "are available for a live official context refresh. | `.venv/bin/python fetch_official_context.py "
            "--config config/run_config.json --use-proxy --json`, then rerun `scripts/check_official_context.py`, "
            "`scripts/check_diagnostic_report.py`, and `scripts/quality_gate.py --final-release --skip-tests --json`. |"
        )
    )
    result = check_review_gap_closure_tracker(
        _write_tracker_text(tmp_path, tracker_text),
        official_context_validation=_official_context_validation(p1_count=3),
        official_context_refresh_status_validation=_official_context_refresh_status(
            ok=False,
            status="failed",
            error_code="MISSING_CREDENTIALS",
            error_category="auth",
            manifest_stale=True,
        ),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "official_context_refresh_queue_fact"
        and finding["expected"] == "manifest_stale=true"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_stale_frontend_surface_queue_after_promotion():
    result = check_review_gap_closure_tracker(
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(
            production_surface="react",
            react_surface="production",
        ),
    )

    assert result["ok"] is False
    assert any(finding["code"] == "stale_frontend_surface_fact" for finding in result["findings"])

def test_review_gap_closure_tracker_rejects_stale_react_ready_fact():
    result = check_review_gap_closure_tracker(
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(ready=False, build_runner=""),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "stale_react_surface_fact" and finding["expected"] == "ready=true"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_weakened_real_submit_gate(tmp_path):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        DEFAULT_TRACKER.read_text(encoding="utf-8").replace(
            "low-risk candidate with complete official metrics",
            "candidate selected by the operator",
        ),
        encoding="utf-8",
    )

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "real_submit_boundary_fact"
        and finding["expected"] == "low-risk candidate with complete official metrics"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_not_yet_submit_claim_without_zero_eligibility(tmp_path):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        DEFAULT_TRACKER.read_text(encoding="utf-8").replace(
            (
                "current local readiness has `eligible_count=0`, `ledger_eligible_count=0`, "
                "and `job_family_eligible_count=0`."
            ),
            "current local readiness is available for follow-up.",
            1,
        ),
        encoding="utf-8",
    )

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert {
        finding["expected"]
        for finding in result["findings"]
        if finding["code"] == "not_yet_claimable"
    } >= {"eligible_count=0", "ledger_eligible_count=0", "job_family_eligible_count=0"}

def test_review_gap_closure_tracker_rejects_real_submit_fact_in_wrong_row(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace(
        "low-risk candidate with complete official metrics",
        "operator-selected candidate",
        1,
    )
    text = text.replace(
        "| `.venv/bin/python scripts/check_live_submit_readiness.py --json` |",
        "| `.venv/bin/python scripts/check_live_submit_readiness.py --json` | low-risk candidate with complete official metrics; ",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "real_submit_boundary_fact"
        and finding["expected"] == "low-risk candidate with complete official metrics"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_mirror_only_decision_fact_in_wrong_row(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace(
        "`scripts/quality_gate.py` now runs `frontend_surface_parity`",
        "`scripts/quality_gate.py` now runs frontend parity",
        1,
    )
    text = text.replace("keep `frontend_surface_parity` green", "keep parity green", 1)
    text = text.replace(
        "| Real BRAIN submit E2E |",
        "| Real BRAIN submit E2E | `frontend_surface_parity`; ",
        1,
    )
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "queue_item"
        and finding["expected"] == "Frontend production-surface promotion"
        for finding in result["findings"]
    )

def test_review_gap_closure_tracker_rejects_queue_row_missing_minimum_verification(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = _with_official_context_queue(DEFAULT_TRACKER.read_text(encoding="utf-8"))
    official_row = next(line for line in text.splitlines() if line.startswith("| Official context refresh |"))
    cells = official_row.split("|")
    cells[4] = " "
    text = text.replace(official_row, "|".join(cells), 1)
    tracker.write_text(text, encoding="utf-8")

    result = check_review_gap_closure_tracker(
        tracker,
        official_context_validation=_official_context_validation(p1_count=3),
        react_build_env_validation=_react_surface_validation(),
    )

    assert result["ok"] is False
    assert any(
        finding["code"] == "queue_row_detail"
        and finding["expected"] == "Official context refresh:minimum_verification"
        for finding in result["findings"]
    )
