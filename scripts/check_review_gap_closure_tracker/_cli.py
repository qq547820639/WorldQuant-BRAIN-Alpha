"""CLI entry point for the review gap closure tracker check.

Split from the former ``scripts/check_review_gap_closure_tracker.py`` monolith
(Task A3). Parses ``argparse`` flags and renders the JSON or human-readable
result. The thin ``scripts/check_review_gap_closure_tracker.py`` shim imports
``main`` from this module via the package ``__init__``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ._constants import DEFAULT_CONFIG, DEFAULT_DELIVERY_AUDIT, DEFAULT_JOBS, DEFAULT_TRACKER  # noqa: E402
from ._core import check_review_gap_closure_tracker  # noqa: E402


def _print_human_result(result: dict[str, Any]) -> None:
    state = "passed" if result["ok"] else "failed"
    print(f"review gap closure tracker check {state}: {result['tracker']}")
    summary = result.get("summary") or {}
    if summary:
        counts = summary["status_counts"]
        queue_items = ", ".join(summary["active_queue_items"]) or "none"
        claimable = "yes" if summary["completion_claimable"] else "no"
        print(f"summary: closed={counts['closed']}, partial={counts['partial']}, active_queue={summary['active_queue_count']}")
        print(f"active queue items: {queue_items}")
        print(f"official context: fresh={summary['official_context_fresh']}, blocking={summary['official_context_blocking_count']}, p1={summary['official_context_p1_count']}")
        print(f"frontend surface: production={summary['production_surface']}, react={summary['react_surface']}, ready={summary['react_ready']}, runner={summary['react_build_runner']}")
        print(f"completion claimable: {claimable}")
        if summary.get("completion_blockers"):
            print(f"completion blockers: {', '.join(summary['completion_blockers'])}")
    if not result["ok"]:
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['message']}: {finding['expected']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check review gap closure tracker consistency.")
    parser.add_argument("--tracker", default=str(DEFAULT_TRACKER), help="Tracker Markdown path.")
    parser.add_argument("--delivery-audit", default=str(DEFAULT_DELIVERY_AUDIT), help="Delivery audit Markdown path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path for current official-context validation.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="Production jobs ledger path for live-submit readiness.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_review_gap_closure_tracker(args.tracker, args.delivery_audit, config_path=args.config, jobs_path=args.jobs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0 if result["ok"] else 1
