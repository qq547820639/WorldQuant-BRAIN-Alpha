"""React surface status validation and frontend queue checks.

Split from the former ``scripts/check_review_gap_closure_tracker.py`` monolith
(Task A3). Loads the optional React build-env validation, normalises it into
the tracker's react_surface payload shape, and verifies that the tracker's
active-work-queue and not-yet-claimable sections reflect the current React
surface state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_review_gap_closure_tracker_helpers import (  # noqa: E402
    expect_all as _expect_all,
    finding as _finding,
    frontend_mirror_only_decision as _frontend_mirror_only_decision,
    reject_any as _reject_any,
    table_row as _table_row,
)

from ._constants import DEFAULT_REACT_APP_DIR, FRONTEND_SURFACE_QUEUE_ITEM


def _react_surface_status(
    *,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        payload = validation if validation is not None else _load_react_build_env_validation()
        return {
            "available": True,
            "ready": bool(payload.get("ready")),
            "production_surface": str(payload.get("production_surface") or ""),
            "react_surface": str(payload.get("react_surface") or ""),
            "build_runner": str((payload.get("tooling") or {}).get("build_runner") or ""),
        }
    except Exception as exc:
        findings.append(
            _finding(
                "react_surface_validation_error",
                str(DEFAULT_REACT_APP_DIR),
                f"could not validate current React surface status: {exc}",
            )
        )
        return {
            "available": False,
            "ready": False,
            "production_surface": "",
            "react_surface": "",
            "build_runner": "",
        }


def _load_react_build_env_validation() -> dict[str, Any]:
    from scripts.check_react_build_env import check_react_build_env

    return check_react_build_env(DEFAULT_REACT_APP_DIR)


def _check_frontend_surface_queue(
    text: str,
    queue: str,
    not_yet: str,
    react_surface: dict[str, Any],
    status_matrix: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> None:
    if not react_surface.get("available"):
        return

    ready = bool(react_surface.get("ready"))
    production_surface = str(react_surface.get("production_surface") or "")
    react_surface_kind = str(react_surface.get("react_surface") or "")
    build_runner = str(react_surface.get("build_runner") or "")
    frontend_row = _table_row(queue, FRONTEND_SURFACE_QUEUE_ITEM)

    if ready:
        for expected in ("ready=true", "build_runner=local_node_modules"):
            if expected not in text:
                findings.append(
                    _finding(
                        "react_surface_fact",
                        expected,
                        "tracker does not reflect current React build readiness",
                    )
                )
    else:
        if "ready=true" in text:
            findings.append(
                _finding(
                    "stale_react_surface_fact",
                    "ready=true",
                    "tracker reports React ready=true while current validation is not ready",
                )
            )
        if "build_runner=local_node_modules" in text and build_runner != "local_node_modules":
            findings.append(
                _finding(
                    "stale_react_surface_fact",
                    "build_runner=local_node_modules",
                    "tracker reports React build readiness that current validation does not support",
                )
            )

    current_preview_split = production_surface == "inline_html_js" and react_surface_kind == "mirror"
    preview_phrases = (
        "inline HTML/JS console remains production",
        "inline HTML/JS console remains the production surface",
        "React remains explicit preview",
        "React mirror-only",
        "React preview path",
        "keep React mirror-only",
    )
    if current_preview_split:
        if _frontend_mirror_only_decision(status_matrix):
            if frontend_row:
                findings.append(
                    _finding(
                        "stale_frontend_surface_queue_fact",
                        FRONTEND_SURFACE_QUEUE_ITEM,
                        "tracker still reports frontend promotion work after the current release decision keeps React mirror-only",
                    )
                )
            _reject_any(
                not_yet,
                ("Frontend unification is not claimable",),
                "stale_frontend_surface_fact",
                findings,
                "not-yet-claimable section still reports frontend promotion work after the mirror-only decision",
            )
            return
        if not frontend_row:
            findings.append(
                _finding(
                    "frontend_surface_queue_fact",
                    FRONTEND_SURFACE_QUEUE_ITEM,
                    "current frontend split still needs an active promotion decision queue item",
                )
            )
        _expect_all(
            frontend_row,
            preview_phrases,
            "frontend_surface_queue_fact",
            findings,
            "frontend queue item does not reflect the current inline/React surface split",
        )
        if "Frontend unification is not claimable" not in not_yet:
            findings.append(
                _finding(
                    "frontend_surface_not_yet_fact",
                    "Frontend unification is not claimable",
                    "not-yet-claimable section does not reflect the current frontend split",
                )
            )
        return

    _reject_any(
        text,
        (*preview_phrases, "Frontend unification is not claimable"),
        "stale_frontend_surface_fact",
        findings,
        "tracker still reports preview-only frontend status after current validation changed",
    )
