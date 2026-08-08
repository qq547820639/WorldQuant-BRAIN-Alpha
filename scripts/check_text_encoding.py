from __future__ import annotations

"""Scan text/source files for mojibake codepoints.

Codepoints in the Unicode private use area (U+E000..U+F8FF) and the replacement
character (U+FFFD) typically indicate encoding corruption or stray control
garbage.  ``node_modules`` and other dependency prefixes are skipped.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "site-packages",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".trae",
    }
)


def _is_mojibake(data: str) -> bool:
    for char in data:
        codepoint = ord(char)
        if 0xE000 <= codepoint <= 0xF8FF or codepoint == 0xFFFD:
            return True
    return False


def _collect_files(root: Path, targets: list[str] | None) -> list[Path]:
    if targets is None:
        return [path for path in sorted(root.rglob("*")) if path.is_file()]
    paths: list[Path] = []
    for target in targets:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.is_dir():
            paths.extend(path for path in sorted(candidate.rglob("*")) if path.is_file())
        elif candidate.is_file():
            paths.append(candidate)
    return paths


def check_text_encoding(root: str | Path = ROOT, targets: list[str] | None = None) -> dict[str, object]:
    root_path = Path(root)
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in _collect_files(root_path, targets):
        try:
            relative = path.relative_to(root_path)
        except ValueError:
            relative = path
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        key = str(relative)
        if key in seen:
            continue
        seen.add(key)
        try:
            data = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _is_mojibake(data):
            findings.append(
                {
                    "code": "mojibake",
                    "path": str(relative),
                    "message": "file contains mojibake codepoints",
                }
            )
    return {
        "ok": not findings,
        "schema_version": "text_encoding_check.v1",
        "root": str(root_path),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan files for mojibake codepoints.")
    parser.add_argument("--root", default=str(ROOT), help="Root directory to scan.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_text_encoding(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"text encoding {status}: {len(result['findings'])} mojibake finding(s)")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['path']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())