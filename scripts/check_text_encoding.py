"""Scan source text for common mojibake and replacement characters."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCAN_DIRS = ("README.md", "brain_alpha_ops", "docs", "scripts", "tests")
TEXT_SUFFIXES = {
    ".bat",
    ".cmd",
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".git",
    ".codex_pydeps",
    ".mypy_cache",
    ".pip_audit_cache",
    ".pytest_cache",
    ".pytest_cache_runtime",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
SKIP_FILES = {
    "docs/CODE_REVIEW_20260521.md",
    "scripts/check_text_encoding.py",
}

MOJIBAKE_RE = re.compile(
    r"�|鈥|銆|鎺|浜戠|鏆|妫|绯荤|鐢熶|杩|绛夊|閫|鍚屾|鍦ㄨ|浠诲|彁浜|寮€|鍙栨"
)


def iter_text_files(root: Path, targets: list[str] | None = None) -> list[Path]:
    root = root.resolve()
    paths: set[Path] = set()
    for target_name in targets or list(DEFAULT_SCAN_DIRS):
        target = (root / target_name).resolve()
        if not target.exists():
            continue
        if target.is_file():
            if _is_text_file(target) and not _is_skipped(target, root):
                paths.add(target)
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            current = Path(dirpath)
            if _is_skipped(current, root):
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
            for filename in filenames:
                path = current / filename
                if _is_text_file(path) and not _is_skipped(path, root):
                    paths.add(path)
    return sorted(paths)


def check_text_encoding(root: Path = ROOT, targets: list[str] | None = None) -> dict[str, Any]:
    root = root.resolve()
    findings: list[dict[str, Any]] = []
    files = iter_text_files(root, targets)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append(_finding(root, path, exc.start + 1, "invalid_utf8", str(exc)))
            continue
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = MOJIBAKE_RE.search(line)
            if match:
                findings.append(_finding(root, path, line_number, "mojibake", line.strip()))
    return {
        "ok": not findings,
        "schema_version": "text_encoding_scan.v1",
        "root": str(root),
        "checked": len(files),
        "findings": findings,
    }


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"README.md"}


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except ValueError:
        return True
    normalized = relative.as_posix()
    if normalized in SKIP_FILES:
        return True
    return any(part in SKIP_DIRS or part.startswith(".codex_tmp_") for part in relative.parts)


def _finding(root: Path, path: Path, line: int, code: str, snippet: str) -> dict[str, Any]:
    return {
        "path": path.resolve().relative_to(root).as_posix(),
        "line": line,
        "code": code,
        "snippet": snippet[:220],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan source text for UTF-8 decode errors and common mojibake.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("targets", nargs="*")
    args = parser.parse_args(argv)

    result = check_text_encoding(Path(args.root), args.targets or None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"Text encoding scan passed: {result['checked']} files checked.")
    else:
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['path']}:{finding['line']}: {finding['snippet']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
