"""Detect logger calls that bypass log redaction helpers."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "brain_alpha_ops"
SCHEMA_VERSION = "log_redaction_check.v1"
LOG_METHODS = {"critical", "debug", "error", "exception", "info", "warning"}
LOGGER_OBJECTS = {"log", "logger", "logging"}
RAW_EXCEPTION_NAMES = {"cleanup_exc", "e", "err", "error", "exc", "last_error"}
RAW_USER_VALUE_NAMES = {
    "alpha_id",
    "cache_dir",
    "expression",
    "filename",
    "filepath",
    "index_code",
    "key",
    "official_alpha_id",
    "path",
    "profile_path",
    "simulation_id",
    "symbol",
}
RAW_MAPPING_KEYS = RAW_USER_VALUE_NAMES | {"official_id"}
SAFE_HELPER_NAMES = {"redact_error_message", "redact_text", "safe_error_message"}


def check_log_redaction(root: str | Path = DEFAULT_ROOT) -> dict[str, Any]:
    scan_root = Path(root)
    findings: list[dict[str, str]] = []
    for path in _python_files(scan_root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except SyntaxError as exc:
            findings.append(_finding("syntax_error", path, exc.lineno or 1, str(exc)))
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_logger_call(node):
                findings.extend(_find_call_issues(path, node))
    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "root": str(scan_root),
        "finding_count": len(findings),
        "findings": findings,
    }


def _python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts
    )


def _is_logger_call(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in LOG_METHODS:
        return False
    value = func.value
    return isinstance(value, ast.Name) and value.id in LOGGER_OBJECTS


def _find_call_issues(path: Path, node: ast.Call) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if node.args and isinstance(node.args[0], ast.JoinedStr):
        findings.append(
            _finding(
                "logger_fstring",
                path,
                node.lineno,
                "logger calls must use structured arguments and redaction helpers",
            )
        )

    for arg in node.args[1:]:
        if _is_safe_helper_call(arg):
            continue
        if isinstance(arg, ast.Name) and arg.id in RAW_EXCEPTION_NAMES:
            findings.append(
                _finding(
                    "raw_exception_log_arg",
                    path,
                    getattr(arg, "lineno", node.lineno),
                    f"raw exception argument `{arg.id}` must use redact_error_message(...)",
                )
            )
            continue
        if _is_raw_user_value(arg):
            findings.append(
                _finding(
                    "raw_user_value_log_arg",
                    path,
                    getattr(arg, "lineno", node.lineno),
                    "raw user expression must use redact_text(...) before logging",
                )
            )
    return findings


def _is_safe_helper_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    return _call_name(node.func) in SAFE_HELPER_NAMES


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_raw_user_value(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in RAW_USER_VALUE_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in RAW_USER_VALUE_NAMES
    if isinstance(node, ast.Call) and _call_name(node.func) == "get" and node.args:
        key = node.args[0]
        return isinstance(key, ast.Constant) and key.value in RAW_MAPPING_KEYS
    return False


def _finding(code: str, path: Path, line: int, message: str) -> dict[str, str]:
    return {
        "code": code,
        "path": str(path),
        "line": str(line),
        "message": message,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check logger calls for raw sensitive values.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Python file or directory to scan")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    result = check_log_redaction(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"log redaction check {state}: {result['root']}")
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['path']}:{finding['line']} ({finding['message']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
