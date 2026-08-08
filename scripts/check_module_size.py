"""Audit source module size against the current architecture baseline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("brain_alpha_ops", "scripts")
SOURCE_SUFFIXES = {".py", ".js", ".html", ".css", ".tsx", ".ts"}
SKIP_DIRS = {
    ".git",
    ".codex_pydeps",
    ".mypy_cache",
    ".pip_audit_cache",
    ".pytest_cache",
    ".pytest_cache_runtime",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "tests",
}
SKIP_FILES = {
    "brain_alpha_ops/web/index.html",
}
DEFAULT_LINE_LIMIT = 350
FRONTEND_LINE_LIMIT = 400
FRONTEND_SRC_PREFIX = "brain_alpha_ops/web/react_app/src/"
# Grandfathered baseline: previously-held files exceeding the 350-line
# default so the audit can prevent regression while permitting future
# workstreams to split them. Entries reflect the current line counts
# (with a small buffer) so the audit acts as a regression guard rather
# than a hard refactor gate.
BASELINE_LINE_LIMITS: dict[str, int] = {
    "brain_alpha_ops/adaptive_executor.py": 381,
    "brain_alpha_ops/agent_research_tools.py": 557,
    "brain_alpha_ops/candidate_lifecycle.py": 432,
    "brain_alpha_ops/compliance/redline_checks.py": 844,
    "brain_alpha_ops/config_domain_validation.py": 405,
    "brain_alpha_ops/config_parser.py": 368,
    "brain_alpha_ops/config_schema.py": 364,
    "brain_alpha_ops/error_catalog.py": 412,
    "brain_alpha_ops/research/iterative_optimizer/optimizer.py": 358,
    "brain_alpha_ops/research/llm_service/llm_service.py": 358,
    "brain_alpha_ops/research/pipeline/pipeline_mixins.py": 581,
    "brain_alpha_ops/research/pipeline_candidates/pipeline_candidates.py": 384,
    "brain_alpha_ops/research/pipeline_snapshot/pipeline_snapshot.py": 448,
    "brain_alpha_ops/research/repository/repository_mixins.py": 367,
    "brain_alpha_ops/research/scoring/scoring_empirical.py": 356,
    "brain_alpha_ops/runtime_constants.py": 398,
    "brain_alpha_ops/scoring/anti_overfit/checks.py": 737,
    "brain_alpha_ops/scoring/anti_overfit/permutation.py": 370,
    "brain_alpha_ops/scoring/official_scoring/official_scoring.py": 360,
    "brain_alpha_ops/scoring/policy.py": 415,
    "brain_alpha_ops/scoring/release_score_gate/release_score_gate.py": 429,
    "brain_alpha_ops/tasks/_store.py": 362,
    "brain_alpha_ops/types.py": 449,
    "brain_alpha_ops/ux/guided.py": 413,
    "brain_alpha_ops/ux/user_messages.py": 356,
    "brain_alpha_ops/web/dispatch/post_routes/post_routes_candidates.py": 381,
    "brain_alpha_ops/web/dispatch/post_routes/post_routes_jobs.py": 535,
    "brain_alpha_ops/web/misc/web_alpha_lifecycle.py": 608,
    "brain_alpha_ops/web/misc/web_assistant_snapshots.py": 829,
    "brain_alpha_ops/web/misc/web_backtest_slots.py": 541,
    "brain_alpha_ops/web/misc/web_errors.py": 411,
    "brain_alpha_ops/web/misc/web_facade_bindings.py": 409,
    "brain_alpha_ops/web/misc/web_payload_validation.py": 692,
    "brain_alpha_ops/web/misc/web_runtime_facade.py": 875,
    "brain_alpha_ops/web/misc/web_scoring_interpreter.py": 554,
    "brain_alpha_ops/web/misc/web_service_namespace.py": 413,
    "brain_alpha_ops/web/misc/web_snapshot_facade.py": 574,
    "brain_alpha_ops/web/misc/web_sse.py": 434,
    "brain_alpha_ops/web/react_app/src/components/ConfigPanel/ConfigPanelCredentials.tsx": 518,
    "brain_alpha_ops/web/react_app/src/components/ConfigPanel/ConfigPanelSections.tsx": 450,
    "brain_alpha_ops/web/react_app/src/components/ConfigPanel/utils.ts": 491,
    "brain_alpha_ops/web/react_app/src/components/OfficialBacktestSlots.tsx": 407,
    "brain_alpha_ops/web/react_app/src/components/OfficialOperations/OfficialDisplayComponents.tsx": 409,
    "brain_alpha_ops/web/react_app/src/components/OfficialOperations/OfficialSummaryComponents.tsx": 413,
    "brain_alpha_ops/web/react_app/src/components/OfficialOperations/officialSyncProgress.ts": 522,
    "brain_alpha_ops/web/react_app/src/components/OfficialOperations/useOfficialOperations.ts": 413,
    "brain_alpha_ops/web/react_app/src/components/OfficialOperations/useSyncWorkflow.ts": 472,
    "brain_alpha_ops/web/react_app/src/components/ScoringPanel/ScoringPanel.tsx": 407,
    "brain_alpha_ops/web/react_app/src/components/ScoringPanel/ScoringPanelGates.tsx": 491,
    "brain_alpha_ops/web/react_app/src/components/ScoringPanel/ScoringPanelHeader.tsx": 520,
    "brain_alpha_ops/web/react_app/src/components/SnapshotPanel/snapshotViews.ts": 604,
    "brain_alpha_ops/web/react_app/src/helpers/runPayload/index.ts": 448,
    "brain_alpha_ops/web/react_app/src/hooks/useAppState/useAppStateEffects.ts": 506,
    "brain_alpha_ops/web/react_app/src/styles/app.css": 1462,
    "brain_alpha_ops/web/react_app/src/types/allTypes.ts": 1792,
    "brain_alpha_ops/web_cloud/snapshot/snapshot_context.py": 652,
    "scripts/check_frontend_surface_parity.py": 606,
    "scripts/check_live_submit_readiness.py": 973,
    "scripts/check_parameter_traceability/__init__.py": 895,
    "scripts/check_prod_defect_tracking.py": 820,
    "scripts/check_review_gap_closure_tracker.py": 974,
    "scripts/check_review_gap_closure_tracker_helpers.py": 624,
    "scripts/check_tracked_data_inventory.py": 714,
    "scripts/final_release_gate.py": 932,
    "scripts/quality_gate/__init__.py": 868,
    "scripts/scan_sensitive_artifacts.py": 527,
    "scripts/verify_canonical_compliance.py": 606,
}


def check_module_size(
    root: str | Path = ROOT,
    targets: list[str] | None = None,
    *,
    default_limit: int = DEFAULT_LINE_LIMIT,
    baseline_limits: dict[str, int] | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    root_path = Path(root).resolve()
    limits = dict(BASELINE_LINE_LIMITS if baseline_limits is None else baseline_limits)
    files = _iter_source_files(root_path, targets or list(DEFAULT_TARGETS))
    rows = []
    findings = []
    for path in files:
        rel = path.resolve().relative_to(root_path).as_posix()
        line_count = _line_count(path)
        limit = int(limits.get(rel, _line_limit_for(rel, default_limit)))
        row = {"path": rel, "lines": line_count, "limit": limit}
        rows.append(row)
        if line_count > limit:
            findings.append({
                **row,
                "code": "module_line_limit_exceeded",
                "message": f"{rel} has {line_count} lines, above the configured limit of {limit}.",
            })
    hotspots = sorted(rows, key=lambda item: item["lines"], reverse=True)[: max(1, int(top_n or 1))]
    return {
        "ok": not findings,
        "schema_version": "module_size_audit.v1",
        "root": str(root_path),
        "checked": len(rows),
        "default_limit": int(default_limit),
        "baseline_limits": limits,
        "hotspots": hotspots,
        "findings": findings,
    }


def _iter_source_files(root: Path, targets: list[str]) -> list[Path]:
    paths: set[Path] = set()
    for target_name in targets:
        target = (root / target_name).resolve()
        if not target.exists():
            continue
        if target.is_file():
            if _is_source_file(target) and not _is_skipped(target, root):
                paths.add(target)
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            current = Path(dirpath)
            if _is_skipped(current, root):
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                path = current / filename
                if _is_source_file(path) and not _is_skipped(path, root):
                    paths.add(path)
    return sorted(paths)


def _is_source_file(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_SUFFIXES


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return True
    normalized = relative.as_posix()
    if normalized in SKIP_FILES:
        return True
    return any(part in SKIP_DIRS or part.startswith(".codex_tmp_") for part in relative.parts)


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _line_limit_for(rel: str, default_limit: int) -> int:
    """Return the line limit for a source file based on its path.

    Files under brain_alpha_ops/web/react_app/src use the frontend limit (400);
    all other files use the default limit (350).
    """
    if rel.startswith(FRONTEND_SRC_PREFIX):
        return FRONTEND_LINE_LIMIT
    return default_limit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check source module line-count budgets.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--target", action="append", dest="targets", help="File or directory to scan. May be repeated.")
    parser.add_argument("--default-limit", type=int, default=DEFAULT_LINE_LIMIT)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_module_size(
        args.root,
        args.targets,
        default_limit=args.default_limit,
        top_n=args.top_n,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"Module size audit passed: {result['checked']} files checked.")
    else:
        for finding in result["findings"]:
            print(f"{finding['path']}:{finding['lines']} > {finding['limit']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
