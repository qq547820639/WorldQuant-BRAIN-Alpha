"""Guard frontend raw innerHTML sinks.

The current frontend still uses a small set of approved string renderers.
This check prevents new direct innerHTML writes from appearing outside that
reviewed surface without an explicit allowlist update.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "brain_alpha_ops" / "web" / "js"

ALLOWED_INNERHTML_SINKS = {
    ("app.js", 141),
    ("app.js", 645),
    ("app.js", 658),
    ("app.js", 660),
    ("components/table.js", 66),
    ("components/table.js", 71),
    ("components/table.js", 92),
    ("components/table.js", 119),
    ("components/toast.js", 41),
    ("result-table.js", 39),
    ("result-table.js", 67),
    ("result-table.js", 72),
    ("result-table.js", 94),
    ("strategy-panel.js", 55),
    ("views/detail.js", 67),
    ("views/detail.js", 174),
    ("views/detail.js", 319),
    ("views/detail.js", 343),
    ("views/detail.js", 368),
    ("views/monitor.js", 90),
    ("views/monitor.js", 144),
    ("views/monitor.js", 162),
    ("views/monitor.js", 167),
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def check_frontend_innerhtml(root: Path = FRONTEND_ROOT) -> dict:
    findings: list[dict] = []
    checked = 0
    for path in sorted(root.rglob("*.js")):
        rel = _rel(path, root)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if ".innerHTML" not in line:
                continue
            checked += 1
            if (rel, line_number) not in ALLOWED_INNERHTML_SINKS:
                findings.append({
                    "file": rel,
                    "line": line_number,
                    "text": line.strip(),
                })
    return {
        "ok": not findings,
        "schema_version": "frontend_innerhtml_guard.v1",
        "root": str(root),
        "checked": checked,
        "allowed": len(ALLOWED_INNERHTML_SINKS),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check frontend innerHTML sinks against an allowlist.")
    parser.add_argument("--root", default=str(FRONTEND_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_frontend_innerhtml(Path(args.root))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"frontend innerHTML guard passed ({result['checked']} sinks checked)")
    else:
        for finding in result["findings"]:
            print(f"{finding['file']}:{finding['line']}: {finding['text']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
