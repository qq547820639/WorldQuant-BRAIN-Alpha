"""Fail-closed release readiness gate for final BRAIN Alpha delivery."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_API_PATHS,
    CANONICAL_RELEASE_REQUIREMENTS,
    CANONICAL_THRESHOLDS,
)

DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
SCHEMA_VERSION = "final_release_gate.v1"

REQUIRED_OFFICIAL_API: dict[str, str] = {
    "base_url": "https://api.worldquantbrain.com",
    "authentication_path": CANONICAL_API_PATHS["authentication"],
    "simulations_path": CANONICAL_API_PATHS["simulations"],
    "data_fields_path": CANONICAL_API_PATHS["data_fields"],
    "operators_path": CANONICAL_API_PATHS["operators"],
    "user_alphas_path": CANONICAL_API_PATHS["user_alphas"],
}

RELEASE_DATASET_STRATEGIES = {"fixed", "locked", "specific"}
CUSTOM_EXTENSION_NAMES = (
    "custom_operator",
    "register_operator",
    "extend_operator",
    "custom_field",
    "register_field",
    "extend_field",
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    current: Any | None = None
    expected: Any | None = None


@dataclass(frozen=True)
class GateReport:
    passed: bool
    schema_version: str
    config: str
    manifest_hash: str
    redlines: dict[str, bool]
    findings: list[Finding]
    official_context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "ok": self.passed,
            "schema_version": self.schema_version,
            "config": self.config,
            "manifest_hash": self.manifest_hash,
            "redlines": self.redlines,
            "findings": [asdict(item) for item in self.findings],
            "official_context": self.official_context,
        }


def run_final_release_gate(
    repo_root: str | Path = ROOT,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
) -> GateReport:
    root = Path(repo_root).resolve()
    config_file = _resolve_under_root(root, config_path)
    findings: list[Finding] = []
    raw_config = _load_config_json(config_file, findings)
    official_context = _validate_official_context(config_file, findings)

    _check_config_loads(config_file, findings)
    _check_environment(raw_config, findings)
    _scan_custom_field_operator_expansion(root, findings)
    _check_exact_thresholds(raw_config, findings)
    _check_dataset_redline(root, raw_config, findings)
    _check_traceability_redline(raw_config, findings)
    _check_official_context_redline(raw_config, findings)
    _check_official_api_alignment(raw_config, findings)
    _check_refresh_status(root, raw_config, findings, official_context=official_context)

    manifest_hash = _build_manifest_hash(root, config_file, findings)
    redlines = _redline_summary(findings)
    passed = not findings
    return GateReport(
        passed=passed,
        schema_version=SCHEMA_VERSION,
        config=str(config_file),
        manifest_hash=manifest_hash,
        redlines=redlines,
        findings=findings,
        official_context=official_context,
    )


def _resolve_under_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _load_config_json(config_path: Path, findings: list[Finding]) -> dict[str, Any]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        findings.append(
            Finding("P0", "CONFIG_MISSING", "Release config file is missing.", str(config_path))
        )
        return {}
    except json.JSONDecodeError as exc:
        findings.append(
            Finding("P0", "CONFIG_JSON_INVALID", f"Release config is not valid JSON: {exc}", str(config_path))
        )
        return {}
    if not isinstance(payload, dict):
        findings.append(
            Finding("P0", "CONFIG_SHAPE_INVALID", "Release config must be a JSON object.", str(config_path))
        )
        return {}
    return payload


def _check_config_loads(config_path: Path, findings: list[Finding]) -> None:
    try:
        from brain_alpha_ops.config import load_run_config

        load_run_config(config_path)
    except Exception as exc:
        findings.append(
            Finding(
                "P0",
                "CONFIG_VALIDATION_FAILED",
                f"Release config cannot be loaded by the runtime validator: {exc}",
                str(config_path),
            )
        )


def _validate_official_context(config_path: Path, findings: list[Finding]) -> dict[str, Any]:
    try:
        from brain_alpha_ops.data.official_context_validation import validate_official_context

        validation = validate_official_context(config_path=config_path)
    except Exception as exc:
        findings.append(
            Finding(
                "P0",
                "OFFICIAL_CONTEXT_VALIDATION_ERROR",
                f"Official context validation failed to run: {exc}",
            )
        )
        return {"ok": False, "error": str(exc)}
    # The lower-level validator distinguishes blocking corruption from
    # audit-only freshness warnings via ``blocking_ok``.  Keep P1 advisories in
    # the returned official_context payload, but only promote blocking context
    # defects into final release findings.
    if validation.get("blocking_ok") is not True:
        for item in validation.get("findings", []):
            severity = str(item.get("severity") or "P0")
            findings.append(
                Finding(
                    "P0" if severity == "BLOCKING" else "P1",
                    f"OFFICIAL_CONTEXT_{str(item.get('code') or 'finding').upper()}",
                    str(item.get("message") or "Official context is not release-clean."),
                    str(item.get("path") or validation.get("data_dir") or ""),
                    current=item,
                )
            )
    return validation


def _check_environment(cfg: dict[str, Any], findings: list[Finding]) -> None:
    environment = str(cfg.get("environment") or "").strip().lower()
    if environment != "production":
        findings.append(
            Finding(
                "P0",
                "ENVIRONMENT_NOT_PRODUCTION",
                "Final release must run with environment=production.",
                "config/run_config.json",
                current=environment,
                expected="production",
            )
        )


def _scan_custom_field_operator_expansion(repo_root: Path, findings: list[Finding]) -> None:
    suspicious: list[str] = []
    for path in _iter_release_source_files(repo_root):
        if _source_registers_custom_field_or_operator(path):
            suspicious.append(path.relative_to(repo_root).as_posix())
    if suspicious:
        findings.append(
            Finding(
                "P0",
                "CUSTOM_FIELD_OPERATOR_RISK",
                "Suspicious custom field/operator extension hooks were found in release source.",
                current=suspicious[:20],
            )
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
    skip_dirs = {
        ".git",
        ".codex_pydeps",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "tests",
    }
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
            files.append(path)
    return sorted(files)


def _check_exact_thresholds(cfg: dict[str, Any], findings: list[Finding]) -> None:
    thresholds = (((cfg.get("ops") or {}).get("thresholds") or {}))
    expected_values = {**CANONICAL_THRESHOLDS, **CANONICAL_RELEASE_REQUIREMENTS}
    for key, expected in expected_values.items():
        current = thresholds.get(key)
        if current != expected:
            findings.append(
                Finding(
                    "P0",
                    f"THRESHOLD_DRIFT_{key.upper()}",
                    f"Threshold {key} differs from the final release baseline.",
                    "config/run_config.json",
                    current=current,
                    expected=expected,
                )
            )


def _check_dataset_redline(repo_root: Path, cfg: dict[str, Any], findings: list[Finding]) -> None:
    ops = cfg.get("ops") or {}
    settings = ops.get("settings") or {}
    budget = ops.get("budget") or {}
    dataset = str(settings.get("dataset") or "").strip()
    strategy = str(budget.get("dataset_strategy") or "").strip().lower()
    if not dataset:
        findings.append(
            Finding(
                "P0",
                "DATASET_ID_EMPTY",
                "Final release requires an explicit settings.dataset value.",
                "config/run_config.json",
                current=dataset,
            )
        )
    if strategy not in RELEASE_DATASET_STRATEGIES:
        findings.append(
            Finding(
                "P0",
                "DATASET_STRATEGY_NOT_FIXED",
                "Final release forbids dynamic dataset rotation/randomization.",
                "config/run_config.json",
                current=strategy,
                expected=sorted(RELEASE_DATASET_STRATEGIES),
            )
        )
    if dataset and dataset not in _official_dataset_ids(repo_root, ops):
        findings.append(
            Finding(
                "P0",
                "DATASET_ID_NOT_IN_OFFICIAL_CONTEXT",
                "Configured dataset must exist in official_datasets.json.",
                "config/run_config.json",
                current=dataset,
            )
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
        findings.append(
            Finding(
                "P1",
                "RUN_FOREVER_ENABLED",
                "Final release requires a bounded run manifest, not run_forever=true.",
                "config/run_config.json",
                current=True,
                expected=False,
            )
        )
    max_cycles = budget.get("max_cycles")
    if not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles <= 0:
        findings.append(
            Finding(
                "P1",
                "MAX_CYCLES_NOT_BOUNDED",
                "Final release requires max_cycles to be a positive integer.",
                "config/run_config.json",
                current=max_cycles,
                expected="positive integer",
            )
        )


def _check_official_context_redline(cfg: dict[str, Any], findings: list[Finding]) -> None:
    ops = cfg.get("ops") or {}
    budget = ops.get("budget") or {}
    api = ops.get("official_api") or {}
    if budget.get("require_cloud_sync") is not True:
        findings.append(
            Finding(
                "P0",
                "CLOUD_SYNC_NOT_REQUIRED",
                "Final release must require cloud synchronization.",
                "config/run_config.json",
                current=budget.get("require_cloud_sync"),
                expected=True,
            )
        )
    if api.get("allow_stale_context_on_rate_limit") is not False:
        findings.append(
            Finding(
                "P0",
                "STALE_CONTEXT_ALLOWED",
                "Final release must fail closed instead of using stale official context.",
                "config/run_config.json",
                current=api.get("allow_stale_context_on_rate_limit"),
                expected=False,
            )
        )


def _check_official_api_alignment(cfg: dict[str, Any], findings: list[Finding]) -> None:
    api = (((cfg.get("ops") or {}).get("official_api") or {}))
    for key, expected in REQUIRED_OFFICIAL_API.items():
        current = api.get(key)
        if current != expected:
            findings.append(
                Finding(
                    "P1",
                    f"OFFICIAL_API_DRIFT_{key.upper()}",
                    f"Official API setting {key} differs from the release baseline.",
                    "config/run_config.json",
                    current=current,
                    expected=expected,
                )
            )


def _official_context_has_fresh_refresh_evidence(official_context: dict[str, Any] | None) -> bool:
    """Accept cache metadata as refresh evidence when a later attempt overwrote status.

    A failed manual refresh can replace ``official_context_refresh_status.json``
    even while all official cache files remain complete, fresh, and sourced from
    the official API.  Final release should fail closed on stale or incomplete
    metadata, but it should not ignore stronger per-file evidence.
    """
    if not isinstance(official_context, dict) or official_context.get("ok") is not True:
        return False
    files = official_context.get("files")
    if not isinstance(files, dict):
        return False
    required = ("official_fields.json", "official_operators.json", "official_datasets.json")
    for filename in required:
        payload = files.get(filename)
        if not isinstance(payload, dict):
            return False
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            return False
        if metadata.get("present") is not True:
            return False
        if metadata.get("source") != "official_api":
            return False
        if metadata.get("complete") is not True:
            return False
        if metadata.get("schema_ok") is not True:
            return False
        if metadata.get("sha256_matches") is not True:
            return False
        if metadata.get("record_count_matches") is not True:
            return False
        if metadata.get("is_stale") is True:
            return False
        if int(payload.get("record_count") or 0) <= 0:
            return False
    return True


def _check_refresh_status(
    repo_root: Path,
    cfg: dict[str, Any],
    findings: list[Finding],
    *,
    official_context: dict[str, Any] | None = None,
) -> None:
    ops = cfg.get("ops") or {}
    storage_dir = Path(str(ops.get("storage_dir") or "data"))
    if not storage_dir.is_absolute():
        storage_dir = repo_root / storage_dir
    status_path = storage_dir / "official_context_refresh_status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        findings.append(
            Finding(
                "P1",
                "OFFICIAL_REFRESH_STATUS_MISSING",
                "Final release requires official_context_refresh_status.json evidence.",
                str(status_path),
            )
        )
        return
    except json.JSONDecodeError as exc:
        findings.append(
            Finding(
                "P1",
                "OFFICIAL_REFRESH_STATUS_INVALID",
                f"official_context_refresh_status.json is invalid JSON: {exc}",
                str(status_path),
            )
        )
        return
    if status.get("ok") is True and str(status.get("status") or "").lower() in {"refreshed", "ok"}:
        return
    if _official_context_has_fresh_refresh_evidence(official_context):
        return
    findings.append(
        Finding(
            "P1",
            "OFFICIAL_REFRESH_NOT_VERIFIED",
            "Final release requires successful official context refresh evidence.",
            str(status_path),
            current={"ok": status.get("ok"), "status": status.get("status")},
            expected={"ok": True, "status": "refreshed"},
        )
    )


def _redline_summary(findings: list[Finding]) -> dict[str, bool]:
    codes = {finding.code for finding in findings}
    return {
        "no_custom_field_operator_extension": "CUSTOM_FIELD_OPERATOR_RISK" not in codes,
        "zero_threshold_drift": not any(code.startswith("THRESHOLD_DRIFT_") for code in codes),
        "dataset_id_fully_available": not any(
            code in {"DATASET_ID_EMPTY", "DATASET_STRATEGY_NOT_FIXED", "DATASET_ID_NOT_IN_OFFICIAL_CONTEXT"}
            or code.startswith("OFFICIAL_CONTEXT_DATASET_")
            for code in codes
        ),
        "full_parameter_traceability": not any(
            code in {"RUN_FOREVER_ENABLED", "MAX_CYCLES_NOT_BOUNDED"} for code in codes
        ),
        "full_factor_coverage": not any(
            code.startswith("OFFICIAL_CONTEXT_") or code in {"CLOUD_SYNC_NOT_REQUIRED", "STALE_CONTEXT_ALLOWED"}
            for code in codes
        ),
        "code_strong_alignment": not any(
            code.startswith("OFFICIAL_API_DRIFT_")
            or code in {
                "CUSTOM_FIELD_OPERATOR_RISK",
                "CONFIG_NOT_LOADABLE",
                "ENVIRONMENT_NOT_PRODUCTION",
                "MANIFEST_FILE_MISSING",
            }
            for code in codes
        ),
        "official_api_alignment": not any(code.startswith("OFFICIAL_API_DRIFT_") for code in codes),
    }


def _build_manifest_hash(
    repo_root: Path, config_path: Path, findings: list[Finding] | None = None
) -> str:
    tracked = [
        config_path,
        repo_root / "pyproject.toml",
        repo_root / "brain_alpha_ops" / "runner.py",
        repo_root / "brain_alpha_ops" / "brain_api" / "official.py",
        repo_root / "brain_alpha_ops" / "research" / "pipeline.py",
        repo_root / "brain_alpha_ops" / "scoring" / "release_score_gate.py",
        repo_root / "brain_alpha_ops" / "web" / "__init__.py",
        repo_root / "scripts" / "final_release_gate.py",
    ]
    digest = hashlib.sha256()
    for path in tracked:
        if not path.exists():
            if findings is not None:
                findings.append(
                    Finding(
                        "P1",
                        "MANIFEST_FILE_MISSING",
                        f"Release manifest file is missing: {path}",
                        str(path),
                    )
                )
            continue
        try:
            path_label = path.relative_to(repo_root).as_posix()
        except ValueError:
            path_label = path.as_posix()
        digest.update(path_label.encode("utf-8", errors="replace"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run final release readiness checks.")
    parser.add_argument("repo_root", nargs="?", default=str(ROOT), help="Repository root.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config to validate.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    report = run_final_release_gate(args.repo_root, config_path=args.config)
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    elif report.passed:
        print(f"Final release gate passed. manifest_hash={report.manifest_hash}")
    else:
        print("Final release gate failed.")
        for finding in report.findings:
            print(f"[{finding.severity}] {finding.code}: {finding.message}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
