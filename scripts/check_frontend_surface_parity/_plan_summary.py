"""Parity-plan summary and validation helpers.

Split from the former ``scripts/check_frontend_surface_parity.py`` monolith
(Task A10 of deep-optimization-phase12). Loads the optional
``FRONTEND_SURFACE_PARITY_PLAN.json`` document, classifies inline-view
mappings into implemented / planned / retired buckets, validates React-only
tab policy entries, and emits structured findings for unmapped, unimplemented,
stale, or invalid plan rows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._constants import VALID_PLAN_STATUSES, VALID_REACT_ONLY_STATUSES
from ._extractors import _finding


def _plan_summary(
    plan_path: Path | None,
    inline_ids: list[str],
    react_ids: set[str],
    react_only_ids: list[str],
    findings: list[dict[str, Any]],
    *,
    fail_on_unmapped_plan: bool,
    fail_on_unimplemented_plan: bool,
    fail_on_stale_plan: bool,
) -> dict[str, Any]:
    if plan_path is None:
        return _empty_plan_summary()
    path = Path(plan_path).resolve()
    if not path.exists():
        if fail_on_unmapped_plan or fail_on_unimplemented_plan:
            findings.append(_finding("missing_parity_plan", str(path), "Frontend parity plan file does not exist."))
        return {**_empty_plan_summary(), "path": str(path)}
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(_finding("invalid_parity_plan", str(path), str(exc)))
        return {**_empty_plan_summary(), "path": str(path), "present": True}

    mappings = plan.get("inline_view_mappings")
    if not isinstance(mappings, dict):
        findings.append(_finding("invalid_parity_plan", str(path), "inline_view_mappings must be an object."))
        mappings = {}
    react_only_policy = plan.get("react_only_tab_policy") or {}
    if not isinstance(react_only_policy, dict):
        findings.append(_finding("invalid_parity_plan", str(path), "react_only_tab_policy must be an object when present."))
        react_only_policy = {}

    mapped_ids: list[str] = []
    implemented: list[str] = []
    planned: list[str] = []
    retired: list[str] = []
    invalid_entries: list[dict[str, str]] = []
    for view_id in inline_ids:
        entry = mappings.get(view_id)
        if not isinstance(entry, dict):
            continue
        mapped_ids.append(view_id)
        status = str(entry.get("status", ""))
        target = str(entry.get("react_target", ""))
        invalid_reason = _plan_entry_error(status, target, react_ids)
        if invalid_reason:
            invalid_entries.append({"id": view_id, "reason": invalid_reason})
            continue
        if status == "implemented":
            implemented.append(view_id)
        elif status == "planned":
            planned.append(view_id)
        elif status == "retired":
            retired.append(view_id)

    accepted_react_only, invalid_react_only_entries = _react_only_policy_summary(
        react_only_policy,
        inline_ids=set(inline_ids),
        react_ids=react_ids,
        react_only_ids=react_only_ids,
    )
    unmapped = [view_id for view_id in inline_ids if view_id not in set(mapped_ids)]
    stale_mappings = sorted(view_id for view_id in mappings if view_id not in set(inline_ids))
    if invalid_entries:
        findings.append(
            {
                "code": "invalid_parity_plan_entries",
                "path": str(path),
                "message": "Frontend parity plan has invalid entries.",
                "entries": invalid_entries,
            }
        )
    if invalid_react_only_entries:
        findings.append(
            {
                "code": "invalid_react_only_tab_policy_entries",
                "path": str(path),
                "message": "Frontend parity plan has invalid React-only tab policy entries.",
                "entries": invalid_react_only_entries,
            }
        )
    if fail_on_unmapped_plan and unmapped:
        findings.append(
            {
                "code": "frontend_surface_unmapped_views",
                "path": str(path),
                "message": "Inline views are missing from the frontend parity plan.",
                "unmapped_inline_views": unmapped,
            }
        )
    if fail_on_unimplemented_plan and planned:
        findings.append(
            {
                "code": "frontend_surface_unimplemented_views",
                "path": str(path),
                "message": "Inline views are still planned rather than implemented or retired.",
                "planned_inline_views": planned,
            }
        )
    if fail_on_stale_plan and stale_mappings:
        findings.append(
            {
                "code": "frontend_surface_stale_plan_entries",
                "path": str(path),
                "message": "Frontend parity plan references inline views that no longer exist.",
                "stale_inline_view_mappings": stale_mappings,
            }
        )
    return {
        "path": str(path),
        "present": True,
        "schema_version": str(plan.get("schema_version", "")),
        "mapped_inline_views": mapped_ids,
        "unmapped_inline_views": unmapped,
        "stale_inline_view_mappings": stale_mappings,
        "implemented_inline_views": implemented,
        "planned_inline_views": planned,
        "retired_inline_views": retired,
        "invalid_entries": invalid_entries,
        "accepted_react_only_tabs": accepted_react_only,
        "unaccepted_react_only_tabs": [tab_id for tab_id in react_only_ids if tab_id not in set(accepted_react_only)],
        "invalid_react_only_entries": invalid_react_only_entries,
    }


def _empty_plan_summary() -> dict[str, Any]:
    return {
        "path": "",
        "present": False,
        "schema_version": "",
        "mapped_inline_views": [],
        "unmapped_inline_views": [],
        "stale_inline_view_mappings": [],
        "implemented_inline_views": [],
        "planned_inline_views": [],
        "retired_inline_views": [],
        "invalid_entries": [],
        "accepted_react_only_tabs": [],
        "unaccepted_react_only_tabs": [],
        "invalid_react_only_entries": [],
    }


def _retired_inline_plan_summary(plan_path: Path | None, react_only_ids: list[str]) -> dict[str, Any]:
    path = str(Path(plan_path).resolve()) if plan_path is not None else ""
    return {
        **_empty_plan_summary(),
        "path": path,
        "present": bool(plan_path and Path(plan_path).exists()),
        "schema_version": "frontend_surface_parity_plan.retired_inline",
        "accepted_react_only_tabs": list(react_only_ids),
    }


def _plan_entry_error(status: str, target: str, react_ids: set[str]) -> str:
    if status not in VALID_PLAN_STATUSES:
        return f"status must be one of {sorted(VALID_PLAN_STATUSES)}"
    if not target:
        return "react_target is required"
    if status == "implemented" and target not in react_ids:
        return "implemented entries must target an existing React tab id"
    if status == "planned" and target not in react_ids and not target.startswith("future:"):
        return "planned entries must target an existing React tab id or future:<id>"
    return ""


def _react_only_policy_summary(
    policy: dict[str, Any],
    *,
    inline_ids: set[str],
    react_ids: set[str],
    react_only_ids: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    accepted = []
    invalid_entries: list[dict[str, str]] = []
    accepted_set = set()
    for tab_id, entry in policy.items():
        if not isinstance(entry, dict):
            invalid_entries.append({"id": str(tab_id), "reason": "entry must be an object"})
            continue
        status = str(entry.get("status", ""))
        reason = _react_only_entry_error(str(tab_id), status, inline_ids, react_ids)
        if reason:
            invalid_entries.append({"id": str(tab_id), "reason": reason})
            continue
        accepted_set.add(str(tab_id))
    for tab_id in react_only_ids:
        if tab_id in accepted_set:
            accepted.append(tab_id)
    return accepted, invalid_entries


def _react_only_entry_error(tab_id: str, status: str, inline_ids: set[str], react_ids: set[str]) -> str:
    if status not in VALID_REACT_ONLY_STATUSES:
        return f"status must be one of {sorted(VALID_REACT_ONLY_STATUSES)}"
    if tab_id not in react_ids:
        return "accepted React-only entries must target an existing React tab id"
    if tab_id in inline_ids:
        return "accepted React-only entries must not duplicate an inline view id"
    return ""
