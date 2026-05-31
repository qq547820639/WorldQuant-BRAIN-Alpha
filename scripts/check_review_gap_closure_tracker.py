"""Validate the defect/implementation tracking document contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACKER = ROOT / "docs" / "REVIEW_GAP_CLOSURE_20260530.md"
DEFAULT_DELIVERY_AUDIT = ROOT / "docs" / "DELIVERY_COMPLETION_AUDIT_20260528.md"
SCHEMA_VERSION = "review_gap_closure_tracker_check.v1"

REQUIRED_SECTIONS = (
    "Current Run Baseline",
    "2026-05-31 Delivery Review Triage",
    "Status Matrix",
    "Active Work Queue",
    "Not Yet Claimable",
)
BASELINE_SNIPPETS = (
    "run_pipeline.py --validate-only --config config/run_config.json --json",
    "scripts/check_frontend_surface_parity.py --json",
    "scripts/check_frontend_innerhtml.py --json",
    "document.writeln",
    "scripts/check_tracked_data_inventory.py --json",
    "scripts/check_react_build_env.py --json",
    "ready=true",
    "build_runner=local_node_modules",
    "scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history",
)
TRIAGE_SNIPPETS = (
    "| Review P0 hardcoded E2E credentials | CLOSED_CURRENT |",
    "BRAIN_E2E_*",
    "| Review P0 E2E screenshot ignore policy | CLOSED_CURRENT |",
    "data/e2e_screenshots/example.png",
    "| Review P0 CI secret scan coverage | CLOSED_CURRENT |",
    "--include-all --include-git-history",
    "output/` runtime smoke artifacts",
    "session-cookie-*",
    "| Review P1 inline HTML injection risk | CLOSED_CURRENT |",
    ".outerHTML",
    "trustedHtml",
    "createContextualFragment",
    "| Review P1 quality-gate subprocess environment | CLOSED_CURRENT |",
    "explicit allowlist",
    "BRAIN_PASSWORD",
    "OPENAI_API_KEY",
    "| Review P1 quality-gate subprocess timeout | CLOSED_CURRENT |",
    "timeout=300",
    "exit_code=124",
    "| Review P2 quality-gate preview smoke port race | CLOSED_CURRENT |",
    "launch_web.py --smoke-test --frontend react --port 0",
    "explicit `0`",
    "OS-assigned",
)
STATUS_SNIPPETS = (
    "| P0-2 React strict build | CLOSED_CURRENT |",
    "| P2-6 Frontend automated tests | CLOSED_LOCAL_WITH_TOOLCHAIN |",
    "| P3-1 Dual frontend unification | PARTIAL_LOCAL |",
)
QUEUE_ITEMS = (
    "Real BRAIN submit E2E",
    "Frontend production-surface promotion",
    "Official context refresh",
)
NOT_YET_SNIPPETS = (
    "Real BRAIN submit success is not claimable",
    "Frontend unification is not claimable",
    "Official context freshness is not claimable",
)
DELIVERY_AUDIT_SNIPPETS = (
    "docs/REVIEW_GAP_CLOSURE_20260530.md",
    "ready=true",
    "build_runner=local_node_modules",
    "lockfile, `node_modules`, required packages, and the React artifact are present",
)
STALE_DELIVERY_AUDIT_SNIPPETS = (
    "ready=false",
    "missing `npm`, lockfile",
    "current default PATH still needs npm",
    "React strict-build reproducibility on the current default PATH is not claimable",
)
TRACKER_STALE_SNIPPETS = (
    "advisory only: `ready=false`",
    "missing `npm`",
    "npm is missing on the current PATH",
    "npm-enabled local toolchain path",
    "current default PATH still needs npm",
    "React strict-build reproducibility on the current default PATH is not claimable",
)


def check_review_gap_closure_tracker(
    tracker_path: str | Path = DEFAULT_TRACKER,
    delivery_audit_path: str | Path = DEFAULT_DELIVERY_AUDIT,
) -> dict[str, Any]:
    path = Path(tracker_path)
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "tracker": str(path),
            "findings": [_finding("missing_tracker", str(path), "tracker file does not exist")],
        }
    delivery_path = Path(delivery_audit_path)
    try:
        delivery_text = delivery_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        delivery_text = ""
        findings.append(_finding("missing_delivery_audit", str(delivery_path), "delivery audit file does not exist"))

    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in text:
            findings.append(_finding("missing_section", section, "required tracker section is missing"))

    baseline = _section(text, "Current Run Baseline")
    _expect_all(baseline, BASELINE_SNIPPETS, "baseline_fact", findings)
    triage = _section(text, "2026-05-31 Delivery Review Triage")
    _expect_all(triage, TRIAGE_SNIPPETS, "review_triage_fact", findings)
    _expect_all(text, STATUS_SNIPPETS, "status_matrix_fact", findings)
    _reject_any(text, TRACKER_STALE_SNIPPETS, "stale_tracker_fact", findings)

    queue = _section(text, "Active Work Queue")
    if "| Item | Current state | Unblock condition | Minimum verification |" not in queue:
        findings.append(
            _finding("queue_header", "Active Work Queue table header", "active work queue table header is missing")
        )
    _expect_all(queue, QUEUE_ITEMS, "queue_item", findings)

    not_yet = _section(text, "Not Yet Claimable")
    _expect_all(not_yet, NOT_YET_SNIPPETS, "not_yet_claimable", findings)
    _expect_all(delivery_text, DELIVERY_AUDIT_SNIPPETS, "delivery_audit_fact", findings)
    _reject_any(delivery_text, STALE_DELIVERY_AUDIT_SNIPPETS, "stale_delivery_audit_fact", findings)

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "tracker": str(path),
        "delivery_audit": str(delivery_path),
        "findings": findings,
    }


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start == -1:
        return ""
    next_start = text.find("\n## ", start + len(marker))
    return text[start:] if next_start == -1 else text[start:next_start]


def _expect_all(text: str, expected_values: tuple[str, ...], code: str, findings: list[dict[str, str]]) -> None:
    for expected in expected_values:
        if expected not in text:
            findings.append(_finding(code, expected, "expected tracker fact is missing"))


def _reject_any(text: str, rejected_values: tuple[str, ...], code: str, findings: list[dict[str, str]]) -> None:
    for rejected in rejected_values:
        if rejected in text:
            findings.append(_finding(code, rejected, "stale tracker fact is still present"))


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check review gap closure tracker consistency.")
    parser.add_argument("--tracker", default=str(DEFAULT_TRACKER), help="Tracker Markdown path.")
    parser.add_argument("--delivery-audit", default=str(DEFAULT_DELIVERY_AUDIT), help="Delivery audit Markdown path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_review_gap_closure_tracker(args.tracker, args.delivery_audit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"review gap closure tracker check passed: {result['tracker']}")
    else:
        print(f"review gap closure tracker check failed: {result['tracker']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['message']}: {finding['expected']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
