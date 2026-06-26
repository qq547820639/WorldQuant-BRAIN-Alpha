"""CLI entry point for the frontend surface parity audit.

Split from the former ``scripts/check_frontend_surface_parity.py`` monolith
(Task A10 of deep-optimization-phase12). Parses ``argparse`` flags and renders
the JSON or human-readable result. The thin
``scripts/check_frontend_surface_parity.py`` shim imports ``main`` from this
module via the package ``__init__``.

``main`` resolves ``check_frontend_surface_parity`` through the package
namespace at call time so that tests which monkeypatch
``scripts.check_frontend_surface_parity.check_frontend_surface_parity`` are
honored (mirroring the original monolith where ``main`` and the audit
function shared the same module globals).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ._constants import (  # noqa: E402
    DEFAULT_INLINE_REGISTRY,
    DEFAULT_PARITY_PLAN,
    DEFAULT_REACT_APP,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit inline and React frontend navigation surface parity.")
    parser.add_argument("--inline-registry", default=str(DEFAULT_INLINE_REGISTRY))
    parser.add_argument("--react-app", default=str(DEFAULT_REACT_APP))
    parser.add_argument("--plan", default=str(DEFAULT_PARITY_PLAN), help="JSON plan mapping inline views to React targets.")
    parser.add_argument("--fail-on-gaps", action="store_true", help="Exit non-zero when the two surfaces expose different navigation ids.")
    parser.add_argument("--fail-on-unmapped-plan", action="store_true", help="Exit non-zero when an inline view has no parity-plan entry.")
    parser.add_argument("--fail-on-unimplemented-plan", action="store_true", help="Exit non-zero when parity-plan entries are still planned.")
    parser.add_argument("--fail-on-stale-plan", action="store_true", help="Exit non-zero when the parity plan references removed inline views.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    # Resolve the audit function through the package namespace so that tests
    # which monkeypatch ``check_frontend_surface_parity`` on the package keep
    # working after the monolith split.
    from scripts.check_frontend_surface_parity import check_frontend_surface_parity  # noqa: E402

    result = check_frontend_surface_parity(
        Path(args.inline_registry),
        Path(args.react_app),
        plan_path=Path(args.plan) if args.plan else None,
        fail_on_gaps=args.fail_on_gaps,
        fail_on_unmapped_plan=args.fail_on_unmapped_plan,
        fail_on_unimplemented_plan=args.fail_on_unimplemented_plan,
        fail_on_stale_plan=args.fail_on_stale_plan,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        parity = result["parity"]
        status = "matches" if parity["matches"] else ("strict matches" if parity.get("strict_matches") else "has gaps")
        print(f"frontend surface parity {status}: {result['inline_view_count']} inline views, {result['react_tab_count']} React tabs")
    else:
        print("frontend surface parity check failed", file=sys.stderr)
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['message']}", file=sys.stderr)
    return 0 if result["ok"] else 1
