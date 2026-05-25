"""Dataset default resolution helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


DEFAULT_DATASET_ID = "pv1"


def resolve_default_dataset_id(
    storage_dir: str | Path = "data",
    *,
    runtime_root: Callable[[], Path] | None = None,
) -> str:
    """Return a stable official dataset id for explicit default configuration."""
    root = Path(storage_dir)
    if not root.is_absolute():
        root = (runtime_root or Path.cwd)() / root
    dataset_path = root / "official_datasets.json"
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_DATASET_ID
    if not isinstance(payload, list):
        return DEFAULT_DATASET_ID
    ids = [
        str(row.get("id") or "").strip()
        for row in payload
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    ]
    if DEFAULT_DATASET_ID in ids:
        return DEFAULT_DATASET_ID
    return ids[0] if ids else DEFAULT_DATASET_ID
