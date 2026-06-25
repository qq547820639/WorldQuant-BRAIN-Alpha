"""Official context persistence (writing) helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.data.cache_metadata import write_context_cache_metadata
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runtime_constants import CloudDefaults

from ._constants import LoadConfig, RuntimeRoot, SafeErrorMessage, _safe_error_message

logger = logging.getLogger(__name__)


def persist_official_context(
    fields: list[dict[str, Any]],
    operators: list[dict[str, Any]],
    datasets: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> None:
    if fields:
        save_official_context_json(
            "official_fields.json",
            fields,
            load_config=load_config,
            runtime_root=runtime_root,
        )
    if operators:
        save_official_context_json(
            "official_operators.json",
            operators,
            load_config=load_config,
            runtime_root=runtime_root,
        )
    if datasets:
        save_official_context_json(
            "official_datasets.json",
            datasets,
            load_config=load_config,
            runtime_root=runtime_root,
        )
    if fields or operators or datasets:
        from brain_alpha_ops.data.loader import OfficialDataLoader

        try:
            data_dir = str(Path(load_config().ops.storage_dir))
        except Exception as exc:
            logger.warning("failed to resolve configured storage dir after official context persist: %s", safe_error_message(exc))
            data_dir = CloudDefaults.OFFICIAL_CONTEXT_DATA_DIR
        OfficialDataLoader.instance().refresh(data_dir)


def save_official_context_json(
    filename: str,
    items: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
) -> None:
    ttl_seconds = CloudDefaults.CONTEXT_CACHE_TTL_SECONDS
    try:
        run_config = load_config()
        data_dir = Path(run_config.ops.storage_dir)
        ttl_seconds = int(run_config.ops.official_api.context_cache_ttl_seconds)
    except Exception as exc:
        logger.warning(
            "failed to resolve configured storage dir while saving official context: %s; falling back to runtime root",
            redact_error_message(exc),
        )
        data_dir = runtime_root() / CloudDefaults.OFFICIAL_CONTEXT_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / filename
    tmp = data_dir / f".{filename}.tmp"
    tmp.write_text(json.dumps(items, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(target)
    write_context_cache_metadata(
        target,
        items,
        source="official_api",
        ttl_seconds=ttl_seconds,
    )
