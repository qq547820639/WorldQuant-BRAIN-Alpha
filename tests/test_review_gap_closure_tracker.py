from __future__ import annotations

from scripts.check_review_gap_closure_tracker import DEFAULT_TRACKER, check_review_gap_closure_tracker


OFFICIAL_QUEUE_ROW = (
    "| Official context refresh | Not claimable as fresh; current validation is structurally safe with "
    "`blocking_ok=True`, but reports `p1_findings=3` for expired official metadata. | BRAIN credentials "
    "and network access are available for a live official context refresh. | `.venv/bin/python "
    "fetch_official_context.py --config config/run_config.json --json`, then rerun "
    "`scripts/check_official_context.py`, `scripts/check_diagnostic_report.py`, and "
    "`scripts/quality_gate.py --final-release --skip-tests --json`. |"
)


def _official_context_validation(*, p1_count: int = 0, blocking_count: int = 0) -> dict:
    return {
        "blocking_ok": blocking_count == 0,
        "blocking_count": blocking_count,
        "p1_count": p1_count,
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
    jobs_checked: int = 8,
    ledger_candidate_count: int = 2,
    ledger_eligible_count: int = 0,
    job_family_candidate_count: int = 17,
    job_family_eligible_count: int = 0,
    latest_job_id: str = "job_0008",
    max_similarity: float | None = 1.0,
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
    real_submit_row = next(line for line in payload.splitlines() if line.startswith("| Real BRAIN submit E2E |"))
    payload = payload.replace(real_submit_row, f"{real_submit_row}\n{row}", 1)
    if "Official context freshness is not claimable" not in payload:
        payload = (
            payload.rstrip()
            + "\n3. Official context freshness is not claimable until the expired official metadata is refreshed from BRAIN.\n"
        )
    return payload


def _write_tracker_text(tmp_path, text: str):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(text, encoding="utf-8")
    return tracker


def test_review_gap_closure_tracker_accepts_current_document():
    result = check_review_gap_closure_tracker(
        official_context_validation=_official_context_validation(),
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
    live_submit_baseline = next(
        result
        for check, result in baseline_by_check.items()
        if "scripts/check_live_submit_readiness.py --json" in check
    )
    assert "ready_to_submit=false" in live_submit_baseline
    assert "eligible_count=0" in live_submit_baseline
    assert "jobs_checked=8" in live_submit_baseline
    assert "job_ledgers_checked=4" in live_submit_baseline
    assert "ledger_eligible_count=0" in live_submit_baseline
    assert "job_family_candidate_count=17" in live_submit_baseline
    assert "job_family_eligible_count=0" in live_submit_baseline
    assert "max_similarity=1.0" in live_submit_baseline
    assert "tracker_contract_ok=true" in tracker_baseline
    assert "completion_claimable=false" in tracker_baseline
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
    assert [item["item"] for item in result["active_queue"]] == [
        "Real BRAIN submit E2E",
    ]
    assert result["official_context"]["p1_count"] == 0
    assert result["react_surface"]["production_surface"] == "inline_html_js"
    assert result["live_submit"]["ready_to_submit"] is False
    assert result["live_submit"]["eligible_count"] == 0
    assert result["live_submit"]["jobs_checked"] == 8
    assert result["live_submit"]["job_ledgers_checked"] == 4
    assert result["live_submit"]["ledger_eligible_count"] == 0
    assert result["live_submit"]["job_family_candidate_count"] == 17
    assert result["live_submit"]["job_family_eligible_count"] == 0
    assert result["live_submit"]["max_similarity"] == 1.0
    assert result["summary"]["tracker_contract_ok"] is True
    assert result["summary"]["completion_claimable"] is False
    assert result["summary"]["completion_blockers"] == [
        "active_queue:Real BRAIN submit E2E",
    ]
    for blocker in result["summary"]["completion_blockers"]:
        assert blocker in tracker_baseline
    assert result["summary"]["active_queue_count"] == 1
    assert result["summary"]["active_queue_items"] == [
        "Real BRAIN submit E2E",
    ]
    assert result["summary"]["official_context_fresh"] is True
    assert result["summary"]["official_context_p1_count"] == 0
    assert result["summary"]["open_status_items"] == []
    assert result["summary"]["react_ready"] is True
    assert result["summary"]["react_preview_only"] is True
    assert result["summary"]["frontend_mirror_only_decision"] is True
    assert result["summary"]["live_submit_ready"] is False
    assert result["summary"]["live_submit_eligible_count"] == 0
    assert result["summary"]["live_submit_job_ledgers_checked"] == 4
    assert result["summary"]["live_submit_jobs_checked"] == 8
    assert result["summary"]["live_submit_ledger_candidate_count"] == 2
    assert result["summary"]["live_submit_ledger_eligible_count"] == 0
    assert result["summary"]["live_submit_job_family_candidate_count"] == 17
    assert result["summary"]["live_submit_job_family_eligible_count"] == 0
    assert result["summary"]["live_submit_latest_job_id"] == "job_0008"
    assert result["summary"]["production_surface"] == "inline_html_js"
    assert result["summary"]["react_surface"] == "mirror"
    assert result["findings"] == []


def test_review_gap_closure_tracker_rejects_missing_queue(tmp_path):
    tracker = tmp_path / "tracker.md"
    tracker.write_text(
        """
# Review Gap Closure Tracker - fixture

## Current Run Baseline

| Check | Result |
|---|---|
| `run_pipeline.py --validate-only --config config/run_config.json --json` | PASS |
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
| `run_pipeline.py --validate-only --config config/run_config.json --json` | PASS |
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
        "| `.venv/bin/python run_pipeline.py --validate-only --config config/run_config.json --json` | PASS |",
        "| `.venv/bin/python run_pipeline.py --validate-only --config config/run_config.json --json` | PASS; ready=true belongs to the React baseline row. |",
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


def test_review_gap_closure_tracker_rejects_stale_self_summary_baseline(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8").replace(
        "`completion_claimable=false`",
        "`completion_claimable=true`",
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
        finding["code"] == "tracker_self_summary_fact"
        and finding["expected"] == "completion_claimable=false"
        for finding in result["findings"]
    )


def test_review_gap_closure_tracker_rejects_mismatched_live_submit_readiness(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace("`eligible_count=0`", "`eligible_count=1`", 1)
    text = text.replace("`ledger_eligible_count=0`", "`ledger_eligible_count=1`", 1)
    text = text.replace("`job_family_eligible_count=0`", "`job_family_eligible_count=1`", 1)
    text = text.replace(
        "`eligible_count=0`, `jobs_checked=8`, `job_ledgers_checked=4`, `ledger_eligible_count=0`",
        "`eligible_count=1`, `jobs_checked=8`, `job_ledgers_checked=4`, `ledger_eligible_count=0`",
        1,
    )
    text = text.replace(
        "`jobs_checked=8`, `job_ledgers_checked=4`, `ledger_eligible_count=0`",
        "`jobs_checked=8`, `job_ledgers_checked=4`, `ledger_eligible_count=1`",
        1,
    )
    text = text.replace(
        "`job_family_candidate_count=17`, `job_family_eligible_count=0`",
        "`job_family_candidate_count=17`, `job_family_eligible_count=1`",
        1,
    )
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
    assert any(
        finding["code"] == "real_submit_readiness_fact"
        and finding["expected"] == "eligible_count=0"
        for finding in result["findings"]
    )
    assert any(
        finding["code"] == "real_submit_readiness_fact"
        and finding["expected"] == "ledger_eligible_count=0"
        for finding in result["findings"]
    )


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
    text = _with_official_context_queue(
        row=(
            "| Official context stale note | Official context refresh is mentioned outside the item cell. | "
            "BRAIN credentials and network access are available. | Rerun the official refresh checks. |"
        )
    )
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


def test_review_gap_closure_tracker_rejects_duplicate_queue_item(tmp_path):
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
        finding["code"] == "queue_duplicate_item" and finding["expected"] == "Real BRAIN submit E2E"
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
        finding["code"] == "real_submit_queue_fact"
        and finding["expected"] == "low-risk candidate with complete official metrics"
        for finding in result["findings"]
    )


def test_review_gap_closure_tracker_rejects_real_submit_fact_in_wrong_queue_row(tmp_path):
    tracker = tmp_path / "tracker.md"
    text = DEFAULT_TRACKER.read_text(encoding="utf-8")
    text = text.replace(
        "low-risk candidate with complete official metrics",
        "operator-selected candidate",
        1,
    )
    text = text.replace(
        "| Frontend production-surface promotion |",
        "| Frontend production-surface promotion | low-risk candidate with complete official metrics; ",
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
        finding["code"] == "real_submit_queue_fact"
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
    text = _with_official_context_queue(
        row=(
            "| Official context refresh | Not claimable as fresh; current validation is structurally safe with "
            "`blocking_ok=True`, but reports `p1_findings=3` for expired official metadata. | BRAIN credentials "
            "and network access are available for a live official context refresh. | |"
        )
    )
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
