#!/usr/bin/env python3
"""Validate the local BRAIN capability registry.

This check is offline by design. It compares canonical settings, web
configuration schema, and local official-context cache metadata, and
additionally verifies that:

  - Business code contains no scattered hardcoded operator/field literals
    (AST-based scan of high-risk modules).
  - The capability registry matches ``data/official_*.json`` exactly
    (parity check).
  - Bidirectional registry ↔ code consistency (opt-in via ``--consistency``).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Business files to scan for scattered hardcoded operator/field literals.
SCANNED_FILES = [
    "brain_alpha_ops/research/local_backtest/engine.py",
    "brain_alpha_ops/presets.py",
    "brain_alpha_ops/research/dataset_selector.py",
    "brain_alpha_ops/research/expression_engine.py",
    "brain_alpha_ops/research/expression_ast/_parser.py",
]

# Variable names that are allowed to hardcode operator/field literals
# (intentional fallbacks or classification sets, not registry duplicates).
ALLOWED_HARDCODED_NAMES = {
    "_FALLBACK_OPERATORS",  # engine.py: documented fallback when registry unavailable
    "func_names",  # engine.py: used for field extraction, not validation
}

# Minimum overlap with official operators to flag as a hardcoded duplicate.
MIN_OPERATOR_OVERLAP = 6


def check_capability_registry() -> dict[str, Any]:
    """Delegate to the existing web capability registry check."""
    from brain_alpha_ops.web_capability_registry import check_capability_registry as _check
    from brain_alpha_ops.web_cloud.snapshot import official_context_file_counts
    from brain_alpha_ops.web_config_schema import public_config_schema

    return _check(
        public_config_schema=public_config_schema,
        official_context_file_counts=official_context_file_counts,
    )


def check_registry_consistency() -> dict[str, Any]:
    """Run bidirectional registry consistency validation (opt-in)."""
    from brain_alpha_ops.registry_validation import validate_registry_consistency

    try:
        from brain_alpha_ops.web_capability_registry import build_capability_registry
        registry = build_capability_registry()
    except Exception:
        registry = None

    scoring_ops = {"rank", "ts_mean", "ts_std", "ts_delta", "ts_rank", "ts_min",
                   "ts_max", "ts_sum", "ts_argmin", "ts_argmax", "group_neutralize",
                   "zscore", "quantile", "power", "abs", "log", "sign", "add",
                   "subtract", "multiply", "divide", "max", "min", "delay",
                   "ts_decay_linear", "ts_corr", "ts_cov", "decay_linear",
                   "indneutralize", "winsorize", "normalize", "demean"}

    gate_ops = {"sharpe", "fitness", "turnover_min", "turnover_platform",
                "self_correlation", "prod_correlation", "weight_concentration",
                "sub_universe_sharpe"}

    return validate_registry_consistency(
        registry=registry,
        scoring_operators=scoring_ops,
        gate_operators=gate_ops,
    )


def check_hardcoded_literals() -> dict[str, Any]:
    """AST-scan SCANNED_FILES for hardcoded operator/field name sets.

    Flags any assignment to a set/frozenset literal containing at least
    ``MIN_OPERATOR_OVERLAP`` official operator names, unless the target
    variable name is in ``ALLOWED_HARDCODED_NAMES``.
    """
    findings: list[dict[str, Any]] = []
    official_ops = _load_official_operator_names()
    for rel_path in SCANNED_FILES:
        path = ROOT / rel_path
        if not path.exists():
            findings.append({
                "code": "scanned_file_missing",
                "severity": "WARNING",
                "message": f"Scanned file not found: {rel_path}",
            })
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            findings.append({
                "code": "scanned_file_parse_error",
                "severity": "WARNING",
                "message": f"Failed to parse {rel_path}: {exc}",
            })
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            target_name = _assign_target_name(node)
            if target_name in ALLOWED_HARDCODED_NAMES:
                continue
            string_values = _extract_string_set(node.value)
            if len(string_values) < MIN_OPERATOR_OVERLAP:
                continue
            overlap = string_values & official_ops
            if len(overlap) >= MIN_OPERATOR_OVERLAP:
                findings.append({
                    "code": "hardcoded_operator_set",
                    "severity": "P1",
                    "message": (
                        f"{rel_path}: '{target_name or '<expr>'}' hardcodes "
                        f"{len(overlap)} official operator names; derive from "
                        "capability registry instead."
                    ),
                    "evidence": {
                        "file": rel_path,
                        "variable": target_name,
                        "overlap_count": len(overlap),
                        "overlap_sample": sorted(overlap)[:10],
                    },
                })
    return {
        "ok": not findings,
        "findings": findings,
        "scanned_files": list(SCANNED_FILES),
        "allowed_hardcoded_names": sorted(ALLOWED_HARDCODED_NAMES),
    }


def check_registry_matches_official_context() -> dict[str, Any]:
    """Verify registry entries match ``data/official_*.json`` exactly."""
    findings: list[dict[str, Any]] = []
    try:
        from brain_alpha_ops.data.capability_registry import get_registry
        registry = get_registry()
    except Exception as exc:
        return {
            "ok": False,
            "findings": [{
                "code": "registry_unavailable",
                "severity": "P0",
                "message": f"Capability registry unavailable: {exc}",
            }],
        }

    registry_ops = registry.operators()
    official_ops = _load_official_operator_names()
    _check_parity("operator", registry_ops, official_ops, findings)

    registry_fields = registry.fields()
    official_fields = _load_official_field_ids()
    _check_parity("field", registry_fields, official_fields, findings)

    registry_datasets = {e.name for e in registry.entries if e.kind == "dataset"}
    official_datasets = _load_official_dataset_ids()
    _check_parity("dataset", registry_datasets, official_datasets, findings)

    return {
        "ok": not findings,
        "findings": findings,
        "counts": {
            "operators": {"registry": len(registry_ops), "official": len(official_ops)},
            "fields": {"registry": len(registry_fields), "official": len(official_fields)},
            "datasets": {"registry": len(registry_datasets), "official": len(official_datasets)},
        },
    }


def _check_parity(
    kind: str,
    registry_set: set[str],
    official_set: set[str],
    findings: list[dict[str, Any]],
) -> None:
    """Append findings when registry_set and official_set diverge."""
    missing = official_set - registry_set
    extra = registry_set - official_set
    if missing:
        findings.append({
            "code": f"registry_missing_{kind}",
            "severity": "P0",
            "message": f"Registry is missing {len(missing)} {kind}(s) present in official_*.json.",
            "evidence": {"missing_sample": sorted(missing)[:10]},
        })
    if extra:
        findings.append({
            "code": f"registry_extra_{kind}",
            "severity": "P1",
            "message": f"Registry has {len(extra)} extra {kind}(s) not in official_*.json.",
            "evidence": {"extra_sample": sorted(extra)[:10]},
        })


def _load_official_operator_names() -> set[str]:
    path = ROOT / "data" / "official_operators.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["name"]) for row in rows}


def _load_official_field_ids() -> set[str]:
    path = ROOT / "data" / "official_fields.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["id"]) for row in rows}


def _load_official_dataset_ids() -> set[str]:
    path = ROOT / "data" / "official_datasets.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["id"]) for row in rows}


def _assign_target_name(node: ast.Assign | ast.AnnAssign) -> str:
    """Extract the variable name from an assignment target."""
    target = node.targets[0] if isinstance(node, ast.Assign) else node.target
    if isinstance(target, ast.Name):
        return target.id
    return ""


def _extract_string_set(node: ast.AST) -> set[str]:
    """Extract string constants from a set/list/frozenset literal."""
    if isinstance(node, (ast.Set, ast.List)):
        return {
            n.value for n in node.elts
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"set", "frozenset"}:
        if node.args:
            return _extract_string_set(node.args[0])
    return set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate local BRAIN capability registry alignment."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--consistency", action="store_true",
                        help="Run bidirectional registry consistency check (opt-in).")
    parser.add_argument("--hardcoded", action="store_true",
                        help="Scan business code for hardcoded operator/field literals.")
    parser.add_argument("--parity", action="store_true",
                        help="Verify registry matches data/official_*.json.")
    parser.add_argument("--all", action="store_true",
                        help="Run all checks (capability + hardcoded + parity).")
    args = parser.parse_args(argv)

    checks: list[tuple[str, dict[str, Any]]] = []
    if args.consistency:
        checks.append(("consistency", check_registry_consistency()))
    elif args.hardcoded:
        checks.append(("hardcoded", check_hardcoded_literals()))
    elif args.parity:
        checks.append(("parity", check_registry_matches_official_context()))
    elif args.all:
        checks = [
            ("capability", check_capability_registry()),
            ("hardcoded", check_hardcoded_literals()),
            ("parity", check_registry_matches_official_context()),
        ]
    else:
        # Default: capability + hardcoded + parity (consistency is opt-in only).
        checks = [
            ("capability", check_capability_registry()),
            ("hardcoded", check_hardcoded_literals()),
            ("parity", check_registry_matches_official_context()),
        ]

    all_ok = all(result.get("ok", False) for _, result in checks)
    all_findings: list[dict[str, Any]] = []
    for name, result in checks:
        for finding in result.get("findings", []):
            entry = dict(finding)
            entry["check"] = name
            all_findings.append(entry)

    if args.json:
        print(json.dumps({
            "ok": all_ok,
            "checks": {name: result for name, result in checks},
            "findings": all_findings,
        }, ensure_ascii=False, indent=2, default=str))
    elif all_ok:
        print("BRAIN capability registry check passed.")
        for name, result in checks:
            print(f"  [{name}] ok={result.get('ok')}")
    else:
        print("BRAIN capability registry check failed.")
        for finding in all_findings:
            print(f"  [{finding.get('severity', '?')}] "
                  f"{finding.get('check', '')}:{finding.get('code', '')}: "
                  f"{finding.get('message', '')}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
