"""Audit source module size against the current architecture baseline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("brain_alpha_ops", "scripts")
SOURCE_SUFFIXES = {".py", ".js", ".html"}
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
}
SKIP_FILES = {
    "brain_alpha_ops/web/index.html",
}
DEFAULT_LINE_LIMIT = 350
# Grandfathered baseline: files currently exceeding the 350-line default are
# recorded with their ACTUAL line counts so the audit prevents regression
# (any growth beyond the recorded count fails) while permitting future
# workstreams to split them and remove the entry. Entries for files that no
# longer exist (split into subpackages in prior phases) have been removed.
BASELINE_LINE_LIMITS = {
    "brain_alpha_ops/browser/brain_ui_runner.py": 381,
    "brain_alpha_ops/config_domain_validation.py": 371,
    "brain_alpha_ops/config_schema.py": 374,
    "brain_alpha_ops/research/_observability_helpers.py": 372,
    "brain_alpha_ops/research/generator/_helpers.py": 355,
    "brain_alpha_ops/research/market_data_cache.py": 354,
    "brain_alpha_ops/research/runtime_service.py": 355,
    "brain_alpha_ops/research/theme_engine/_engine.py": 363,
    "brain_alpha_ops/runtime_constants.py": 382,
    "brain_alpha_ops/types.py": 380,
    "brain_alpha_ops/ux/user_messages.py": 351,
    "brain_alpha_ops/web/business/web_async_jobs.py": 364,
    "brain_alpha_ops/web/business/web_jobs.py": 352,
    "brain_alpha_ops/web/handlers/phase.py": 375,
    "brain_alpha_ops/web/security/web_security.py": 362,
    "scripts/check_defect_analysis_report.py": 378,
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
        limit = int(limits.get(rel, default_limit))
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
