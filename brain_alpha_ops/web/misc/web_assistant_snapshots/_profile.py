"""Latest run-history path lookup and user profile snapshot."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message, redact_text

from ._helpers import (
    LoadConfig,
    SafeErrorMessage,
    StoragePath,
    logger,
)


def latest_run_history_path(*, load_config: LoadConfig = load_run_config) -> Path | None:
    history_dir = Path(load_config().ops.storage_dir) / "run_history"
    try:
        files = [path for path in history_dir.glob("*.json") if path.is_file()]
    except Exception:
        logger.warning("failed to list run history files from %s", history_dir, exc_info=True)
        return None
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def user_profile_snapshot(
    *,
    job_store: Any,
    storage_jsonl_path: StoragePath,
    safe_error_message: SafeErrorMessage = redact_error_message,
) -> dict[str, Any]:
    active = job_store.latest_active()
    if not active:
        profile_path = storage_jsonl_path("user_profile.json")
        if profile_path.exists():
            try:
                return json.loads(profile_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(
                    "failed to read user profile from %s: %s",
                    redact_text(profile_path, max_length=180),
                    safe_error_message(exc),
                )
        return {"tier": "offline", "level": None, "points": None, "username": ""}

    _job_id, job = active
    progress = job.get("progress") or {}
    data = progress.get("data") or {}
    result = job.get("result") or {}
    summary = result.get("summary") or {}
    profile = (
        data.get("user_profile")
        or summary.get("user_profile")
        or {"tier": "loading", "level": None, "points": None}
    )
    return profile
