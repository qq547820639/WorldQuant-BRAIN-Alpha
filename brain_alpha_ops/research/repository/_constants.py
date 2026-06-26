"""Module-level constants, logger, and helper functions for the repository package."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.expression_ast import expression_profile_summary

# Hardcoded logger name to preserve the original module's logger identity
# (originally ``logging.getLogger(__name__)`` where __name__ was
# ``brain_alpha_ops.research.repository``).
logger = logging.getLogger("brain_alpha_ops.research.repository")

_LOCK_STALE_SECONDS = 120.0
_LOCK_POLL_SECONDS = 0.05
_EXPRESSION_INDEXED_FILES = {
    "candidates.jsonl",
    "lifecycle.jsonl",
    "checks.jsonl",
    "backtests.jsonl",
    "submissions.jsonl",
    "cloud_alphas.jsonl",
}
_RECORD_INDEXED_FILES = {
    "cloud_alphas.jsonl",
    "backtests.jsonl",
}
_SQLITE_INDEX_DIAGNOSTICS_FILE = "sqlite_index_diagnostics.jsonl"
_REPOSITORY_JSONL_FILES = _EXPRESSION_INDEXED_FILES | _RECORD_INDEXED_FILES | {
    "ab_tests.jsonl",
    "assistant_guidance.jsonl",
    "events.jsonl",
    "families.jsonl",
    _SQLITE_INDEX_DIAGNOSTICS_FILE,
    "strategy_lifecycle.jsonl",
}
_REPOSITORY_LOCK_NAMES = _REPOSITORY_JSONL_FILES | {"run_history"}


def _cloud_alpha_id(row: dict[str, Any] | None) -> str:
    row = row or {}
    return str(row.get("id") or row.get("alpha_id") or "")


def _cloud_record_hash(row: dict[str, Any] | None) -> str:
    row = row or {}
    volatile = {"timestamp", "synced_at", "sync_range", "cloud_record_hash"}
    stable = {key: value for key, value in row.items() if key not in volatile}
    payload = json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _with_expression_summary(record: dict[str, Any]) -> dict[str, Any]:
    expression = str(record.get("expression") or "")
    if not expression:
        candidate = record.get("candidate")
        if isinstance(candidate, dict):
            expression = str(candidate.get("expression") or "")
    if not expression:
        return record
    return {**record, **expression_profile_summary(expression)}


def _repository_safe(record: dict[str, Any]) -> dict[str, Any]:
    clean = redact_data(record)
    return clean if isinstance(clean, dict) else {}


def _ensure_contained(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"repository path escapes storage root: {path}") from None
