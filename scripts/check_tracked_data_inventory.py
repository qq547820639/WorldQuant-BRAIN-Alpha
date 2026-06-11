"""Inventory tracked data files so runtime artifacts stay visible.

This script is read-only. It reports tracked files under ``data/`` and
classifies them so callers can separate intentional snapshots from runtime
artifacts that still need a human boundary decision.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOUNDARY_PLAN = ROOT / "docs" / "TRACKED_DATA_BOUNDARY_PLAN.json"
BOUNDARY_STATUSES = {"keep", "remove", "pending_decision"}

RUNTIME_GENERATED_PREFIXES = (
    "data/_codex_bench",
    "data/api_cache/",
    "data/checkpoints/",
    "data/e2e_screenshots/",
    "data/jobs_",
    "data/run_history/",
)
SNAPSHOT_PREFIXES = ("data/official_",)
QUALIFICATION_SNAPSHOT_PATHS = {"data/qualified_alpha_summary.json"}
REVIEW_ARTIFACT_PREFIXES = ("data/prd_", "data/qa_", "data/audit/")
REFERENCE_EXCLUDED_PREFIXES = ("data/", "tests/")
REFERENCE_EXCLUDED_PATHS = {
    ".gitignore",
    "docs/REVIEW_GAP_CLOSURE_20260530.md",
    "docs/TRACKED_DATA_BOUNDARY_PLAN.json",
    "scripts/check_tracked_data_inventory.py",
}


def inventory_tracked_data(
    root: Path = ROOT,
    *,
    fail_on_runtime_generated: bool = False,
    fail_on_changed_runtime_generated: bool = False,
    boundary_plan_path: Path | None = None,
    fail_on_unresolved_boundary: bool = False,
    fail_on_stale_boundary: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    tracked = _tracked_data_files(root)
    tracked_set = set(tracked)
    changed = [rel_path for rel_path in _changed_tracked_data_files(root) if rel_path in tracked_set]
    categories: dict[str, list[str]] = defaultdict(list)
    changed_categories: dict[str, list[str]] = defaultdict(list)
    findings: list[dict[str, Any]] = []
    for rel_path in changed:
        changed_categories[_classify(rel_path)].append(rel_path)
    changed_runtime_generated = sorted(changed_categories.get("runtime_generated", []))
    for rel_path in tracked:
        category = _classify(rel_path)
        categories[category].append(rel_path)
        if category == "unclassified":
            findings.append(
                {
                    "code": "unclassified_tracked_data",
                    "path": rel_path,
                    "message": f"Tracked data file does not match a known category: {rel_path}",
                }
            )
    runtime_generated = sorted(categories.get("runtime_generated", []))
    runtime_generated_references = _runtime_generated_references(root, runtime_generated)
    boundary_plan = _boundary_plan_summary(
        boundary_plan_path,
        runtime_generated,
        changed_runtime_generated,
        runtime_generated_references,
        findings,
        fail_on_unresolved_boundary=fail_on_unresolved_boundary,
        fail_on_stale_boundary=fail_on_stale_boundary,
    )
    if fail_on_changed_runtime_generated:
        changed_failures = (
            boundary_plan.get("recommendations", {}).get("changed_recommended_remove_files")
            if boundary_plan.get("present")
            else changed_runtime_generated
        )
        for rel_path in sorted(changed_failures or []):
            findings.append(
                {
                    "code": "changed_runtime_generated_data",
                    "path": rel_path,
                    "message": f"Runtime-generated data file has local tracked changes: {rel_path}",
                }
            )
    if fail_on_runtime_generated:
        runtime_failures = (
            boundary_plan.get("recommendations", {}).get("recommended_remove_files")
            if boundary_plan.get("present")
            else runtime_generated
        )
        for rel_path in sorted(runtime_failures or []):
            findings.append(
                {
                    "code": "tracked_runtime_generated_data",
                    "path": rel_path,
                    "message": f"Runtime-generated data file is still tracked: {rel_path}",
                }
            )
    return {
        "ok": not findings,
        "schema_version": "tracked_data_inventory.v1",
        "root": str(root),
        "tracked_count": len(tracked),
        "changed_count": len(changed),
        "categories": {name: sorted(paths) for name, paths in sorted(categories.items())},
        "changed_categories": {name: sorted(paths) for name, paths in sorted(changed_categories.items())},
        "changed_tracked_data_files": changed,
        "changed_runtime_generated_files": changed_runtime_generated,
        "runtime_generated_references": runtime_generated_references,
        "boundary_plan": boundary_plan,
        "findings": findings,
    }


def _tracked_data_files(root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "data"],
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _changed_tracked_data_files(root: Path) -> list[str]:
    changed: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "--", "data"],
        ["git", "diff", "--cached", "--name-only", "--", "data"],
    ):
        proc = subprocess.run(
            args,
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            rel_path = line.strip().replace("\\", "/")
            if rel_path:
                changed.add(rel_path)
    return sorted(changed)


def _classify(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith(RUNTIME_GENERATED_PREFIXES):
        return "runtime_generated"
    if normalized.startswith(SNAPSHOT_PREFIXES):
        return "official_snapshot"
    if normalized in QUALIFICATION_SNAPSHOT_PATHS:
        return "qualification_snapshot"
    if normalized.startswith(REVIEW_ARTIFACT_PREFIXES):
        return "review_artifact"
    return "unclassified"


def _runtime_generated_references(root: Path, runtime_generated: list[str]) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    for rel_path in runtime_generated:
        proc = subprocess.run(
            ["git", "grep", "-n", "-F", "--", rel_path],
            cwd=str(root),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if proc.returncode not in (0, 1):
            continue
        matches: set[str] = set()
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            ref_path = line.split(":", 1)[0].strip().replace("\\", "/")
            if _is_reference_excluded(ref_path):
                continue
            matches.add(line.strip())
        if matches:
            references[rel_path] = sorted(matches)
    return references


def _is_reference_excluded(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in REFERENCE_EXCLUDED_PATHS:
        return True
    return normalized.startswith(REFERENCE_EXCLUDED_PREFIXES)


def _boundary_plan_summary(
    plan_path: Path | None,
    runtime_generated: list[str],
    changed_runtime_generated: list[str],
    runtime_generated_references: dict[str, list[str]],
    findings: list[dict[str, Any]],
    *,
    fail_on_unresolved_boundary: bool,
    fail_on_stale_boundary: bool,
) -> dict[str, Any]:
    if plan_path is None:
        return _empty_boundary_plan()
    path = Path(plan_path).resolve()
    if not path.exists():
        if fail_on_unresolved_boundary and runtime_generated:
            findings.append(
                {
                    "code": "missing_tracked_data_boundary_plan",
                    "path": str(path),
                    "message": "Tracked runtime-generated data needs a boundary plan before strict cleanup enforcement.",
                }
            )
        return {**_empty_boundary_plan(), "path": str(path)}
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            {
                "code": "invalid_tracked_data_boundary_plan",
                "path": str(path),
                "message": str(exc),
            }
        )
        return {**_empty_boundary_plan(), "path": str(path), "present": True}

    entries = plan.get("tracked_runtime_generated_data")
    if not isinstance(entries, dict):
        findings.append(
            {
                "code": "invalid_tracked_data_boundary_plan",
                "path": str(path),
                "message": "tracked_runtime_generated_data must be an object.",
            }
        )
        entries = {}

    keep_files: list[str] = []
    remove_files: list[str] = []
    pending_files: list[str] = []
    missing_files: list[str] = []
    invalid_entries: list[dict[str, str]] = []
    runtime_set = set(runtime_generated)
    for rel_path in runtime_generated:
        entry = entries.get(rel_path)
        if not isinstance(entry, dict):
            missing_files.append(rel_path)
            continue
        status = str(entry.get("status", ""))
        if status not in BOUNDARY_STATUSES:
            invalid_entries.append({"path": rel_path, "reason": f"status must be one of {sorted(BOUNDARY_STATUSES)}"})
            continue
        if status == "keep":
            keep_files.append(rel_path)
        elif status == "remove":
            remove_files.append(rel_path)
        else:
            pending_files.append(rel_path)

    stale_entries = sorted(path for path in entries if path not in runtime_set)
    if invalid_entries:
        findings.append(
            {
                "code": "invalid_tracked_data_boundary_entries",
                "path": str(path),
                "message": "Tracked data boundary plan has invalid entries.",
                "entries": invalid_entries,
            }
        )
    unresolved = sorted(pending_files + missing_files)
    recommendations = _boundary_recommendations(
        runtime_generated,
        changed_runtime_generated,
        runtime_generated_references,
        keep_files,
        remove_files,
    )
    if fail_on_unresolved_boundary and unresolved:
        findings.append(
            {
                "code": "tracked_data_boundary_unresolved",
                "path": str(path),
                "message": "Tracked runtime-generated data has pending or missing keep/remove decisions.",
                "pending_decision_files": sorted(pending_files),
                "missing_decision_files": sorted(missing_files),
            }
        )
    if fail_on_stale_boundary and stale_entries:
        findings.append(
            {
                "code": "tracked_data_boundary_stale_entries",
                "path": str(path),
                "message": "Tracked data boundary plan references files that are no longer tracked runtime-generated data.",
                "stale_entries": stale_entries,
            }
        )
    decision_todo = _boundary_decision_todo(
        unresolved,
        recommendations["recommended_remove_files"],
        recommendations["changed_recommended_remove_files"],
    )
    return {
        "path": str(path),
        "present": True,
        "schema_version": str(plan.get("schema_version", "")),
        "entry_count": len(entries),
        "keep_files": sorted(keep_files),
        "remove_files": sorted(remove_files),
        "pending_decision_files": sorted(pending_files),
        "missing_decision_files": sorted(missing_files),
        "stale_entries": stale_entries,
        "invalid_entries": invalid_entries,
        "unresolved_count": len(unresolved),
        "recommendations": recommendations,
        "decision_todo": decision_todo,
    }


def _boundary_recommendations(
    runtime_generated: list[str],
    changed_runtime_generated: list[str],
    runtime_generated_references: dict[str, list[str]],
    keep_files: list[str],
    remove_files: list[str],
) -> dict[str, Any]:
    runtime_files = sorted(runtime_generated)
    keep_set = set(keep_files)
    remove_set = set(remove_files)
    referenced_files = sorted(path for path in runtime_files if runtime_generated_references.get(path))
    cleanup_files = sorted(
        remove_set.union(
            path for path in runtime_files if path not in runtime_generated_references and path not in keep_set
        )
    )
    changed_files = sorted(set(changed_runtime_generated).intersection(cleanup_files))
    return {
        "recommended_remove_files": cleanup_files,
        "changed_recommended_remove_files": changed_files,
        "referenced_runtime_generated_files": referenced_files,
        "recommended_remove_count": len(cleanup_files),
        "changed_recommended_remove_count": len(changed_files),
        "referenced_runtime_generated_count": len(referenced_files),
        "rationale": (
            "These paths match runtime-generated data patterns. Explicit remove decisions are cleanup "
            "candidates even when a file is referenced. Unreferenced files remain recommended cleanup "
            "candidates unless the boundary plan marks them keep."
        ),
    }


def _boundary_decision_todo(
    unresolved_files: list[str],
    recommended_remove_files: list[str],
    changed_recommended_remove_files: list[str],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    unresolved = sorted(unresolved_files)
    changed_recommended = sorted(changed_recommended_remove_files)
    recommended_remove = sorted(recommended_remove_files)
    if unresolved:
        tasks.append(
            {
                "id": "decide_runtime_generated_boundary",
                "description": "Choose keep or remove for tracked runtime-generated data files.",
                "strict_gate": "--fail-on-unresolved-boundary",
                "count": len(unresolved),
                "files": unresolved,
            }
        )
    if changed_recommended:
        tasks.append(
            {
                "id": "resolve_changed_runtime_generated_data",
                "description": "Remove/untrack or intentionally keep changed runtime-generated data before enabling the changed-data strict gate.",
                "strict_gate": "--fail-on-changed-runtime-generated",
                "count": len(changed_recommended),
                "files": changed_recommended,
            }
        )
    if recommended_remove:
        tasks.append(
            {
                "id": "cleanup_recommended_runtime_generated_data",
                "description": "Remove or untrack runtime-generated data after the human boundary decision allows cleanup.",
                "strict_gate": "--fail-on-runtime-generated",
                "count": len(recommended_remove),
                "files": recommended_remove,
            }
        )
    return tasks


def _empty_boundary_plan() -> dict[str, Any]:
    return {
        "path": "",
        "present": False,
        "schema_version": "",
        "entry_count": 0,
        "keep_files": [],
        "remove_files": [],
        "pending_decision_files": [],
        "missing_decision_files": [],
        "stale_entries": [],
        "invalid_entries": [],
        "unresolved_count": 0,
        "recommendations": {
            "recommended_remove_files": [],
            "changed_recommended_remove_files": [],
            "referenced_runtime_generated_files": [],
            "recommended_remove_count": 0,
            "changed_recommended_remove_count": 0,
            "referenced_runtime_generated_count": 0,
            "rationale": "",
        },
        "decision_todo": [],
    }


def _count_summary(items: dict[str, list[str]]) -> str:
    return ", ".join(f"{name}={len(paths)}" for name, paths in sorted(items.items())) or "none"


def _human_summary_lines(result: dict[str, Any], *, show_files: bool = False) -> list[str]:
    status = "passed" if result["ok"] else "failed"
    lines = [
        f"Tracked data inventory {status}: {result['tracked_count']} files classified.",
        f"Categories: {_count_summary(result.get('categories', {}))}.",
        f"Changed tracked data files: {result['changed_count']}.",
    ]
    changed_categories = result.get("changed_categories", {})
    if changed_categories:
        lines.append(f"Changed categories: {_count_summary(changed_categories)}.")

    boundary = result.get("boundary_plan", {})
    if boundary.get("present"):
        lines.append(
            "Boundary plan: "
            f"{boundary.get('unresolved_count', 0)} unresolved, "
            f"{len(boundary.get('pending_decision_files', []))} pending, "
            f"{len(boundary.get('missing_decision_files', []))} missing, "
            f"{len(boundary.get('stale_entries', []))} stale, "
            f"{len(boundary.get('keep_files', []))} keep, "
            f"{len(boundary.get('remove_files', []))} remove."
        )
        recommendations = boundary.get("recommendations", {})
        if recommendations:
            lines.append(
                "Cleanup candidates: "
                f"{recommendations.get('recommended_remove_count', 0)} recommended, "
                f"{recommendations.get('changed_recommended_remove_count', 0)} changed, "
                f"{recommendations.get('referenced_runtime_generated_count', 0)} referenced."
            )
        decision_todo = boundary.get("decision_todo", [])
        if decision_todo:
            lines.append("Decision todo:")
            for task in decision_todo:
                lines.append(
                    f"- {task.get('id', 'unknown')}: "
                    f"{task.get('count', 0)} files via {task.get('strict_gate', 'n/a')}"
                )
        if show_files:
            runtime_files = result.get("categories", {}).get("runtime_generated", [])
            changed_files = set(result.get("changed_runtime_generated_files", []))
            referenced_files = set(result.get("runtime_generated_references", {}))
            keep_files = set(boundary.get("keep_files", []))
            remove_files = set(boundary.get("remove_files", []))
            pending_files = set(boundary.get("pending_decision_files", []))
            missing_files = set(boundary.get("missing_decision_files", []))
            lines.append("Runtime-generated files:")
            for rel_path in runtime_files:
                status_tags = []
                if rel_path in keep_files:
                    status_tags.append("keep")
                elif rel_path in remove_files:
                    status_tags.append("remove")
                elif rel_path in pending_files:
                    status_tags.append("pending")
                elif rel_path in missing_files:
                    status_tags.append("missing")
                else:
                    status_tags.append("unclassified")
                if rel_path in changed_files:
                    status_tags.append("changed")
                if rel_path in referenced_files:
                    status_tags.append("referenced")
                lines.append(f"- [{','.join(status_tags)}] {rel_path}")
    elif boundary.get("path"):
        lines.append(f"Boundary plan missing: {boundary['path']}.")

    findings = result.get("findings", [])
    if findings:
        lines.append("Findings:")
        for finding in findings:
            lines.append(f"- {finding.get('code', 'unknown')}: {finding.get('path', '')}")
    return lines


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


if __name__ == "__main__":
    raise SystemExit(main())
