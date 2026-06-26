"""Top-level tracked-data inventory orchestrator.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Enumerates tracked data files via
the git helpers, classifies them, computes the changed-file subset, builds
the runtime-generated reference map, drives the boundary-plan summary, and
emits findings for the strict-gate CLI flags.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ._boundary import _boundary_plan_summary
from ._classify import _classify
from ._git import (
    _changed_tracked_data_files,
    _runtime_generated_references,
    _tracked_data_files,
)


def inventory_tracked_data(
    root: Path,
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
