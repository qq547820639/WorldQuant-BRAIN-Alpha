#!/usr/bin/env python3
"""Static guard for Web candidate scientific-audit integration."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/audit.py"
GENERATION_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/generation.py"
OPTIMIZATION_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/optimization.py"
OPTIMIZATION_EXPLAINABILITY_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/optimization_explainability.py"
DECISIONS_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/decisions.py"
PAYLOADS_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/payloads.py"
SIMULATION_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/simulation.py"
CHECK_EVIDENCE_MODULE = ROOT / "brain_alpha_ops" / "web_candidates/check_evidence.py"
PIPELINE_RUNTIME_MODULE = ROOT / "brain_alpha_ops" / "research" / "pipeline_runtime" / "_records_mixin.py"
QUALITY_GATE = ROOT / "scripts" / "quality_gate" / "__init__.py"

REQUIRED_SCHEMA = "candidate-scientific-audit-v1"
REQUIRED_SUMMARY_SCHEMA = "candidate-scientific-audit-summary-v1"
FORBIDDEN_FEEDBACK_SOURCE_TOKENS = (
    "pytest",
    "fixture",
    "unit_test",
    "test_result",
    "browser_smoke",
    "vitest",
)


def check_candidate_scientific_audit(root: str | Path = ROOT) -> dict[str, Any]:
    root_path = Path(root)
    files = {
        "audit": root_path / "brain_alpha_ops" / "web_candidates/audit.py",
        "generation": root_path / "brain_alpha_ops" / "web_candidates/generation.py",
        "optimization": root_path / "brain_alpha_ops" / "web_candidates/optimization.py",
        "optimization_explainability": root_path
        / "brain_alpha_ops"
        / "web_candidates/optimization_explainability.py",
        "decisions": root_path / "brain_alpha_ops" / "web_candidates/decisions.py",
        "payloads": root_path / "brain_alpha_ops" / "web_candidates/payloads.py",
        "simulation": root_path / "brain_alpha_ops" / "web_candidates/simulation.py",
        "simulation_failures": root_path / "brain_alpha_ops" / "web_candidates/simulation_failures.py",
        "check_evidence": root_path / "brain_alpha_ops" / "web_candidates/check_evidence.py",
        "pipeline_runtime": root_path / "brain_alpha_ops" / "research" / "pipeline_runtime" / "_records_mixin.py",
        "quality_gate": root_path / "scripts" / "quality_gate" / "__init__.py",
    }
    findings: list[dict[str, Any]] = []
    texts = {name: _read(path, findings=findings, key=name) for name, path in files.items()}

    _require(texts["audit"], REQUIRED_SCHEMA, "missing_candidate_scientific_audit_schema", files["audit"], findings)
    _require(texts["audit"], REQUIRED_SUMMARY_SCHEMA, "missing_candidate_scientific_audit_summary_schema", files["audit"], findings)
    for token in (
        "attach_scientific_audit",
        "scientific_audit_summary",
        "test_script_outcomes_used",
        "submit_allowed",
        "official_api_called",
        "redact_data",
        "append_scientific_audit_event",
        "expression_profile_summary",
        "expression_similarity",
        "official_context_proof",
        "expression_delta",
        "optimization_explanation",
    ):
        _require(texts["audit"], token, f"missing_audit_contract_token:{token}", files["audit"], findings)

    _require(texts["generation"], "attach_scientific_audit", "generation_not_attaching_scientific_audit", files["generation"], findings)
    _require(texts["generation"], "operation=\"candidate_generation\"", "generation_missing_operation_label", files["generation"], findings)
    _require(texts["generation"], "scientific_audit_summary(processed_candidates)", "generation_missing_audit_summary", files["generation"], findings)

    _require(texts["optimization"], "attach_scientific_audit", "optimization_not_attaching_scientific_audit", files["optimization"], findings)
    _require(texts["optimization"], "operation=\"candidate_optimization\"", "optimization_missing_operation_label", files["optimization"], findings)
    _require(texts["optimization"], "parent=parent.to_dict()", "optimization_missing_parent_lineage", files["optimization"], findings)
    _require(texts["optimization"], "expression_official_context_proof", "optimization_missing_official_context_proof", files["optimization"], findings)
    _require(texts["optimization"], "expression_delta", "optimization_missing_expression_delta", files["optimization"], findings)
    _require(texts["optimization"], "optimization_explanation", "optimization_missing_explanation_contract", files["optimization"], findings)
    _require(texts["optimization"], "optimizer_trace", "optimization_missing_optimizer_trace", files["optimization"], findings)
    _require(texts["optimization"], "selected_strategy", "optimization_missing_selected_strategy", files["optimization"], findings)
    _require(texts["optimization"], "failed_dimension", "optimization_missing_failed_dimension", files["optimization"], findings)
    _require(texts["optimization"], "scientific_audit_summary(processed_candidates)", "optimization_missing_audit_summary", files["optimization"], findings)
    for token in (
        "optimization_concentration_audit",
        "optimization-concentration-audit-v1",
        "concentration_risk",
        "risk_reasons",
        "single_mutation_mode",
        "single_parent_failure",
    ):
        _require(
            texts["optimization_explainability"],
            token,
            f"optimization_explainability_missing_token:{token}",
            files["optimization_explainability"],
            findings,
        )

    _require(texts["decisions"], "attach_scientific_audit", "decisions_not_restoring_or_attaching_audit", files["decisions"], findings)
    _require(texts["decisions"], "operation=\"production_decision\"", "decisions_missing_operation_label", files["decisions"], findings)

    _require(texts["payloads"], "scientific_audit_summary(annotated_rows)", "payloads_missing_audit_summary", files["payloads"], findings)
    _require(texts["simulation"], "append_scientific_audit_event", "simulation_missing_audit_event_append", files["simulation"], findings)
    _require(texts["simulation"], "operation=\"official_simulation_writeback\"", "simulation_missing_writeback_operation_label", files["simulation"], findings)
    _require(texts["simulation_failures"], "append_scientific_audit_event", "simulation_failures_missing_audit_event_append", files["simulation_failures"], findings)
    _require(texts["simulation_failures"], "operation=\"official_simulation_writeback\"", "simulation_failures_missing_writeback_operation_label", files["simulation_failures"], findings)
    _require(texts["check_evidence"], "append_scientific_audit_event", "check_evidence_missing_audit_event_append", files["check_evidence"], findings)
    _require(texts["check_evidence"], "operation=\"pre_submit_availability_check\"", "check_evidence_missing_operation_label", files["check_evidence"], findings)
    _require(texts["pipeline_runtime"], "append_scientific_audit_event", "pipeline_runtime_missing_audit_event_append", files["pipeline_runtime"], findings)
    _require(texts["pipeline_runtime"], "operation=\"robustness_feedback\"", "pipeline_runtime_missing_robustness_operation_label", files["pipeline_runtime"], findings)
    _require(texts["quality_gate"], "candidate_scientific_audit", "quality_gate_missing_candidate_audit_step", files["quality_gate"], findings)

    for name in (
        "audit",
        "generation",
        "optimization",
        "optimization_explainability",
        "decisions",
        "payloads",
        "simulation",
        "simulation_failures",
        "check_evidence",
        "pipeline_runtime",
    ):
        _find_forbidden_feedback_sources(texts[name], files[name], findings)

    return {
        "ok": not findings,
        "schema_version": "candidate_scientific_audit_check.v1",
        "root": str(root_path),
        "checked_files": len(files),
        "findings": findings,
    }


def _read(path: Path, *, findings: list[dict[str, Any]], key: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(_finding("missing_file", path, f"{key} file cannot be read: {exc}", line=1))
        return ""


def _require(text: str, token: str, code: str, path: Path, findings: list[dict[str, Any]]) -> None:
    if token not in text:
        findings.append(_finding(code, path, f"Missing required token: {token}", line=1))


def _find_forbidden_feedback_sources(text: str, path: Path, findings: list[dict[str, Any]]) -> None:
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        findings.append(_finding("python_syntax_error", path, str(exc), line=exc.lineno or 1))
        return
    _FeedbackSourceVisitor(path, findings).visit(tree)


class _FeedbackSourceVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, findings: list[dict[str, Any]]) -> None:
        self.path = path
        self.findings = findings
        self.scopes: list[dict[str, tuple[list[str], int]]] = [{}]

    @property
    def scope(self) -> dict[str, tuple[list[str], int]]:
        return self.scopes[-1]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_scoped_body(node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_scoped_body(node.body)

    def visit_Lambda(self, node: ast.Lambda) -> Any:
        return None

    def visit_Assign(self, node: ast.Assign) -> Any:
        values = self._literal_strings(node.value)
        if values is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.scope[target.id] = (values, node.lineno)
        self.generic_visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        values = self._literal_strings(node.value) if node.value is not None else None
        if values is not None and isinstance(node.target, ast.Name):
            self.scope[node.target.id] = (values, node.lineno)
        if node.value is not None:
            self.generic_visit(node.value)

    def visit_Expr(self, node: ast.Expr) -> Any:
        self._record_append(node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        if self._call_name(node.func) in {"attach_scientific_audit", "append_scientific_audit_event"}:
            for keyword in node.keywords:
                if keyword.arg != "feedback_sources":
                    continue
                values = self._literal_strings(keyword.value)
                if values is None and isinstance(keyword.value, ast.Name):
                    values = self._lookup_strings(keyword.value.id)
                if values is not None:
                    self._report_forbidden(values, line=getattr(keyword.value, "lineno", node.lineno))
        self.generic_visit(node)

    def _visit_scoped_body(self, body: list[ast.stmt]) -> None:
        self.scopes.append({})
        for statement in body:
            self.visit(statement)
        self.scopes.pop()

    def _literal_strings(self, node: ast.AST | None) -> list[str] | None:
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values: list[str] = []
            for item in node.elts:
                if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                    return None
                values.append(item.value)
            return values
        if isinstance(node, ast.Name):
            return self._lookup_strings(node.id)
        return None

    def _record_append(self, node: ast.AST) -> None:
        if not isinstance(node, ast.Call):
            return
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "append":
            return
        if not isinstance(node.func.value, ast.Name) or len(node.args) != 1:
            return
        variable = node.func.value.id
        entry = self.scope.get(variable)
        if entry is None:
            return
        value = node.args[0]
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return
        existing, line = entry
        self.scope[variable] = ([*existing, value.value], line)

    def _lookup_strings(self, name: str) -> list[str] | None:
        for scope in reversed(self.scopes):
            entry = scope.get(name)
            if entry is not None:
                return list(entry[0])
        return None

    def _call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""

    def _report_forbidden(self, values: list[str], *, line: int) -> None:
        lowered = [str(value).lower() for value in values]
        if not any(any(token in value for token in FORBIDDEN_FEEDBACK_SOURCE_TOKENS) for value in lowered):
            return
        self.findings.append(_finding(
            "test_feedback_source_in_production",
            self.path,
            "Production candidate audit feedback sources must not include pytest, fixtures, browser smoke, or unit-test outcomes.",
            line=line,
        ))


def _finding(code: str, path: Path, message: str, *, line: int) -> dict[str, Any]:
    try:
        file_name = path.relative_to(ROOT).as_posix()
    except ValueError:
        file_name = str(path)
    return {
        "code": code,
        "file": file_name,
        "line": int(line),
        "severity": "blocking",
        "message": message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Web candidate scientific-audit integration.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_candidate_scientific_audit(args.root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    elif result["ok"]:
        print("candidate scientific audit guard passed")
    else:
        for finding in result["findings"]:
            print(f"{finding['file']}:{finding['line']}: {finding['code']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
