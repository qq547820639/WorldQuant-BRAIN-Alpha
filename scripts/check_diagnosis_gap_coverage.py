"""Check executable coverage for the diagnosis gap plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = ROOT / "config" / "run_config.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check diagnosis gap coverage.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path.")
    parser.add_argument("--strict-freshness", action="store_true", help="Require fresh official-context evidence.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    from brain_alpha_ops.diagnosis_gap_coverage import check_diagnosis_gap_coverage

    result = check_diagnosis_gap_coverage(args.config, strict_freshness=args.strict_freshness)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif result["ok"]:
        print("diagnosis gap coverage check passed.")
    else:
        print("diagnosis gap coverage check failed.")
        for finding in result.get("findings") or []:
            print(f"[{finding.get('severity')}] {finding.get('code')}: {finding.get('message')}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
