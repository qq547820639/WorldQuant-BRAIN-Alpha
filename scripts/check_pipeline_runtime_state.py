"""Validate the grouped runtime-state contract for AlphaResearchPipeline."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PIPELINE = ROOT / "brain_alpha_ops" / "research" / "pipeline.py"
DEFAULT_STATE = ROOT / "brain_alpha_ops" / "research" / "pipeline_state.py"
SCHEMA_VERSION = "pipeline_runtime_state_check.v1"
MAX_INIT_SELF_ASSIGNMENTS = 5
MIN_RUNTIME_STATE_FIELDS = 20


def check_pipeline_runtime_state(
    pipeline_path: str | Path = DEFAULT_PIPELINE,
    state_path: str | Path = DEFAULT_STATE,
) -> dict[str, Any]:
    pipeline_file = Path(pipeline_path)
    state_file = Path(state_path)
    findings: list[dict[str, str]] = []

    pipeline_tree = ast.parse(pipeline_file.read_text(encoding="utf-8"), filename=str(pipeline_file))
    state_tree = ast.parse(state_file.read_text(encoding="utf-8"), filename=str(state_file))

    init_assignments = _init_self_assignments(pipeline_tree)
    runtime_state_class = _class_def(state_tree, "PipelineRuntimeState")
    bind_call_present = _bind_call_present(pipeline_tree)

    runtime_state_fields = []
    if runtime_state_class is None:
        findings.append(_finding("missing_runtime_state_class", "PipelineRuntimeState"))
    else:
        runtime_state_fields = _dataclass_field_names(runtime_state_class)
        if len(runtime_state_fields) < MIN_RUNTIME_STATE_FIELDS:
            findings.append(
                _finding(
                    "runtime_state_field_count",
                    str(len(runtime_state_fields)),
                    "runtime state should group a substantial portion of the pipeline runtime fields",
                )
            )

    if init_assignments > MAX_INIT_SELF_ASSIGNMENTS:
        findings.append(
            _finding(
                "init_self_assignment_count",
                str(init_assignments),
                "pipeline __init__ should keep direct self assignments small and route runtime state through the bundle",
            )
        )

    if not bind_call_present:
        findings.append(
            _finding(
                "missing_bind_call",
                "bind_runtime_state_properties(AlphaResearchPipeline)",
                "pipeline module should bind runtime-state compatibility properties after class definition",
            )
        )

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "pipeline_path": str(pipeline_file),
        "state_path": str(state_file),
        "init_self_assignment_count": init_assignments,
        "runtime_state_field_count": len(runtime_state_fields),
        "runtime_state_fields": runtime_state_fields,
        "bind_call_present": bind_call_present,
        "findings": findings,
    }


def _class_def(tree: ast.Module, name: str) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _dataclass_field_names(class_def: ast.ClassDef) -> list[str]:
    return [
        node.target.id
        for node in class_def.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
    ]


def _init_self_assignments(tree: ast.Module) -> int:
    class_def = _class_def(tree, "AlphaResearchPipeline")
    if class_def is None:
        return 0
    init = next((node for node in class_def.body if isinstance(node, ast.FunctionDef) and node.name == "__init__"), None)
    if init is None:
        return 0
    count = 0
    for node in ast.walk(init):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    count += 1
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                count += 1
    return count


def _bind_call_present(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        if not (isinstance(value.func, ast.Name) and value.func.id == "bind_runtime_state_properties"):
            continue
        if not value.args:
            continue
        arg = value.args[0]
        if isinstance(arg, ast.Name) and arg.id == "AlphaResearchPipeline":
            return True
    return False


def _finding(code: str, value: str, message: str = "") -> dict[str, str]:
    finding = {"code": code, "value": value}
    if message:
        finding["message"] = message
    return finding


def main() -> int:
    parser = argparse.ArgumentParser(description="Check AlphaResearchPipeline runtime-state grouping.")
    parser.add_argument("--pipeline", default=str(DEFAULT_PIPELINE), help="Path to brain_alpha_ops/research/pipeline.py")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="Path to brain_alpha_ops/research/pipeline_state.py")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    result = check_pipeline_runtime_state(args.pipeline, args.state)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"pipeline runtime state check {state}: {result['pipeline_path']}")
        for finding in result["findings"]:
            extra = f" ({finding['message']})" if "message" in finding else ""
            print(f"- {finding['code']}: {finding['value']}{extra}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
