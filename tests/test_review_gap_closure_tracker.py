from __future__ import annotations

from scripts.check_review_gap_closure_tracker import check_review_gap_closure_tracker


def test_review_gap_closure_tracker_accepts_current_document():
    result = check_review_gap_closure_tracker()

    assert result["ok"] is True
    assert result["schema_version"] == "review_gap_closure_tracker_check.v1"
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
