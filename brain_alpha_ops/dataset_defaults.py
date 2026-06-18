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
    """Return a stable official dataset id from the official dataset cache.

    Missing or invalid official metadata is a production configuration error,
    not a reason to invent a dataset id locally.
    """
    root = Path(storage_dir)
    if not root.is_absolute():
        root = (runtime_root or Path.cwd)() / root
    dataset_path = root / "official_datasets.json"
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"official dataset cache is unavailable: {dataset_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"official dataset cache is not valid JSON: {dataset_path}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"official dataset cache must be a list: {dataset_path}")
    ids = [
        str(row.get("id") or "").strip()
        for row in payload
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    ]
    if not ids:
        raise ValueError(f"official dataset cache contains no dataset ids: {dataset_path}")
    if DEFAULT_DATASET_ID in ids:
        return DEFAULT_DATASET_ID
    return ids[0]
