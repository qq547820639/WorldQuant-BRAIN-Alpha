"""Refresh official BRAIN fields, operators, and datasets.

This maintenance entry point uses the same OfficialBrainAPI adapter and
official-context persistence helpers as the Web console. It never prints
credentials, tokens, cookies, or raw authentication responses.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from typing import Any

from brain_alpha_ops.brain_api.official import OfficialBrainAPI
from brain_alpha_ops.config import DEFAULT_RUN_CONFIG_PATH, RunConfig, load_run_config
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_cloud_snapshot import (
    datasets_from_fields,
    official_context_file_counts,
    persist_official_context,
)


STATUS_FILENAME = "official_context_refresh_status.json"
SCHEMA_VERSION = "official_context_refresh.v1"


def refresh_official_context(
    config_path: str | Path | None = None,
    *,
    write: bool = True,
    status_output: str | Path | None = None,
    write_status: bool = True,
) -> dict[str, Any]:
    """Fetch official context and optionally persist it into configured storage."""
    run_config = load_run_config(config_path)
    started_at = datetime.now(timezone.utc).isoformat()
    status_path = _status_output_path(run_config, status_output) if write_status else None
    before = official_context_file_counts(load_config=lambda: run_config)

    try:
        _require_credentials(run_config)
        with _api_cache_scope(run_config, write=write) as api_config:
            api = OfficialBrainAPI(api_config, **run_config.credentials.resolve())
            api.set_market_scope(run_config.ops.settings)
            auth = api.authenticate()
            progress: dict[str, list[dict[str, Any]]] = {"fields": [], "operators": [], "datasets": []}
            fields = api.list_fields("all", run_config.ops.settings.region, progress_callback=_progress(progress, "fields"))
            if not fields:
                raise RuntimeError("official data-fields refresh returned zero records")
            operators = api.list_operators("all", progress_callback=_progress(progress, "operators"))
            if not operators:
                raise RuntimeError("official operators refresh returned zero records")
            datasets = list_official_datasets_or_derive(
                api,
                fields,
                region=run_config.ops.settings.region,
                datasets_from_fields=lambda rows: datasets_from_fields(rows, load_config=lambda: run_config),
            )
            if not datasets:
                raise RuntimeError("official data-sets refresh returned zero records")
            if write:
                persist_official_context(
                    fields,
                    operators,
                    datasets,
                    load_config=lambda: run_config,
                )
            after = official_context_file_counts(load_config=lambda: run_config)
            result = _base_result(run_config, started_at, status_path, write=write)
            result.update(
                {
                    "ok": True,
                    "status": "refreshed" if write else "fetched_no_write",
                    "auth": _safe_auth_summary(auth),
                    "counts": {
                        "fields": len(fields),
                        "operators": len(operators),
                        "datasets": len(datasets),
                    },
                    "before": _context_counts(before),
                    "after": _context_counts(after),
                    "progress": _compact_progress(progress),
                }
            )
            _write_status_file(status_path, result)
            return result
    except Exception as exc:
        retry_after = _retry_after_seconds(exc)
        result = _base_result(run_config, started_at, status_path, write=write)
        result.update(
            {
                "ok": False,
                "status": "failed",
                "error_code": _error_code(exc, run_config),
                "error_category": _error_category(exc, run_config),
                "retryable": _retryable(exc),
                "retry_after_seconds": retry_after,
                "next_retry_at": _next_retry_at(retry_after) if retry_after is not None else "",
                "error": redact_error_message(exc),
                "before": _context_counts(before),
                "after": _context_counts(official_context_file_counts(load_config=lambda: run_config)),
            }
        )
        _write_status_file(status_path, result)
        return result


class _api_cache_scope:
    def __init__(self, run_config: RunConfig, *, write: bool):
        self.run_config = run_config
        self.write = write
        self._tmp: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self):
        api_config = deepcopy(self.run_config.ops.official_api)
        if not self.write:
            self._tmp = tempfile.TemporaryDirectory(prefix="brain_alpha_context_")
            api_config.cache_dir = self._tmp.name
        return api_config

    def __exit__(self, *_args):
        if self._tmp is not None:
            self._tmp.cleanup()
        return False


def _progress(progress: dict[str, list[dict[str, Any]]], key: str):
    def _record(event: dict[str, Any]) -> None:
        progress.setdefault(key, []).append(dict(event))

    return _record


def _base_result(run_config: RunConfig, started_at: str, status_path: Path | None, *, write: bool) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "started_at": started_at,
        "environment": run_config.environment,
        "storage_dir": run_config.ops.storage_dir,
        "base_url": run_config.ops.official_api.base_url,
        "region": run_config.ops.settings.region,
        "universe": run_config.ops.settings.universe,
        "delay": run_config.ops.settings.delay,
        "write_enabled": bool(write),
        "status_path": str(status_path or ""),
    }


def _require_credentials(run_config: RunConfig) -> None:
    credentials = run_config.credentials.resolve()
    has_token = bool(credentials.get("token"))
    has_basic = bool(credentials.get("username") and credentials.get("password"))
    if not has_token and not has_basic:
        raise RuntimeError("BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN environment variables are required")


def _error_code(exc: Exception, run_config: RunConfig) -> str:
    if "environment variables are required" in str(exc):
        return "MISSING_CREDENTIALS"
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code:
        return f"HTTP_{status_code}"
    return "OFFICIAL_CONTEXT_REFRESH_FAILED"


def _error_category(exc: Exception, run_config: RunConfig) -> str:
    code = _error_code(exc, run_config)
    if code == "RATE_LIMITED":
        return "rate_limit"
    if code == "MISSING_CREDENTIALS":
        return "auth"
    if code.startswith("HTTP_"):
        return "http"
    return "internal"


def _retryable(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 429, 500, 502, 503, 504}:
        return True
    return "rate limit" in str(exc).lower()


def _retry_after_seconds(exc: Exception) -> float | None:
    value = getattr(exc, "retry_after", None)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 0.0
    if parsed > 0:
        return parsed
    if getattr(exc, "status_code", None) == 429 or "rate limit" in str(exc).lower():
        return 15 * 60
    return None


def _next_retry_at(retry_after_seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, retry_after_seconds))).isoformat()


def _status_output_path(run_config: RunConfig, override: str | Path | None) -> Path:
    if override:
        return Path(override)
    return Path(run_config.ops.storage_dir) / STATUS_FILENAME


def _write_status_file(path: Path | None, result: dict[str, Any]) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        result["status_write_error"] = redact_error_message(exc)


def _context_counts(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "fields": int(payload.get("fields_count", 0) or 0),
        "operators": int(payload.get("operators_count", 0) or 0),
        "datasets": int(payload.get("datasets_count", 0) or 0),
        "manifest_complete": bool((payload.get("context_cache_manifest") or {}).get("complete")),
        "manifest_stale": bool((payload.get("context_cache_manifest") or {}).get("is_stale")),
    }


def _compact_progress(progress: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, rows in progress.items():
        latest = rows[-1] if rows else {}
        compact[key] = {
            "events": len(rows),
            "scanned": latest.get("scanned", 0),
            "total": latest.get("total", 0),
            "cached": bool(latest.get("cached")),
            "truncated": bool(latest.get("truncated")),
            "warning": str(latest.get("warning") or ""),
        }
    return compact


def _safe_auth_summary(auth: Any) -> dict[str, Any]:
    payload = auth if isinstance(auth, dict) else {}
    return {
        "status": payload.get("status", ""),
        "auth": payload.get("auth", ""),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh official WorldQuant BRAIN context files.")
    parser.add_argument("--config", default=str(DEFAULT_RUN_CONFIG_PATH), help="Run config path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--no-write", action="store_true", help="Fetch and compare without overwriting official context JSON files.")
    parser.add_argument("--status-output", default="", help="Optional non-sensitive refresh status JSON path.")
    parser.add_argument("--no-status-file", action="store_true", help="Do not write the refresh status JSON file.")
    args = parser.parse_args(argv)

    result = refresh_official_context(
        args.config,
        write=not args.no_write,
        status_output=args.status_output or None,
        write_status=not args.no_status_file,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        status = "PASS" if result.get("ok") else "FAIL"
        counts = result.get("counts") or {}
        print(f"[{status}] official context refresh: {result.get('status')}")
        print(f"fields={counts.get('fields', 0)} operators={counts.get('operators', 0)} datasets={counts.get('datasets', 0)}")
        if result.get("error"):
            print(f"error={result['error']}")
        if result.get("status_path"):
            print(f"status={result['status_path']}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
