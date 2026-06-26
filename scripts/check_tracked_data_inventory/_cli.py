"""CLI entry point for the tracked-data inventory check.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Parses ``argparse`` flags and
renders the JSON or human-readable result. The thin
``scripts/check_tracked_data_inventory.py`` shim imports ``main`` from this
module via the package ``__init__``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._constants import DEFAULT_BOUNDARY_PLAN, ROOT
from ._core import inventory_tracked_data
from ._summary import _human_summary_lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory tracked files under data/.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument(
        "--fail-on-runtime-generated",
        action="store_true",
        help="Fail when known runtime-generated data files are tracked.",
    )
    parser.add_argument(
        "--fail-on-changed-runtime-generated",
        action="store_true",
        help="Fail when tracked runtime-generated data has local changes.",
    )
    parser.add_argument(
        "--boundary-plan",
        default=str(DEFAULT_BOUNDARY_PLAN),
        help="JSON plan recording keep/remove decisions for tracked runtime-generated data.",
    )
    parser.add_argument(
        "--fail-on-unresolved-boundary",
        action="store_true",
        help="Fail when tracked runtime-generated data lacks a keep/remove decision.",
    )
    parser.add_argument(
        "--fail-on-stale-boundary",
        action="store_true",
        help="Fail when the boundary plan references runtime-generated files that are no longer tracked.",
    )
    parser.add_argument(
        "--show-files",
        action="store_true",
        help="Print tracked runtime-generated file names in the plain-text summary.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = inventory_tracked_data(
        Path(args.root),
        fail_on_runtime_generated=args.fail_on_runtime_generated,
        fail_on_changed_runtime_generated=args.fail_on_changed_runtime_generated,
        boundary_plan_path=Path(args.boundary_plan) if args.boundary_plan else None,
        fail_on_unresolved_boundary=args.fail_on_unresolved_boundary,
        fail_on_stale_boundary=args.fail_on_stale_boundary,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join(_human_summary_lines(result, show_files=args.show_files)))
    return 0 if result["ok"] else 1
