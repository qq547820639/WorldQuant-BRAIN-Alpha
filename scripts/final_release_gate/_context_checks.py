"""Official-context, capability-registry, and refresh-status redline checks.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Covers the official context cache
redline, capability registry alignment, official-context file completeness
predicates, and refresh-status evidence checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._models import (
    OFFICIAL_CONTEXT_FILES,
    OFFICIAL_CONTEXT_REQUIRED_METADATA,
    Finding,
    _add_finding,
)


def _check_official_context_redline(
    cfg: dict[str, Any],
    findings: list[Finding],
    *,
    official_context: dict[str, Any],
) -> None:
    ops = cfg.get("ops") or {}
    budget = ops.get("budget") or {}
    api = ops.get("official_api") or {}
    if budget.get("require_cloud_sync") is not True and not _official_context_cache_complete(official_context):
        _add_finding(
            findings,
            "P0",
            "CLOUD_SYNC_CACHE_MISSING",
            "Final release requires either forced cloud sync or a complete official context cache.",
            "config/run_config.json",
            current=budget.get("require_cloud_sync"),
            expected="require_cloud_sync=true or complete official context cache",
        )
    if api.get("allow_stale_context_on_rate_limit") is not False:
        _add_finding(
            findings,
            "P0",
            "STALE_CONTEXT_ALLOWED",
            "Final release must fail closed instead of using stale official context.",
            "config/run_config.json",
            current=api.get("allow_stale_context_on_rate_limit"),
            expected=False,
        )


def _official_context_cache_complete(official_context: dict[str, Any]) -> bool:
    if official_context.get("blocking_ok") is not True:
        return False
    return _official_context_files_complete(official_context, require_fresh=False)


def _check_capability_registry_redline(findings: list[Finding]) -> None:
    try:
        from brain_alpha_ops.web_capability_registry import check_capability_registry
        from brain_alpha_ops.web_cloud.snapshot import official_context_file_counts
        from brain_alpha_ops.web_config_schema import public_config_schema

        result = check_capability_registry(
            public_config_schema=public_config_schema,
            official_context_file_counts=official_context_file_counts,
        )
    except Exception as exc:
        _add_finding(
            findings,
            "P0",
            "CAPABILITY_REGISTRY_CHECK_ERROR",
            f"Capability registry validation failed to run: {exc}",
        )
        return
    if result.get("ok") is True:
        return
    for item in result.get("findings", []):
        severity = str(item.get("severity") or "P0")
        _add_finding(
            findings,
            "P0" if severity == "P0" else "P1",
            f"CAPABILITY_REGISTRY_{str(item.get('code') or 'finding').upper()}",
            str(item.get("message") or "Capability registry is not aligned."),
            current=item.get("evidence"),
            expected="canonical settings, config schema, and local official cache aligned",
        )


def _official_context_has_fresh_refresh_evidence(official_context: dict[str, Any] | None) -> bool:
    """Accept complete fresh file metadata when refresh status was overwritten."""
    if not isinstance(official_context, dict) or official_context.get("ok") is not True:
        return False
    return _official_context_files_complete(official_context, require_fresh=True)


def _official_context_files_complete(official_context: dict[str, Any], *, require_fresh: bool) -> bool:
    files = official_context.get("files")
    if not isinstance(files, dict):
        return False
    for filename in OFFICIAL_CONTEXT_FILES:
        payload = files.get(filename)
        if not isinstance(payload, dict):
            return False
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            return False
        if not all(metadata.get(flag) is True for flag in OFFICIAL_CONTEXT_REQUIRED_METADATA):
            return False
        record_source = payload if require_fresh else metadata
        if int(record_source.get("record_count") or 0) <= 0:
            return False
        if require_fresh and (
            metadata.get("present") is not True
            or metadata.get("source") != "official_api"
            or metadata.get("is_stale") is True
        ):
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
        _add_finding(
            findings,
            "P1",
            "OFFICIAL_REFRESH_STATUS_MISSING",
            "Final release requires official_context_refresh_status.json evidence.",
            str(status_path),
        )
        return
    except json.JSONDecodeError as exc:
        _add_finding(
            findings,
            "P1",
            "OFFICIAL_REFRESH_STATUS_INVALID",
            f"official_context_refresh_status.json is invalid JSON: {exc}",
            str(status_path),
        )
        return
    if status.get("ok") is True and str(status.get("status") or "").lower() in {"refreshed", "ok"}:
        return
    if _official_context_has_fresh_refresh_evidence(official_context):
        return
    _add_finding(
        findings,
        "P1",
        "OFFICIAL_REFRESH_NOT_VERIFIED",
        "Final release requires successful official context refresh evidence.",
        str(status_path),
        current={"ok": status.get("ok"), "status": status.get("status")},
        expected={"ok": True, "status": "refreshed"},
    )
