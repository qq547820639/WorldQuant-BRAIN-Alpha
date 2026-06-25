"""Cached user-alpha path enumeration and loading helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_text

from ._constants import LoadConfig
from ._storage import extract_alpha_rows

logger = logging.getLogger(__name__)


def latest_cached_user_alphas(
    limit: int | None = None,
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> list[dict[str, Any]]:
    for path in cached_user_alpha_paths(load_config=load_config, max_files=max_files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read cached user alpha file %s", redact_text(path, max_length=180))
            continue
        rows = extract_alpha_rows(data)
        if rows:
            return rows if limit is None else rows[-max(1, int(limit or 1)):]
    return []


def latest_cached_user_alpha_path(
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> Path | None:
    for path in cached_user_alpha_paths(load_config=load_config, max_files=max_files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read cached user alpha file %s", redact_text(path, max_length=180))
            continue
        if extract_alpha_rows(data):
            return path
    return None


def cached_user_alpha_paths(
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> list[Path]:
    config = load_config()
    cache_dir = Path(config.ops.official_api.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path.cwd() / cache_dir
    try:
        candidates = []
        for path in cache_dir.glob("user_alphas_*.json"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        ordered = [path for _mtime, path in sorted(candidates, reverse=True)]
        if max_files is None:
            return ordered
        return ordered[: max(1, int(max_files or 1))]
    except OSError:
        logger.warning("failed to list cached user alpha files from %s", redact_text(cache_dir, max_length=180))
        return []
