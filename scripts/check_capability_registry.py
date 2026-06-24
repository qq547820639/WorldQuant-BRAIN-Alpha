#!/usr/bin/env python3
"""Validate the local BRAIN capability registry.

This check is offline by design: it only compares canonical settings, Web
configuration schema, and local official-context cache metadata.

Extended checks:
  - Bidirectional consistency: registry ↔ code (fields, operators, datasets)
  - Threshold version snapshot for audit trail
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
    from brain_alpha_ops.web_cloud.snapshot import official_context_file_counts
    from brain_alpha_ops.web_config_schema import public_config_schema

    return _check(
        public_config_schema=public_config_schema,
        official_context_file_counts=official_context_file_counts,
    )


def check_registry_consistency() -> dict[str, Any]:
    """Run bidirectional registry consistency validation."""
    from brain_alpha_ops.registry_validation import validate_registry_consistency

    try:
        from brain_alpha_ops.web_capability_registry import build_capability_registry
        registry = build_capability_registry()
    except Exception:
        registry = None

    scoring_ops = {"rank", "ts_mean", "ts_std", "ts_delta", "ts_rank", "ts_min",
                   "ts_max", "ts_sum", "ts_argmin", "ts_argmax", "group_neutralize",
                   "zscore", "quantile", "power", "abs", "log", "sign", "add",
                   "subtract", "multiply", "divide", "max", "min", "delay",
                   "ts_decay_linear", "ts_corr", "ts_cov", "decay_linear",
                   "indneutralize", "winsorize", "normalize", "demean"}

    gate_ops = {"sharpe", "fitness", "turnover_min", "turnover_platform",
                "self_correlation", "prod_correlation", "weight_concentration",
                "sub_universe_sharpe"}

    return validate_registry_consistency(
        registry=registry,
        scoring_operators=scoring_ops,
        gate_operators=gate_ops,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local BRAIN capability registry alignment.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--consistency", action="store_true",
                        help="Run bidirectional registry consistency check.")
    args = parser.parse_args(argv)

    if args.consistency:
        result = check_registry_consistency()
    else:
        result = check_capability_registry()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif result["ok"]:
        if args.consistency:
            print("BRAIN registry consistency check passed.")
        else:
            print("BRAIN capability registry check passed.")
    else:
        if args.consistency:
            print("BRAIN registry consistency check failed.")
        else:
            print("BRAIN capability registry check failed.")
        for finding in result.get("findings", []):
            print(f"[{finding['severity']}] {finding['code']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
