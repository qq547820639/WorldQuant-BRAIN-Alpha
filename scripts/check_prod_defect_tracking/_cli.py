"""CLI entry point for production defect tracking validation."""

from __future__ import annotations

import argparse
import json

from ._checker import check_prod_defect_tracking
from ._constants import DEFAULT_CONFIG, DEFAULT_JOBS, DEFAULT_REPORT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check production defect tracking evidence.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to production defect report.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="Production jobs ledger path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_prod_defect_tracking(args.report, config_path=args.config, jobs_path=args.jobs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"production defect tracking {status}: {result['report']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['expected']}: {finding['message']}")
    return 0 if result["ok"] else 1
