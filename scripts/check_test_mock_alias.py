#!/usr/bin/env python3
"""Check for test-mock-alias anti-pattern (P0-4 type lesson).

Scans test files for mock classes that add method aliases (e.g.
``list_fields = get_fields``) and verifies the corresponding production
class also has the aliased method.  Reports instances where tests
"fix" a missing production method by patching the mock.

Usage:
    .venv/bin/python scripts/check_test_mock_alias.py [--json] [--root ROOT]
"""

from __future__ import annotations

import ast
import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_VERSION = "test_mock_alias_check.v1"

# Maps test class names to production class import paths
# (auto-discovered below; manual overrides here)
KNOWN_PRODUCTION_CLASSES: dict[str, str] = {
    "OfficialDataLoader": "brain_alpha_ops.data.loader",
    "CandidateGenerator": "brain_alpha_ops.research.generator",
}


def _find_method_aliases(tree: ast.AST) -> list[dict[str, Any]]:
    """Find ``alias_name = method_name`` assignments inside class bodies."""
    aliases: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_name = node.name
        for stmt in node.body:
            # Look for:  alias_name = existing_method_name
            if not isinstance(stmt, ast.Assign):
                continue
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            alias_name = stmt.targets[0].id
            if not isinstance(stmt.value, ast.Name):
                continue
            method_name = stmt.value.id
            # Only count if method_name is defined as a function in the same class
            if _class_has_method(node, method_name):
                aliases.append({
                    "class": class_name,
                    "alias": alias_name,
                    "method": method_name,
                    "line": stmt.lineno,
                })
    return aliases


def _class_has_method(class_node: ast.ClassDef, method_name: str) -> bool:
    """Check whether *class_node* defines a function named *method_name*."""
    for stmt in class_node.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == method_name:
            return True
    return False


def _find_production_module(class_name: str) -> str | None:
    """Resolve a production module path for *class_name*."""
    return KNOWN_PRODUCTION_CLASSES.get(class_name)


def _class_has_method_in_module(module_path: str, class_name: str, method_name: str) -> bool | None:
    """Check whether production class defines *method_name*.  Returns None if unresolvable."""
    try:
        mod = __import__(module_path, fromlist=[class_name])
        cls = getattr(mod, class_name, None)
    except Exception:
        return None
    if cls is None:
        return None
    return hasattr(cls, method_name) and callable(getattr(cls, method_name))


def scan(root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    test_dir = root / "tests"
    if not test_dir.is_dir():
        return {"ok": True, "findings": []}

    for test_file in sorted(test_dir.rglob("test_*.py")):
        try:
            tree = ast.parse(test_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        aliases = _find_method_aliases(tree)
        for alias_info in aliases:
            class_name = alias_info["class"]
            alias_name = alias_info["alias"]
            method_name = alias_info["method"]

            prod_module = _find_production_module(class_name)
            if prod_module is None:
                continue  # Not a known production class; skip

            has_in_prod = _class_has_method_in_module(prod_module, class_name, alias_name)
            if has_in_prod:
                continue  # Production also has the alias; all good

            findings.append({
                "code": "test_mock_alias_missing_in_production",
                "test_file": str(test_file.relative_to(root)),
                "test_class": class_name,
                "alias": alias_name,
                "aliases_to": method_name,
                "test_line": alias_info["line"],
                "production_module": prod_module,
                "production_has_alias": False,
                "message": (
                    f"test class '{class_name}' in {test_file.name} defines "
                    f"'{alias_name} = {method_name}' alias, but production "
                    f"class '{class_name}' in {prod_module} has no '{alias_name}' "
                    f"method — this is the P0-4 anti-pattern"
                ),
            })

    return {
        "ok": len(findings) == 0,
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "findings": findings,
        "finding_count": len(findings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check for test-mock-alias anti-pattern")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root")
    args = parser.parse_args()

    result = scan(args.root)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["ok"]:
            print(f"OK: No test-mock-alias anti-patterns found ({result['finding_count']} findings)")
        else:
            print(f"FAIL: {result['finding_count']} test-mock-alias anti-pattern(s) found:")
            for f in result["findings"]:
                print(f"  {f['test_file']}:{f['test_line']} — {f['message']}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
