"""Config loading and official-context validation helpers.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Resolves paths under the repo root,
loads the release config JSON, runs the runtime config validator, and
delegates official-context validation to ``brain_alpha_ops.data``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._models import Finding, _add_finding


def _resolve_under_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _load_config_json(config_path: Path, findings: list[Finding]) -> dict[str, Any]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        _add_finding(findings, "P0", "CONFIG_MISSING", "Release config file is missing.", str(config_path))
        return {}
    except json.JSONDecodeError as exc:
        _add_finding(findings, "P0", "CONFIG_JSON_INVALID", f"Release config is not valid JSON: {exc}", str(config_path))
        return {}
    if not isinstance(payload, dict):
        _add_finding(findings, "P0", "CONFIG_SHAPE_INVALID", "Release config must be a JSON object.", str(config_path))
        return {}
    return payload


def _check_config_loads(config_path: Path, findings: list[Finding]) -> None:
    try:
        from brain_alpha_ops.config import load_run_config

        load_run_config(config_path)
    except Exception as exc:
        _add_finding(
            findings,
            "P0",
            "CONFIG_VALIDATION_FAILED",
            f"Release config cannot be loaded by the runtime validator: {exc}",
            str(config_path),
        )


def _validate_official_context(config_path: Path, findings: list[Finding]) -> dict[str, Any]:
    try:
        from brain_alpha_ops.data.official_context_validation import validate_official_context

        validation = validate_official_context(config_path=config_path)
    except Exception as exc:
        _add_finding(findings, "P0", "OFFICIAL_CONTEXT_VALIDATION_ERROR", f"Official context validation failed to run: {exc}")
        return {"ok": False, "error": str(exc)}
    # The lower-level validator distinguishes blocking corruption from
    # audit-only freshness warnings via ``blocking_ok``.  Keep P1 advisories in
    # the returned official_context payload, but only promote blocking context
    # defects into final release findings.
    if validation.get("blocking_ok") is not True:
        for item in validation.get("findings", []):
            severity = str(item.get("severity") or "P0")
            _add_finding(
                findings,
                "P0" if severity == "BLOCKING" else "P1",
                f"OFFICIAL_CONTEXT_{str(item.get('code') or 'finding').upper()}",
                str(item.get("message") or "Official context is not release-clean."),
                str(item.get("path") or validation.get("data_dir") or ""),
                current=item,
            )
    return validation
