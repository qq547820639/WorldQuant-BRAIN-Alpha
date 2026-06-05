"""Validate incremental web.py facade hardening progress."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEB = ROOT / "brain_alpha_ops" / "web.py"
SCHEMA_VERSION = "web_facade_contract_check.v1"


def check_web_facade_contract(web_path: str | Path = DEFAULT_WEB) -> dict[str, Any]:
    path = Path(web_path)
    findings: list[dict[str, str]] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    has_context_class = _has_web_application_context_binding(tree)
    has_context_factory = any(isinstance(node, ast.FunctionDef) and node.name == "web_application_context" for node in tree.body)
    direct_sys_modules_count = _direct_sys_modules_count(tree)
    lambda_alias_count = _module_lambda_alias_count(tree)
    runtime_facade_direct_sys_modules = _runtime_facade_direct_sys_modules(tree)
    public_brain_alpha_imports = _public_brain_alpha_imports(tree)

    if not has_context_class:
        findings.append(_finding("missing_web_application_context", "WebApplicationContext"))
    if not has_context_factory:
        findings.append(_finding("missing_context_factory", "web_application_context"))
    if direct_sys_modules_count != 1:
        findings.append(_finding("direct_sys_modules_count", str(direct_sys_modules_count)))
    if lambda_alias_count != 0:
        findings.append(_finding("lambda_alias_count", str(lambda_alias_count)))
    for line in runtime_facade_direct_sys_modules:
        findings.append(_finding("runtime_facade_sys_modules_call", str(line)))
    for imported in public_brain_alpha_imports:
        findings.append(_finding("public_brain_alpha_import", imported))

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "web_path": str(path),
        "has_context_class": has_context_class,
        "has_context_factory": has_context_factory,
        "direct_sys_modules_count": direct_sys_modules_count,
        "lambda_alias_count": lambda_alias_count,
        "runtime_facade_sys_modules_count": len(runtime_facade_direct_sys_modules),
        "public_brain_alpha_import_count": len(public_brain_alpha_imports),
        "public_brain_alpha_imports": public_brain_alpha_imports,
        "findings": findings,
    }


def _module_lambda_alias_count(tree: ast.Module) -> int:
    return sum(
        1
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda)
    )


def _has_web_application_context_binding(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "WebApplicationContext":
            return True
        if isinstance(node, ast.Assign) and any(_is_name(target, "WebApplicationContext") for target in node.targets):
            return True
        if isinstance(node, ast.AnnAssign) and _is_name(node.target, "WebApplicationContext"):
            return True
    return False


def _is_name(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _runtime_facade_direct_sys_modules(tree: ast.Module) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "_runtime_facade"
        ):
            continue
        if any(_is_sys_modules_dunder_name(arg) for arg in node.args):
            lines.append(node.lineno)
    return lines


def _public_brain_alpha_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("brain_alpha_ops"):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                if not bound_name.startswith("_"):
                    imports.append(f"{node.lineno}:{node.module}.{alias.name}->{bound_name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name.startswith("brain_alpha_ops"):
                    continue
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                if not bound_name.startswith("_"):
                    imports.append(f"{node.lineno}:{alias.name}->{bound_name}")
    return imports


def _direct_sys_modules_count(tree: ast.Module) -> int:
    return sum(1 for node in ast.walk(tree) if _is_sys_modules_dunder_name(node))


def _is_sys_modules_dunder_name(node: ast.AST) -> bool:
    slice_is_dunder_name = (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "sys"
        and node.value.attr == "modules"
        and (
            (isinstance(node.slice, ast.Constant) and node.slice.value == "__name__")
            or (isinstance(node.slice, ast.Name) and node.slice.id == "__name__")
        )
    )
    return slice_is_dunder_name


def _finding(code: str, value: str) -> dict[str, str]:
    return {"code": code, "value": value}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check web.py facade hardening contract.")
    parser.add_argument("--web", default=str(DEFAULT_WEB), help="Path to brain_alpha_ops/web.py")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    result = check_web_facade_contract(args.web)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"web facade contract check {state}: {result['web_path']}")
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['value']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
