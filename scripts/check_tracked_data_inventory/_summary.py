"""Plain-text summary rendering for tracked-data inventory results.

Split from the former ``scripts/check_tracked_data_inventory.py`` monolith
(Task A7 of deep-optimization-phase12). Formats the structured
``inventory_tracked_data`` result dict into human-readable lines for the
non-JSON CLI output, including category counts, boundary-plan status,
cleanup candidates, decision-todo items, runtime-generated file tags, and
finding headers.
"""

from __future__ import annotations

from typing import Any


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
