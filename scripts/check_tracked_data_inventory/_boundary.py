"""Boundary-plan summary and recommendation logic.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Loads the tracked-data boundary
plan JSON, validates its entries against the runtime-generated file set,
emits findings for missing/stale/invalid decisions, and computes cleanup
recommendations plus a decision-todo list used by the CLI strict gates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._constants import BOUNDARY_STATUSES


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
