"""Source-text extraction and IO helpers for the surface parity audit.

Split from the former ``scripts/check_frontend_surface_parity.py`` monolith
(Task A10 of deep-optimization-phase12). Provides the regex-driven parsers
that recover inline view-registry entries and React TABS / Sidebar /
CARD_CONFIG entries from raw source text, plus the small ``_read_text`` and
``_finding`` helpers shared with the audit and plan-summary layers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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


def _extract_sidebar_nav_items(source: str) -> list[dict[str, str]]:
    """Extract navigation items from Sidebar.tsx — supports v2.0 NAV_ITEMS and v3.0 phase groups."""
    items: list[dict[str, str]] = []

    # v3.0: phase group items ({ id: "xxx" as CardViewId, label: "xxx" })
    for match in re.finditer(
        r"""\{\s*id:\s*['\"](?P<id>[^'\"]+)['\"]\s+as\s+CardViewId\s*,\s*label:\s*['\"](?P<label>[^'\"]+)['\"]""",
        source,
    ):
        items.append({"id": match.group("id"), "label": match.group("label")})

    # v2.0: TOOLS_ITEMS array
    tools_match = re.search(r"const\s+TOOLS_ITEMS\b[^=]*=\s*\[(?P<body>.*?)\];", source, flags=re.DOTALL)
    if tools_match:
        for match in re.finditer(
            r"\{\s*id:\s*['\"](?P<id>[^'\"]+)['\"]\s*,\s*label:\s*['\"](?P<label>[^'\"]+)['\"]",
            tools_match.group("body"),
        ):
            items.append({"id": match.group("id"), "label": match.group("label")})

    # Legacy: v2.0 NAV_ITEMS
    nav_match = re.search(r"const\s+NAV_ITEMS\b[^=]*=\s*\[(?P<body>.*?)\];", source, flags=re.DOTALL)
    if nav_match:
        for match in re.finditer(
            r"\{\s*id:\s*['\"](?P<id>[^'\"]+)['\"]\s*,\s*label:\s*['\"](?P<label>[^'\"]+)['\"]",
            nav_match.group("body"),
        ):
            items.append({"id": match.group("id"), "label": match.group("label")})

    return items


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


def _finding(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}
