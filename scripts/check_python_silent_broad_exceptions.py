"""Guard against silent broad exception handlers in Python code."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("brain_alpha_ops", "scripts")
EXCLUDED_PARTS = {"tests", "experiments", "__pycache__", ".git", ".pytest_cache", ".pytest_cache_runtime"}
BROAD_EXCEPTIONS = {"Exception", "BaseException"}


def check_python_silent_broad_exceptions(root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    root_path = Path(root)
    candidates = _candidate_files(root_path)
    findings: list[dict[str, Any]] = []
    for path in candidates:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for handler in _broad_handlers(tree):
            if not _is_silent_handler(handler):
                continue
            findings.append({
                "file": path.relative_to(root_path).as_posix(),
                "line": handler.lineno,
                "text": _snippet(text, handler.lineno),
            })
    findings.sort(key=lambda item: (item["file"], int(item["line"])))
    return {
        "ok": not findings,
        "schema_version": "python_silent_broad_exceptions.v1",
        "root": str(root_path),
        "checked_files": len(candidates),
        "silent_broad_exception_count": len(findings),
        "findings": findings,
    }


def _candidate_files(root_path: Path) -> list[Path]:
    files: list[Path] = []
    for relative_root in SCAN_ROOTS:
        base = root_path / relative_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in EXCLUDED_PARTS for part in path.relative_to(root_path).parts):
                continue
            files.append(path)
    return sorted(files)


def _broad_handlers(tree: ast.AST) -> list[ast.ExceptHandler]:
    handlers: list[ast.ExceptHandler] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_exception(node.type):
            handlers.append(node)
    return handlers


def _is_broad_exception(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in BROAD_EXCEPTIONS
    if isinstance(node, ast.Tuple):
        return any(_is_broad_exception(elt) for elt in node.elts)
    return False


def _is_silent_handler(handler: ast.ExceptHandler) -> bool:
    body = [stmt for stmt in handler.body if not _is_docstring(stmt)]
    if not body:
        return True
    for stmt in body:
        if isinstance(stmt, (ast.Pass, ast.Continue)):
            continue
        if isinstance(stmt, ast.Return) and _is_silent_return(stmt):
            continue
        return False
    return True


def _is_silent_return(stmt: ast.Return) -> bool:
    value = stmt.value
    if value is None:
        return True
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    return False


def _is_docstring(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)


def _snippet(text: str, line_number: int, *, radius: int = 1) -> str:
    lines = text.splitlines()
    start = max(0, line_number - 1 - radius)
    end = min(len(lines), line_number + radius)
    return " | ".join(line.strip() for line in lines[start:end])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Python broad exception handlers for silent swallowing.")
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_python_silent_broad_exceptions(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"python silent broad exception guard passed ({result['silent_broad_exception_count']} findings)")
    else:
        for finding in result["findings"]:
            print(f"{finding['file']}:{finding['line']}: {finding['text']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
