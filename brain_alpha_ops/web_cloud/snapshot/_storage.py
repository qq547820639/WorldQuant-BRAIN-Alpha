"""Storage path and JSONL read helpers for the snapshot subpackage."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.jsonl import read_jsonl_records, read_jsonl_tail_with_stats

from ._constants import LoadConfig, RuntimeRoot, SafeErrorMessage


def storage_jsonl_path(filename: str, *, load_config: LoadConfig = load_run_config) -> Path:
    config = load_config()
    return Path(config.ops.storage_dir) / filename


def read_storage_jsonl(filename: str, *, limit: int | None = 500, load_config: LoadConfig = load_run_config) -> list[dict[str, Any]]:
    # When limit=None the caller explicitly wants ALL records — pass max_rows=None
    # to read_jsonl_records to remove the safety cap. The caller (e.g. cloud
    # alpha snapshot) is expected to have enough memory for the full dataset.
    max_rows: int | None = None if limit is None else limit or 10_000
    return read_jsonl_records(storage_jsonl_path(filename, load_config=load_config), limit=limit, max_rows=max_rows)


def read_storage_jsonl_stats(filename: str, *, limit: int = 500, load_config: LoadConfig = load_run_config) -> dict[str, Any]:
    return read_jsonl_tail_with_stats(storage_jsonl_path(filename, load_config=load_config), limit=limit).to_dict()


def path_modified_at(path: Path | None) -> tuple[str, int | None]:
    if not path:
        return "", None
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return "", None
    return datetime.fromtimestamp(modified_at, timezone.utc).isoformat(), max(0, int(time.time() - modified_at))


def extract_alpha_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "alphas", "data", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []
