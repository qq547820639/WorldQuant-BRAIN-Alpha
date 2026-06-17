"""Cache helpers for the official BRAIN API adapter."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any

from brain_alpha_ops.config import OfficialAPIConfig
from brain_alpha_ops.redaction import redact_error_message, redact_text


logger = logging.getLogger("brain_alpha_ops.brain_api.official")


def cache_key(kind: str, params: dict[str, Any]) -> str:
    raw = json.dumps({"kind": kind, "params": params}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"{kind}_{digest}.json"


def cache_path(config: OfficialAPIConfig, name: str) -> Path:
    return Path(config.cache_dir) / name


def read_cache(
    config: OfficialAPIConfig,
    name: str,
    *,
    cache_path_builder: Any = cache_path,
    log: logging.Logger | None = None,
    cache_lock: threading.Lock | threading.RLock | None = None,
) -> dict[str, Any]:
    active_logger = log or logger
    path = cache_path_builder(config, name)

    def _do_read() -> dict[str, Any]:
        if not path.exists():
            return {"items": [], "fresh": False, "missing": True}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - float(data.get("created_at", 0.0))
            return {
                "items": data.get("items", []),
                "total": int(data.get("total", 0) or 0),
                "fresh": age <= max(0, int(config.context_cache_ttl_seconds)),
                "age_seconds": max(0, int(age)),
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            active_logger.warning("failed to read official API cache %s: %s", redact_text(path, max_length=180), redact_error_message(exc))
            return {"items": [], "fresh": False, "error": redact_error_message(exc)}

    if cache_lock is not None:
        with cache_lock:
            return _do_read()
    return _do_read()


def write_cache(
    config: OfficialAPIConfig,
    cache_lock: threading.Lock | threading.RLock,
    name: str,
    items: list[dict[str, Any]],
    total: int = 0,
    *,
    cache_path_builder: Any = cache_path,
    log: logging.Logger | None = None,
) -> None:
    active_logger = log or logger
    path = cache_path_builder(config, name)
    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"created_at": time.time(), "items": items, "total": int(total or len(items))},
            ensure_ascii=False,
            indent=2,
        )
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with cache_lock:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
    except OSError as exc:
        active_logger.warning(
            "failed to write official API cache %s: %s",
            redact_text(path, max_length=180),
            redact_error_message(exc),
        )
        if tmp is not None:
            try:
                tmp.unlink()
            except Exception as cleanup_exc:
                active_logger.debug(
                    "failed to remove temporary cache file %s: %s",
                    redact_text(tmp, max_length=180),
                    redact_error_message(cleanup_exc),
                )
