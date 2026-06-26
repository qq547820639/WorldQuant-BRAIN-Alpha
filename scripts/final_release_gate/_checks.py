"""Source/config redline checks for the final release gate.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Covers environment, custom
field/operator expansion scanning, threshold drift, dataset redline,
traceability, and official API alignment checks.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_RELEASE_REQUIREMENTS,
    CANONICAL_THRESHOLDS,
)

from ._models import (
    CUSTOM_EXTENSION_NAMES,
    Finding,
    LEGACY_SINGLE_DATASET_STRATEGIES,
    RELEASE_DATASET_STRATEGIES,
    REQUIRED_OFFICIAL_API,
    _add_finding,
)


def _check_environment(cfg: dict[str, Any], findings: list[Finding]) -> None:
    environment = str(cfg.get("environment") or "").strip().lower()
    if environment != "production":
        _add_finding(
            findings,
            "P0",
            "ENVIRONMENT_NOT_PRODUCTION",
            "Final release must run with environment=production.",
            "config/run_config.json",
            current=environment,
            expected="production",
        )


def _scan_custom_field_operator_expansion(repo_root: Path, findings: list[Finding]) -> None:
    suspicious: list[str] = []
    for path in _iter_release_source_files(repo_root):
        if _source_registers_custom_field_or_operator(path):
            suspicious.append(path.relative_to(repo_root).as_posix())
    if suspicious:
        _add_finding(
            findings,
            "P0",
            "CUSTOM_FIELD_OPERATOR_RISK",
            "Suspicious custom field/operator extension hooks were found in release source.",
            current=suspicious[:20],
        )


def _source_registers_custom_field_or_operator(path: Path) -> bool:
    """Detect executable custom field/operator extension hooks.

    The release gate should not fail because an audit script contains a string
    such as ``custom_field`` in a diagnostic message.  We only flag code-level
    names and call targets that would actually register or expose extensions.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, OSError):
        return True
    suspicious_names = {name.lower() for name in CUSTOM_EXTENSION_NAMES}
    for node in ast.walk(tree):
        name = ""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        if not name:
            continue
        normalized = name.lower().replace("-", "_")
        if normalized in suspicious_names:
            return True
    return False


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _iter_release_source_files(repo_root: Path) -> list[Path]:
    skip_dirs = {".git", ".codex_pydeps", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__", "build", "dist", "tests"}
    files: list[Path] = []
    for base_name in ("brain_alpha_ops", "scripts"):
        base = repo_root / base_name
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(repo_root)
            if any(part in skip_dirs for part in rel.parts):
                continue
            if rel.as_posix() == "scripts/final_release_gate.py":
                continue
            if rel.parts[:2] == ("scripts", "final_release_gate"):
                continue
            files.append(path)
    return sorted(files)


def _check_exact_thresholds(cfg: dict[str, Any], findings: list[Finding]) -> None:
    thresholds = (((cfg.get("ops") or {}).get("thresholds") or {}))
    expected_values = {**CANONICAL_THRESHOLDS, **CANONICAL_RELEASE_REQUIREMENTS}
    for key, expected in expected_values.items():
        current = thresholds.get(key)
        if current != expected:
            _add_finding(
                findings,
                "P0",
                f"THRESHOLD_DRIFT_{key.upper()}",
                f"Threshold {key} differs from the final release baseline.",
                "config/run_config.json",
                current=current,
                expected=expected,
            )


def _check_dataset_redline(repo_root: Path, cfg: dict[str, Any], findings: list[Finding]) -> None:
    ops = cfg.get("ops") or {}
    settings = ops.get("settings") or {}
    budget = ops.get("budget") or {}
    dataset = str(settings.get("dataset") or "").strip()
    strategy = str(budget.get("dataset_strategy") or "").strip().lower()
    official_dataset_ids = _official_dataset_ids(repo_root, ops)
    if not dataset:
        _add_finding(
            findings,
            "P0",
            "DATASET_ID_EMPTY",
            "Final release requires an explicit settings.dataset value.",
            "config/run_config.json",
            current=dataset,
        )
    dataset_available = bool(dataset and dataset in official_dataset_ids)
    legacy_single_dataset_strategy = strategy in LEGACY_SINGLE_DATASET_STRATEGIES and dataset_available
    if strategy not in RELEASE_DATASET_STRATEGIES and not legacy_single_dataset_strategy:
        _add_finding(
            findings,
            "P0",
            "DATASET_STRATEGY_NOT_FIXED",
            "Final release requires a fixed dataset strategy or a legacy strategy backed by an explicit official dataset.",
            "config/run_config.json",
            current=strategy,
            expected=sorted(RELEASE_DATASET_STRATEGIES),
        )
    if dataset and dataset not in official_dataset_ids:
        _add_finding(
            findings,
            "P0",
            "DATASET_ID_NOT_IN_OFFICIAL_CONTEXT",
            "Configured dataset must exist in official_datasets.json.",
            "config/run_config.json",
            current=dataset,
        )


def _official_dataset_ids(repo_root: Path, ops: dict[str, Any]) -> set[str]:
    storage_dir = Path(str(ops.get("storage_dir") or "data"))
    if not storage_dir.is_absolute():
        storage_dir = repo_root / storage_dir
    try:
        rows = json.loads((storage_dir / "official_datasets.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(rows, list):
        return set()
    return {str(row.get("id") or "").strip() for row in rows if isinstance(row, dict)}


def _check_traceability_redline(cfg: dict[str, Any], findings: list[Finding]) -> None:
    budget = ((cfg.get("ops") or {}).get("budget") or {})
    if budget.get("run_forever") is True:
        _add_finding(
            findings,
            "P1",
            "RUN_FOREVER_ENABLED",
            "Final release requires a bounded run manifest, not run_forever=true.",
            "config/run_config.json",
            current=True,
            expected=False,
        )
    max_cycles = budget.get("max_cycles")
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles <= 0:
        _add_finding(
            findings,
            "P1",
            "MAX_CYCLES_NOT_BOUNDED",
            "Final release requires max_cycles to be a positive integer.",
            "config/run_config.json",
            current=max_cycles,
            expected="positive integer",
        )


def _check_official_api_alignment(cfg: dict[str, Any], findings: list[Finding]) -> None:
    api = (((cfg.get("ops") or {}).get("official_api") or {}))
    for key, expected in REQUIRED_OFFICIAL_API.items():
        current = api.get(key)
        if current != expected:
            _add_finding(
                findings,
                "P1",
                f"OFFICIAL_API_DRIFT_{key.upper()}",
                f"Official API setting {key} differs from the release baseline.",
                "config/run_config.json",
                current=current,
                expected=expected,
            )
