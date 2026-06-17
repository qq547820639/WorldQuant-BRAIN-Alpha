#!/usr/bin/env python3
"""Validate the local BRAIN capability registry.

This check is offline by design: it only compares canonical settings, Web
configuration schema, and local official-context cache metadata.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check_capability_registry() -> dict[str, Any]:
    from brain_alpha_ops.web_capability_registry import check_capability_registry as _check
    from brain_alpha_ops.web_cloud_snapshot import official_context_file_counts
    from brain_alpha_ops.web_config_schema import public_config_schema

    return _check(
        public_config_schema=public_config_schema,
        official_context_file_counts=official_context_file_counts,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local BRAIN capability registry alignment.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    result = check_capability_registry()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif result["ok"]:
        print("BRAIN capability registry check passed.")
    else:
        print("BRAIN capability registry check failed.")
        for finding in result["findings"]:
            print(f"[{finding['severity']}] {finding['code']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
