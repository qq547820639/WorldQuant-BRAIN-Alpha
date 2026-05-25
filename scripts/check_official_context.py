"""Check official BRAIN context cache completeness and lineage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate official BRAIN context files and metadata.")
    parser.add_argument("--config", default=str(ROOT / "config" / "run_config.json"), help="Run config path.")
    parser.add_argument("--data-dir", default="", help="Override the official context data directory.")
    parser.add_argument("--allow-missing-metadata", action="store_true", help="Do not fail when .meta.json files are missing.")
    parser.add_argument("--allow-non-official-source", action="store_true", help="Do not require metadata source=official_api.")
    parser.add_argument("--strict-freshness", action="store_true", help="Fail when official metadata is stale or incomplete.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    from brain_alpha_ops.data.official_context_validation import validate_official_context

    validation = validate_official_context(
        config_path=args.config,
        data_dir=args.data_dir or None,
        require_metadata=not args.allow_missing_metadata,
        require_official_source=not args.allow_non_official_source,
    )
    passed = bool(validation["ok"] if args.strict_freshness else validation.get("blocking_ok"))
    result = {
        **validation,
        "validation_ok": validation["ok"],
        "ok": passed,
    }
    result["enforcement_mode"] = "strict_freshness" if args.strict_freshness else "blocking_only"
    result["enforcement_ok"] = passed
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif passed and result.get("p1_count", 0):
        print(f"Official context validation passed with P1 refresh findings: {result['data_dir']}")
        for finding in result["findings"]:
            if finding.get("severity") == "P1":
                print(f"[{finding['code']}] {finding['path']}: {finding['message']}")
    elif passed:
        print(f"Official context validation passed: {result['data_dir']}")
    else:
        print(f"Official context validation failed: {result['data_dir']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['path']}: {finding['message']}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
