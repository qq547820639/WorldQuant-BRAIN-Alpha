"""Audit the production inline console and React mirror navigation surfaces.

This check is intentionally read-only. It makes the dual-frontend gap visible
without changing which frontend is served by default. Use ``--fail-on-gaps``
only when React is expected to be ready for promotion to the single surface.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INLINE_REGISTRY = ROOT / "brain_alpha_ops" / "web" / "js" / "view-registry.js"
DEFAULT_REACT_APP = ROOT / "brain_alpha_ops" / "web" / "react_app" / "src" / "App.tsx"
DEFAULT_PARITY_PLAN = ROOT / "docs" / "FRONTEND_SURFACE_PARITY_PLAN.json"
VALID_PLAN_STATUSES = {"implemented", "planned", "retired"}
VALID_REACT_ONLY_STATUSES = {"accepted"}


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


def extract_inline_views(source: str) -> list[dict[str, str]]:
    view_order = _extract_inline_view_order(source)
    titles = _extract_inline_titles(source)
    return [{"id": view_id, "label": titles.get(view_id, view_id)} for view_id in view_order]


def extract_react_tabs(source: str) -> list[dict[str, str]]:
    tabs_match = re.search(r"const\s+TABS\b[^=]*=\s*\[(?P<body>.*?)\];", source, flags=re.DOTALL)
    if tabs_match:
        tabs: list[dict[str, str]] = []
        for match in re.finditer(
            r"\{\s*id:\s*['\"](?P<id>[^'\"]+)['\"]\s*,\s*label:\s*['\"](?P<label>[^'\"]+)['\"]",
            tabs_match.group("body"),
        ):
            tabs.append({"id": match.group("id"), "label": match.group("label")})
        return tabs
    return _extract_react_card_config(source)


def _extract_react_card_config(source: str) -> list[dict[str, str]]:
    config_match = re.search(
        r"const\s+CARD_CONFIG\s*=\s*\{(?P<body>.*?)\}\s+as\s+const;",
        source,
        flags=re.DOTALL,
    )
    if not config_match:
        return []
    cards: list[dict[str, str]] = []
    for match in re.finditer(
        r"(?P<id>[A-Za-z0-9_]+)\s*:\s*\{\s*title:\s*['\"](?P<label>[^'\"]+)['\"]",
        config_match.group("body"),
    ):
        cards.append({"id": match.group("id"), "label": match.group("label")})
    return cards


def _extract_inline_view_order(source: str) -> list[str]:
    arrays: dict[str, list[str]] = {}
    for name in ("WORKFLOW_VIEWS", "DATA_VIEWS", "RESEARCH_VIEWS"):
        match = re.search(rf"var\s+{name}\s*=\s*\[(?P<body>.*?)\];", source, flags=re.DOTALL)
        arrays[name] = _string_literals(match.group("body")) if match else []

    view_order_match = re.search(r"VIEW_ORDER:\s*(?P<body>.*?),\s*\n\s*WORKFLOW_VIEWS:", source, flags=re.DOTALL)
    if not view_order_match:
        return arrays["WORKFLOW_VIEWS"] + arrays["DATA_VIEWS"] + arrays["RESEARCH_VIEWS"]

    order: list[str] = []
    for name in re.findall(r"\b(?:WORKFLOW_VIEWS|DATA_VIEWS|RESEARCH_VIEWS)\b", view_order_match.group("body")):
        order.extend(arrays.get(name, []))
    return order


def _extract_inline_titles(source: str) -> dict[str, str]:
    match = re.search(r"VIEW_TITLES:\s*\{(?P<body>.*?)\},\s*\n\s*VIEW_ICONS:", source, flags=re.DOTALL)
    if not match:
        return {}
    titles: dict[str, str] = {}
    for item in re.finditer(r"(?P<id>[A-Za-z0-9_]+)\s*:\s*['\"](?P<label>[^'\"]+)['\"]", match.group("body")):
        titles[item.group("id")] = item.group("label")
    return titles


def _string_literals(source: str) -> list[str]:
    return [match.group("value") for match in re.finditer(r"['\"](?P<value>[^'\"]+)['\"]", source)]


def _read_text(path: Path, findings: list[dict[str, Any]], *, required: bool = True) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if required:
            findings.append(_finding("missing_file", str(path), "Required frontend source file does not exist."))
    except OSError as exc:
        findings.append(_finding("read_error", str(path), str(exc)))
    return ""


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


def _finding(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit inline and React frontend navigation surface parity.")
    parser.add_argument("--inline-registry", default=str(DEFAULT_INLINE_REGISTRY))
    parser.add_argument("--react-app", default=str(DEFAULT_REACT_APP))
    parser.add_argument("--plan", default=str(DEFAULT_PARITY_PLAN), help="JSON plan mapping inline views to React targets.")
    parser.add_argument("--fail-on-gaps", action="store_true", help="Exit non-zero when the two surfaces expose different navigation ids.")
    parser.add_argument("--fail-on-unmapped-plan", action="store_true", help="Exit non-zero when an inline view has no parity-plan entry.")
    parser.add_argument("--fail-on-unimplemented-plan", action="store_true", help="Exit non-zero when parity-plan entries are still planned.")
    parser.add_argument("--fail-on-stale-plan", action="store_true", help="Exit non-zero when the parity plan references removed inline views.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_frontend_surface_parity(
        Path(args.inline_registry),
        Path(args.react_app),
        plan_path=Path(args.plan) if args.plan else None,
        fail_on_gaps=args.fail_on_gaps,
        fail_on_unmapped_plan=args.fail_on_unmapped_plan,
        fail_on_unimplemented_plan=args.fail_on_unimplemented_plan,
        fail_on_stale_plan=args.fail_on_stale_plan,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        parity = result["parity"]
        status = "matches" if parity["matches"] else ("strict matches" if parity.get("strict_matches") else "has gaps")
        print(f"frontend surface parity {status}: {result['inline_view_count']} inline views, {result['react_tab_count']} React tabs")
    else:
        print("frontend surface parity check failed", file=sys.stderr)
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['message']}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
