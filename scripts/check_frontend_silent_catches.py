"""Guard against silent catch blocks in the frontend runtime bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "brain_alpha_ops" / "web"

SILENT_CATCH_RE = re.compile(
    r"catch\s*(?:\([^)]*\))?\s*\{\s*(?:(?:/\*.*?\*/)|(?://[^\n]*))*\s*\}",
    re.S,
)


def check_frontend_silent_catches(root: str | Path = DEFAULT_ROOT) -> dict[str, Any]:
    root_path = Path(root)
    js_root = root_path / "js"
    react_src = root_path / "react_app" / "src"
    candidates: list[Path] = []
    if js_root.exists():
        candidates.extend(sorted(js_root.rglob("*.js")))
    if react_src.exists():
        candidates.extend(
            sorted(
                path
                for path in react_src.rglob("*")
                if path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}
            )
        )
    index_path = root_path / "index.html"
    if index_path.exists():
        candidates.append(index_path)

    findings: list[dict[str, Any]] = []
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in SILENT_CATCH_RE.finditer(text):
            findings.append({
                "file": path.relative_to(root_path).as_posix(),
                "line": _line_number(text, match.start()),
                "text": _compact(match.group(0)),
            })

    findings.sort(key=lambda item: (item["file"], int(item["line"])))
    return {
        "ok": not findings,
        "schema_version": "frontend_silent_catches.v1",
        "root": str(root_path),
        "checked_files": len(candidates),
        "silent_catch_count": len(findings),
        "findings": findings,
    }


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _compact(text: str) -> str:
    return " ".join(str(text or "").split())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check frontend catch blocks for silent swallowing.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_frontend_silent_catches(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"frontend silent catch guard passed ({result['silent_catch_count']} silent catches found)")
    else:
        for finding in result["findings"]:
            print(f"{finding['file']}:{finding['line']}: {finding['text']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
