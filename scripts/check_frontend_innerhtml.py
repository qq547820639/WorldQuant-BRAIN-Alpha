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
FRONTEND_ROOT = PROJECT_ROOT / "brain_alpha_ops" / "web" / "js"

HTML_SINK_PATTERNS = (
    ("innerHTML", ".innerHTML"),
    ("outerHTML", ".outerHTML"),
    ("insertAdjacentHTML", ".insertAdjacentHTML("),
    ("document.write", "document.write("),
    ("document.writeln", "document.writeln("),
    ("createContextualFragment", ".createContextualFragment("),
)

ALLOWED_HTML_SINKS: set[tuple[str, int, str]] = set()

ALLOWED_HTML_SINK_SNIPPETS = {
    ("innerHTML", "utils.js", "el.innerHTML = String(html ?? '');"),
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def check_frontend_innerhtml(root: Path = FRONTEND_ROOT) -> dict:
    findings: list[dict] = []
    checked = 0
    for path in sorted(root.rglob("*.js")):
        rel = _rel(path, root)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            for sink, marker in HTML_SINK_PATTERNS:
                if marker not in line:
                    continue
                checked += 1
                if _is_allowed_sink(rel, line_number, sink, stripped):
                    continue
                findings.append({
                    "file": rel,
                    "line": line_number,
                    "sink": sink,
                    "text": stripped,
                })
    return {
        "ok": not findings,
        "schema_version": "frontend_innerhtml_guard.v1",
        "root": str(root),
        "checked": checked,
        "allowed": len(ALLOWED_HTML_SINKS) + len(ALLOWED_HTML_SINK_SNIPPETS),
        "findings": findings,
    }


def _is_allowed_sink(rel: str, line_number: int, sink: str, stripped: str) -> bool:
    if (rel, line_number, sink) in ALLOWED_HTML_SINKS:
        return True
    return any(
        allowed_sink == sink and allowed_rel == rel and snippet in stripped
        for allowed_sink, allowed_rel, snippet in ALLOWED_HTML_SINK_SNIPPETS
    )


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
