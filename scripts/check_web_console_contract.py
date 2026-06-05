"""Check shipped Web console HTML for production UX contract details.

This is a static guard for small but user-visible regressions that are easy to
miss in broader syntax/module checks: favicon fallback, credential form
semantics, and lifecycle view wiring.
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = ROOT / "brain_alpha_ops" / "web" / "index.html"
REACT_DIST_HTML = ROOT / "brain_alpha_ops" / "web" / "react_app" / "dist" / "index.html"
ASSET_REF_RE = re.compile(r"""(?:src|href)=["'](/assets/[^"']+)["']""")
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
REQUIRED_INLINE_SNIPPETS = {
    "connection_form_submit_handler": "connectionForm.addEventListener('submit', submitConnectionForm)",
    "connection_form_submit_function": "function submitConnectionForm(event)",
    "lifecycle_data_view": "var DATA_VIEWS = ['cloud', 'lifecycle']",
    "lifecycle_title": "lifecycle: '生命周期'",
    "lifecycle_renderer": "case 'lifecycle': return buildLifecycleRows(lifecycle)",
}


class ConsoleContractParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements_by_id: dict[str, dict[str, Any]] = {}
        self.icon_links: list[dict[str, str]] = []
        self.meta_by_name: dict[str, dict[str, str]] = {}
        self.title_text = ""
        self._stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        attr_map = {str(key).lower(): "" if value is None else str(value) for key, value in attrs}
        parent_ids = [item["id"] for item in self._stack if item.get("id")]
        node = {"tag": tag_name, "attrs": attr_map, "parent_ids": parent_ids}
        node_id = attr_map.get("id", "")
        if node_id:
            node["id"] = node_id
            self.elements_by_id[node_id] = node
        if tag_name == "link" and "icon" in attr_map.get("rel", "").lower().split():
            self.icon_links.append(attr_map)
        if tag_name == "meta" and attr_map.get("name"):
            self.meta_by_name[attr_map["name"]] = attr_map
        if tag_name not in VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        while self._stack:
            node = self._stack.pop()
            if node["tag"] == tag_name:
                break

    def handle_data(self, data: str) -> None:
        if self._stack and self._stack[-1]["tag"] == "title":
            self.title_text += data


def check_web_console_contract(html_path: str | Path = DEFAULT_HTML) -> dict[str, Any]:
    requested_path = Path(html_path)
    path = _resolve_html_path(requested_path)
    findings: list[dict[str, str]] = []
    try:
        html = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return _result(requested_path, findings=[_finding("missing_html", str(requested_path), "HTML file does not exist")])
    except OSError as exc:
        return _result(path, findings=[_finding("read_error", str(path), str(exc))])

    parser = ConsoleContractParser()
    parser.feed(html)
    if _is_react_shell(parser, html):
        return _check_react_shell_contract(path, parser, html, findings)

    return _check_legacy_inline_contract(path, parser, html, findings)


def _resolve_html_path(html_path: Path) -> Path:
    if html_path.is_file():
        return html_path
    if html_path.resolve() == DEFAULT_HTML.resolve() and REACT_DIST_HTML.is_file():
        return REACT_DIST_HTML
    return html_path


def _is_react_shell(parser: ConsoleContractParser, html: str) -> bool:
    return "root" in parser.elements_by_id and (
        "brain-alpha-csrf" in parser.meta_by_name
        or "brain-alpha-stream" in parser.meta_by_name
        or "/assets/" in html
    )


def _check_legacy_inline_contract(
    path: Path,
    parser: ConsoleContractParser,
    html: str,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    facts = {
        "surface": "legacy_inline",
        "title": parser.title_text.strip(),
        "favicon_count": len(parser.icon_links),
        "connection_form_tag": _element_tag(parser, "connectionForm"),
        "password_inside_connection_form": _inside(parser, "password", "connectionForm"),
        "conn_test_button_type": _element_attr(parser, "connTestBtn", "type"),
        "conn_test_button_action": _element_attr(parser, "connTestBtn", "data-action"),
        "conn_test_button_inside_connection_form": _inside(parser, "connTestBtn", "connectionForm"),
        "lifecycle_snippets": {},
    }

    _expect(bool(facts["title"] == "BRAIN Alpha Ops"), "title", "BRAIN Alpha Ops", facts["title"], findings)
    _expect(bool(parser.icon_links), "favicon_present", "link rel=icon", "missing", findings)
    for index, icon in enumerate(parser.icon_links):
        href = icon.get("href", "")
        if href == "/favicon.ico" or href.endswith("/favicon.ico"):
            findings.append(_finding("favicon_no_default_ico", href, "favicon must not fall back to /favicon.ico"))
        if not href:
            findings.append(_finding("favicon_href", f"icon[{index}]", "favicon link is missing href"))
    _expect(facts["connection_form_tag"] == "form", "connection_form", "form#connectionForm", facts["connection_form_tag"], findings)
    _expect(
        bool(facts["password_inside_connection_form"]),
        "password_form_semantics",
        "password input inside connectionForm",
        "outside form",
        findings,
    )
    _expect(facts["conn_test_button_type"] == "submit", "conn_test_submit", "type=submit", facts["conn_test_button_type"], findings)
    _expect(
        facts["conn_test_button_action"] == "test-connection",
        "conn_test_action",
        "data-action=test-connection",
        facts["conn_test_button_action"],
        findings,
    )
    _expect(
        bool(facts["conn_test_button_inside_connection_form"]),
        "conn_test_inside_form",
        "connTestBtn inside connectionForm",
        "outside form",
        findings,
    )

    lifecycle_facts: dict[str, bool] = {}
    for code, snippet in REQUIRED_INLINE_SNIPPETS.items():
        present = snippet in html
        lifecycle_facts[code] = present
        _expect(present, code, snippet, "missing", findings)
    facts["lifecycle_snippets"] = lifecycle_facts

    return _result(path, facts=facts, findings=findings)


def _check_react_shell_contract(
    path: Path,
    parser: ConsoleContractParser,
    html: str,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    asset_refs = sorted(set(ASSET_REF_RE.findall(html)))
    facts = {
        "surface": "react_dist",
        "title": parser.title_text.strip(),
        "favicon_count": len(parser.icon_links),
        "root_tag": _element_tag(parser, "root"),
        "csrf_meta_present": "brain-alpha-csrf" in parser.meta_by_name,
        "stream_meta_present": "brain-alpha-stream" in parser.meta_by_name,
        "asset_refs": asset_refs,
    }

    _expect(facts["title"] == "BRAIN Alpha Ops", "title", "BRAIN Alpha Ops", facts["title"], findings)
    _expect(bool(parser.icon_links), "favicon_present", "link rel=icon", "missing", findings)
    for index, icon in enumerate(parser.icon_links):
        href = icon.get("href", "")
        if href == "/favicon.ico" or href.endswith("/favicon.ico"):
            findings.append(_finding("favicon_no_default_ico", href, "favicon must not fall back to /favicon.ico"))
        if not href:
            findings.append(_finding("favicon_href", f"icon[{index}]", "favicon link is missing href"))
    _expect(facts["root_tag"] == "div", "react_root", "div#root", facts["root_tag"], findings)
    _expect(
        bool(facts["csrf_meta_present"]),
        "csrf_meta",
        "meta[name=brain-alpha-csrf]",
        "missing",
        findings,
    )
    _expect(
        bool(facts["stream_meta_present"]),
        "stream_meta",
        "meta[name=brain-alpha-stream]",
        "missing",
        findings,
    )
    _expect(bool(asset_refs), "react_assets", "/assets/*.js and /assets/*.css", "missing", findings)
    missing_assets = [ref for ref in asset_refs if not (path.parent / ref.lstrip("/")).is_file()]
    if missing_assets:
        findings.append(_finding("missing_react_asset", ",".join(missing_assets), "React shell references missing assets"))
    return _result(path, facts=facts, findings=findings)


def _result(path: Path, *, facts: dict[str, Any] | None = None, findings: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "ok": not findings,
        "schema_version": "web_console_contract_check.v1",
        "html": str(path),
        "facts": facts or {},
        "findings": findings,
    }


def _element_tag(parser: ConsoleContractParser, element_id: str) -> str:
    return str((parser.elements_by_id.get(element_id) or {}).get("tag") or "")


def _element_attr(parser: ConsoleContractParser, element_id: str, attr: str) -> str:
    element = parser.elements_by_id.get(element_id) or {}
    attrs = element.get("attrs") if isinstance(element.get("attrs"), dict) else {}
    return str(attrs.get(attr, ""))


def _inside(parser: ConsoleContractParser, element_id: str, ancestor_id: str) -> bool:
    element = parser.elements_by_id.get(element_id) or {}
    parent_ids = element.get("parent_ids") if isinstance(element.get("parent_ids"), list) else []
    return ancestor_id in parent_ids


def _expect(condition: bool, code: str, expected: str, actual: str, findings: list[dict[str, str]]) -> None:
    if not condition:
        findings.append(_finding(code, expected, f"actual: {actual}"))


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check shipped Web console contract details.")
    parser.add_argument("--html", default=str(DEFAULT_HTML), help="Built Web HTML path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_web_console_contract(args.html)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"web console contract check passed: {result['html']}")
    else:
        print(f"web console contract check failed: {result['html']}", file=sys.stderr)
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['message']}: {finding['expected']}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
