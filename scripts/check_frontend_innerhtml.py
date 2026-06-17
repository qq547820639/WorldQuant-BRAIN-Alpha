"""Guard frontend raw HTML injection sinks.

The current frontend still uses a small set of approved string renderers.
This check prevents new direct HTML writes from appearing outside that reviewed
surface without an explicit allowlist update.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_FRONTEND_ROOT = PROJECT_ROOT / "brain_alpha_ops" / "web" / "js"
FRONTEND_ROOT = PROJECT_ROOT / "brain_alpha_ops" / "web" / "react_app" / "src"

HTML_SINK_PATTERNS = (
    ("innerHTML", ".innerHTML"),
    ("outerHTML", ".outerHTML"),
    ("insertAdjacentHTML", ".insertAdjacentHTML("),
    ("document.write", "document.write("),
    ("document.writeln", "document.writeln("),
    ("createContextualFragment", ".createContextualFragment("),
)
MISNAMED_RAW_ALIAS_MARKERS = ("setSafeHtml", "setRawHtml")
RAW_HTML_CALL_MARKER = "setRawHtml("
REACT_HTML_SINK_PATTERNS = (
    ("dangerouslySetInnerHTML", "dangerouslySetInnerHTML"),
    ("raw_html_prop", "__html"),
)

ALLOWED_HTML_SINKS: set[tuple[str, int, str]] = set()
APPROVED_RAW_HTML_CALLS: dict[str, tuple[tuple[str, ...], ...]] = {
    "app.js": (
        ("VIEW_GROUPS.map(function (group)", "renderTab(view, currentView)", "esc(group.label)", "esc(group.hint)"),
        ("setRawHtml(document.body", "shutdown-screen", "服务已关闭"),
    ),
    "strategy-panel.js": (
        ("policy-grid", "items.map(function (item)", "esc(item.label)", "esc(String(item.value))", "esc(item.note)"),
    ),
    "result-table.js": (
        ("setRawHtml(tableBody, '')",),
        ("getEmptyActionsHtml(view)",),
        ("rows.map(function (row, idx)", "renderSafeHtmlFragment(rendered, col.htmlType)", "escapeAttr(row.id", "escapeAttr(title)"),
        ("rows.map(function (row, idx)", "renderSafeHtmlFragment(rendered || '-', col.htmlType)", "escapeAttr(row.id", "actionsHtml"),
    ),
    "views/detail.js": (
        ("detail-empty", "暂无详情数据"),
        ("parts.map(function (html)", "detail-section", "html.body || html"),
        ("sectionBlock('云端记录'", "renderFieldTableHTML"),
        ("sectionBlock('生命周期记录'", "renderFieldTableHTML"),
        ("sectionBlock('检查结果'", "renderFieldTableHTML", "sectionBlock('检查详情'"),
    ),
    "views/monitor.js": (
        ("cards.map(function (card)", "esc(card.icon)", "esc(card.label)", "esc(String(card.value))"),
        ("tiles.map(function (tile)", "esc(tile.label)", "esc(String(tile.value))"),
        ("slot-empty", "暂无回测槽位"),
        ("backtests.map(function (bt, idx)", "esc(status)", "esc(alphaId)", "scoreSpan"),
    ),
    "components/toast.js": (
        ("setRawHtml(toastEl, html)",),
    ),
    "components/table.js": (
        ("setRawHtml(container, '')",),
        ("esc(options.emptyText)",),
        ("displayRows.map(function (row, idx)", "renderSafeHtmlFragment(rendered, col.htmlType)", "escapeAttr(rowId)", "esc(String(value"),
        ("displayRows.map(function (row, idx)", "renderSafeHtmlFragment(rendered || '-', col.htmlType)", "esc(String(title))", "actions"),
    ),
    "components/spinner.js": (
        ("setRawHtml(tableBody, skeletonHtml)",),
        ("setRawHtml(container, blocks)",),
    ),
    "workflow-assist.js": (
        ("shortcuts-list", "itemsHtml"),
        ("workflow-wizard", "stepsHtml", "close-wizard", "start-wizard-run"),
    ),
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def check_frontend_innerhtml(root: Path = FRONTEND_ROOT) -> dict:
    findings: list[dict] = []
    checked = 0
    raw_calls_checked = 0
    files_checked = 0
    if not root.exists():
        return {
            "ok": False,
            "schema_version": "frontend_innerhtml_guard.v1",
            "root": str(root),
            "checked": 0,
            "raw_calls_checked": 0,
            "files_checked": 0,
            "approved_raw_call_patterns": sum(len(patterns) for patterns in APPROVED_RAW_HTML_CALLS.values()),
            "allowed": len(ALLOWED_HTML_SINKS) + 2,
            "findings": [{
                "file": ".",
                "line": 0,
                "sink": "missing_frontend_root",
                "text": f"frontend root does not exist: {root}",
            }],
        }
    suffixes = ("*.js",) if root == LEGACY_FRONTEND_ROOT or any(root.glob("*.js")) else ("*.ts", "*.tsx", "*.js", "*.jsx")
    paths: list[Path] = []
    for suffix in suffixes:
        paths.extend(root.rglob(suffix))
    for path in sorted(set(paths)):
        files_checked += 1
        rel = _rel(path, root)
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            for sink, marker in REACT_HTML_SINK_PATTERNS:
                if marker in line:
                    checked += 1
                    findings.append({
                        "file": rel,
                        "line": line_number,
                        "sink": sink,
                        "text": stripped,
                    })
            if _is_misnamed_raw_html_alias(stripped):
                findings.append({
                    "file": rel,
                    "line": line_number,
                    "sink": "misnamed_raw_alias",
                    "text": stripped,
                })
            for sink, marker in HTML_SINK_PATTERNS:
                if marker not in line:
                    continue
                checked += 1
                if _is_allowed_sink(rel, line_number, sink, stripped, lines):
                    continue
                findings.append({
                    "file": rel,
                    "line": line_number,
                    "sink": sink,
                    "text": stripped,
                })
            if RAW_HTML_CALL_MARKER in line:
                raw_calls_checked += 1
                call_text = _extract_call_text(lines, line_number - 1, RAW_HTML_CALL_MARKER)
                if not _is_allowed_raw_html_call(rel, call_text):
                    findings.append({
                        "file": rel,
                        "line": line_number,
                        "sink": "setRawHtml",
                        "text": _compact(call_text),
                    })
    return {
        "ok": not findings,
        "schema_version": "frontend_innerhtml_guard.v1",
        "root": str(root),
        "checked": checked,
        "raw_calls_checked": raw_calls_checked,
        "files_checked": files_checked,
        "approved_raw_call_patterns": sum(len(patterns) for patterns in APPROVED_RAW_HTML_CALLS.values()),
        "allowed": len(ALLOWED_HTML_SINKS) + 2,
        "findings": findings,
    }


def _is_misnamed_raw_html_alias(stripped: str) -> bool:
    return (
        "=" in stripped
        and all(marker in stripped for marker in MISNAMED_RAW_ALIAS_MARKERS)
        and stripped.index("setSafeHtml") < stripped.index("=") < stripped.index("setRawHtml")
    )


def _is_allowed_sink(rel: str, line_number: int, sink: str, stripped: str, lines: list[str]) -> bool:
    if (rel, line_number, sink) in ALLOWED_HTML_SINKS:
        return True
    if rel != "utils.js" or sink != "innerHTML":
        return False
    if stripped == "el.innerHTML = Utils.escapeHtml(String(html ?? ''));":
        return True
    if stripped == "el.innerHTML = String(html ?? '');":
        context = "\n".join(lines[max(0, line_number - 4):line_number])
        return "Utils.setRawHtml = function" in context
    return False


def _extract_call_text(lines: list[str], start_index: int, marker: str) -> str:
    collected: list[str] = []
    balance = 0
    started = False
    for index in range(start_index, min(len(lines), start_index + 30)):
        line = lines[index]
        if not started:
            marker_at = line.find(marker)
            if marker_at < 0:
                continue
            line = line[marker_at:]
            started = True
        collected.append(line.rstrip())
        balance += _paren_balance(line)
        if started and balance <= 0 and ");" in line:
            break
    return "\n".join(collected)


def _paren_balance(line: str) -> int:
    balance = 0
    quote = ""
    escaped = False
    for char in line:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            balance += 1
        elif char == ")":
            balance -= 1
    return balance


def _is_allowed_raw_html_call(rel: str, call_text: str) -> bool:
    if not call_text:
        return False
    compact = _compact(call_text)
    if "Utils.setRawHtml = function" in compact:
        return True
    return any(
        all(snippet in compact for snippet in required_snippets)
        for required_snippets in APPROVED_RAW_HTML_CALLS.get(rel, ())
    )


def _compact(text: str) -> str:
    return " ".join(str(text or "").split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check frontend raw HTML sinks against an allowlist.")
    parser.add_argument("--root", default=str(FRONTEND_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_frontend_innerhtml(Path(args.root))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"frontend raw HTML sink guard passed ({result['checked']} sinks checked)")
    else:
        for finding in result["findings"]:
            print(f"{finding['file']}:{finding['line']}: {finding['sink']}: {finding['text']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
