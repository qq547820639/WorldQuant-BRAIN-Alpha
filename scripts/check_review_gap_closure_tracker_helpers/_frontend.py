"""Frontend surface decisions for the review gap closure tracker."""

from __future__ import annotations

from typing import Any


def frontend_mirror_only_decision(status_matrix: list[dict[str, str]]) -> bool:
    row = next((item for item in status_matrix if item.get("gap") == "P3-1 Dual frontend unification"), {})
    evidence = f"{row.get('current_evidence', '')} {row.get('remaining_evidence_needed', '')}"
    return (
        row.get("status") == "CLOSED_CURRENT"
        and "mirror-only" in evidence
        and "current release" in evidence
        and "frontend_surface_parity" in evidence
    )


def frontend_surface_requires_queue(react_surface: dict[str, Any], status_matrix: list[dict[str, str]]) -> bool:
    if not react_surface.get("available"):
        return True
    production_surface = str(react_surface.get("production_surface") or "")
    react_surface_kind = str(react_surface.get("react_surface") or "")
    current_preview_split = production_surface == "inline_html_js" and react_surface_kind == "mirror"
    return current_preview_split and not frontend_mirror_only_decision(status_matrix)
