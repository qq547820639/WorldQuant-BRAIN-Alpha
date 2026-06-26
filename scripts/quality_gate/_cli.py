"""``main`` CLI entry point for the quality_gate subpackage.

Split from the former ``scripts/quality_gate.py`` monolith (Task A5).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ._constants import DEFAULT_CONFIG, DEFAULT_HTML
from ._orchestrator import run_quality_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local BRAIN Alpha Ops quality gates.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path to validate.")
    parser.add_argument("--html", default=str(DEFAULT_HTML), help="Built Web HTML path to syntax-check.")
    parser.add_argument("--include-all-secrets", action="store_true", help="Scan all text-like files for secrets.")
    parser.add_argument("--include-git-history-secrets", action="store_true", help="Also scan Git history for known leaked secret hashes.")
    parser.add_argument("--dependency-audit", action="store_true", help="Run pip-audit when installed.")
    parser.add_argument("--optional-tooling", action="store_true", help="Report optional ruff/mypy/pip-audit availability without enforcing it.")
    parser.add_argument("--strict-optional-tooling", action="store_true", help="Fail optional tooling check when ruff/mypy/pip-audit are missing.")
    parser.add_argument("--strict-official-context", action="store_true", help="Fail when official fields/operators/datasets metadata is stale.")
    parser.add_argument("--strict-react-build", action="store_true", help="Fail when React build prerequisites are missing.")
    parser.add_argument("--run-react-build", action="store_true", help="Run npm run build after React build prerequisites are available.")
    parser.add_argument("--react-preview-smoke", action="store_true", help="Smoke-test the built React artifact through launch_web.py --frontend react.")
    parser.add_argument("--fail-on-frontend-surface-gaps", action="store_true", help="Fail when inline production views and React mirror tabs have navigation gaps.")
    parser.add_argument("--fail-on-unmapped-frontend-surface-plan", action="store_true", help="Fail when an inline view has no frontend surface parity plan entry.")
    parser.add_argument("--fail-on-unimplemented-frontend-surface-plan", action="store_true", help="Fail when frontend surface parity plan entries are still planned.")
    parser.add_argument("--fail-on-stale-frontend-surface-plan", action="store_true", help="Fail when the frontend surface parity plan references removed inline views.")
    parser.add_argument(
        "--fail-on-runtime-generated-data",
        action="store_true",
        help="Fail when tracked data files match known runtime-generated paths.",
    )
    parser.add_argument(
        "--fail-on-changed-runtime-generated-data",
        action="store_true",
        help="Fail when tracked runtime-generated data files have local changes.",
    )
    parser.add_argument(
        "--fail-on-unresolved-tracked-data-boundary",
        action="store_true",
        help="Fail when tracked runtime-generated data lacks explicit keep/remove decisions.",
    )
    parser.add_argument(
        "--fail-on-stale-tracked-data-boundary",
        action="store_true",
        help="Fail when the tracked data boundary plan references files that are no longer tracked.",
    )
    parser.add_argument("--final-release", action="store_true", help="Run fail-closed final release readiness checks.")
    parser.add_argument("--ruff", action="store_true", help="Run ruff on the incremental static-analysis target set.")
    parser.add_argument("--mypy", action="store_true", help="Run mypy on the incremental static-analysis target set.")
    parser.add_argument("--skip-compile", action="store_true", help="Skip Python compileall syntax checks.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest for a fast preflight.")
    parser.add_argument("--coverage", action="store_true", help="Run pytest with the configured 80%% coverage threshold.")
    parser.add_argument(
        "--require-live-submit-ready",
        action="store_true",
        help="When --final-release is used, fail unless check_live_submit_readiness.py reports an eligible candidate.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Optional pytest args after --.")
    args = parser.parse_args(argv)

    pytest_args = list(args.pytest_args or [])
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    result = run_quality_gate(
        config_path=Path(args.config),
        html_path=Path(args.html),
        include_all_secrets=args.include_all_secrets,
        include_git_history_secrets=args.include_git_history_secrets,
        dependency_audit=args.dependency_audit,
        optional_tooling=args.optional_tooling,
        strict_optional_tooling=args.strict_optional_tooling,
        strict_official_context=args.strict_official_context,
        strict_react_build=args.strict_react_build,
        run_react_build=args.run_react_build,
        react_preview_smoke=args.react_preview_smoke,
        fail_on_frontend_surface_gaps=args.fail_on_frontend_surface_gaps,
        fail_on_unmapped_frontend_surface_plan=args.fail_on_unmapped_frontend_surface_plan,
        fail_on_unimplemented_frontend_surface_plan=args.fail_on_unimplemented_frontend_surface_plan,
        fail_on_stale_frontend_surface_plan=args.fail_on_stale_frontend_surface_plan,
        fail_on_runtime_generated_data=args.fail_on_runtime_generated_data,
        fail_on_changed_runtime_generated_data=args.fail_on_changed_runtime_generated_data,
        fail_on_unresolved_tracked_data_boundary=args.fail_on_unresolved_tracked_data_boundary,
        fail_on_stale_tracked_data_boundary=args.fail_on_stale_tracked_data_boundary,
        final_release=args.final_release,
        require_live_submit_ready=args.require_live_submit_ready,
        ruff=args.ruff,
        mypy=args.mypy,
        skip_compile=args.skip_compile,
        skip_tests=args.skip_tests,
        coverage=args.coverage,
        pytest_args=pytest_args,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for step in result["steps"]:
            status = "PASS" if step["ok"] else "FAIL"
            print(f"[{status}] {step['name']} ({step.get('duration_seconds', 0)}s)")
            if not step["ok"]:
                output = (step.get("stdout") or "") + (step.get("stderr") or "")
                if output.strip():
                    print(output.strip()[-2000:])
        print("Quality gate passed." if result["ok"] else "Quality gate failed.")
    return 0 if result["ok"] else 1
