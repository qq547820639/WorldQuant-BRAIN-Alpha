"""Top-level surface-parity audit orchestrator.

Split from the former ``scripts/check_frontend_surface_parity.py`` monolith
(Task A10 of deep-optimization-phase12). Coordinates inline-view and
React-tab extraction, classifies the parity gap, applies the optional
parity-plan summary, and emits the ``frontend_surface_parity.v1`` result
document consumed by the CLI and quality-gate callers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._constants import DEFAULT_INLINE_REGISTRY, DEFAULT_REACT_APP
from ._extractors import (
    _extract_sidebar_nav_items,
    _finding,
    _read_text,
    extract_inline_views,
    extract_react_tabs,
)
from ._plan_summary import _plan_summary, _retired_inline_plan_summary


def check_frontend_surface_parity(
    inline_registry: Path = DEFAULT_INLINE_REGISTRY,
    react_app: Path = DEFAULT_REACT_APP,
    *,
    plan_path: Path | None = None,
    fail_on_gaps: bool = False,
    fail_on_unmapped_plan: bool = False,
    fail_on_unimplemented_plan: bool = False,
    fail_on_stale_plan: bool = False,
) -> dict[str, Any]:
    inline_registry = inline_registry.resolve()
    react_app = react_app.resolve()
    findings: list[dict[str, Any]] = []

    inline_source = _read_text(inline_registry, findings, required=False)
    react_source = _read_text(react_app, findings)
    inline_views = extract_inline_views(inline_source) if inline_source else []
    react_tabs = extract_react_tabs(react_source) if react_source else []

    # Fallback: Terminal Precision v2.0 uses Sidebar.tsx NAV_ITEMS for navigation
    if react_source and not react_tabs:
        sidebar_path = react_app.parent / "components" / "Sidebar.tsx"
        if sidebar_path.exists():
            try:
                sidebar_source = sidebar_path.read_text(encoding="utf-8")
                react_tabs = _extract_sidebar_nav_items(sidebar_source)
            except OSError:
                pass  # Sidebar file unreadable — best-effort extraction, failures are non-fatal

    inline_retired = not inline_source and react_source and inline_registry == DEFAULT_INLINE_REGISTRY.resolve()

    if inline_source and not inline_views:
        findings.append(_finding("missing_inline_views", str(inline_registry), "No inline VIEW_ORDER entries were detected."))
    if react_source and not react_tabs:
        findings.append(_finding("missing_react_tabs", str(react_app), "No React TABS entries were detected."))

    inline_ids = [item["id"] for item in inline_views]
    react_ids = [item["id"] for item in react_tabs]
    inline_id_set = set(inline_ids)
    react_id_set = set(react_ids)
    inline_only = [view_id for view_id in inline_ids if view_id not in react_id_set]
    react_only = [tab_id for tab_id in react_ids if tab_id not in inline_id_set]
    shared = [view_id for view_id in inline_ids if view_id in react_id_set]
    if inline_retired:
        plan = _retired_inline_plan_summary(plan_path, react_only)
    else:
        plan = _plan_summary(
            plan_path,
            inline_ids,
            react_id_set,
            react_only,
            findings,
            fail_on_unmapped_plan=fail_on_unmapped_plan,
            fail_on_unimplemented_plan=fail_on_unimplemented_plan,
            fail_on_stale_plan=fail_on_stale_plan,
        )
    accepted_react_only = plan["accepted_react_only_tabs"]
    unaccepted_react_only = [tab_id for tab_id in react_only if tab_id not in set(accepted_react_only)]
    parity_matches = bool(inline_views and react_tabs and not inline_only and not react_only)
    strict_matches = (
        bool(inline_views and react_tabs and not inline_only and not unaccepted_react_only)
        or bool(inline_retired and react_tabs)
    )

    if fail_on_gaps and inline_views and react_tabs and not strict_matches:
        findings.append(
            {
                "code": "frontend_surface_mismatch",
                "path": f"{inline_registry}::{react_app}",
                "message": "Inline production views and React mirror tabs have unimplemented or unaccepted navigation gaps.",
                "inline_only_views": inline_only,
                "react_only_tabs": unaccepted_react_only,
            }
        )

    return {
        "ok": not findings,
        "schema_version": "frontend_surface_parity.v1",
        "inline_registry": str(inline_registry),
        "react_app": str(react_app),
        "fail_on_gaps": bool(fail_on_gaps),
        "inline_surface_retired": bool(inline_retired),
        "inline_view_count": len(inline_views),
        "react_tab_count": len(react_tabs),
        "plan": plan,
        "parity": {
            "matches": parity_matches,
            "strict_matches": strict_matches,
            "shared_ids": shared,
            "inline_only_views": inline_only,
            "react_only_tabs": react_only,
            "accepted_react_only_tabs": accepted_react_only,
            "unaccepted_react_only_tabs": unaccepted_react_only,
        },
        "inline_views": inline_views,
        "react_tabs": react_tabs,
        "findings": findings,
    }
