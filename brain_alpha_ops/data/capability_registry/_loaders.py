"""Build a CapabilityRegistry from the official_*.json context files.

Reads ``data/official_fields.json``, ``official_operators.json``, and
``official_datasets.json`` and converts each row into a CapabilityEntry.

Logger name is hardcoded to ``brain_alpha_ops.data.capability_registry._loaders``
to preserve module identity after the split.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.data.capability_registry._types import (
    CapabilityEntry,
    CapabilityKind,
    CapabilityRegistry,
)

logger = logging.getLogger("brain_alpha_ops.data.capability_registry._loaders")

OFFICIAL_FILES: dict[str, CapabilityKind] = {
    "official_fields.json": "field",
    "official_operators.json": "operator",
    "official_datasets.json": "dataset",
}


def build_registry_from_official_context(data_dir: Path) -> CapabilityRegistry:
    """Build a registry from the three official_*.json files in *data_dir*.

    Each JSON row becomes one CapabilityEntry. Missing files are logged and
    skipped; the resulting registry simply has no entries of that kind. The
    caller (typically ``get_registry()``) decides whether an empty kind is a
    hard error or an acceptable degraded state.
    """
    root = Path(data_dir)
    entries: list[CapabilityEntry] = []

    for filename, kind in OFFICIAL_FILES.items():
        path = root / filename
        rows = _read_json_list(path)
        if rows is None:
            logger.warning("capability_registry: %s missing or unreadable", path)
            continue
        for row in rows:
            entry = _row_to_entry(row, kind, str(path))
            if entry is not None:
                entries.append(entry)

    return CapabilityRegistry(
        entries=tuple(entries),
        built_at=datetime.now(timezone.utc).isoformat(),
        source_tag="official_context",
    )


def _read_json_list(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("capability_registry: failed to parse %s: %s", path, exc)
        return None
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


def _row_to_entry(
    row: dict[str, Any],
    kind: CapabilityKind,
    source: str,
) -> CapabilityEntry | None:
    name = str(row.get("id") or row.get("name") or "").strip()
    if not name:
        return None
    updated_at = str(row.get("dateUpdated") or row.get("saved_at") or "")
    scope = _scope_from_row(row, kind)
    allowed: tuple[Any, ...] = (name,)
    rule_id = f"official_context:{kind}"
    hint = _error_hint_for(kind, name)
    return CapabilityEntry(
        name=name,
        kind=kind,
        source=source,
        updated_at=updated_at,
        scope=scope,
        default_value=None,
        allowed_values=frozenset(allowed),
        forbidden_values=(),
        validation_rule=rule_id,
        error_hint=hint,
    )


def _scope_from_row(row: dict[str, Any], kind: CapabilityKind) -> tuple[str, ...]:
    """Extract scope parts from a row.

    For field entries, the category and dataset_id are included so the
    registry can answer "which fields belong to category X?" without
    callers needing to re-read the official_*.json files. For other
    kinds, only region/universe are included (legacy behavior).
    """
    if kind == "field":
        category = str(row.get("category") or "").strip().lower()
        dataset_id = str(row.get("dataset_id") or "").strip().lower()
        parts = [part for part in (category, dataset_id) if part]
        return tuple(parts)
    region = str(row.get("region") or "").strip()
    universe = str(row.get("universe") or "").strip()
    parts = [part for part in (region, universe) if part]
    return tuple(parts)


def _error_hint_for(kind: CapabilityKind, name: str) -> str:
    return (
        f"{kind} {name!r} is not present in the official BRAIN context cache; "
        "needs human confirmation before extension"
    )


__all__ = ["build_registry_from_official_context", "OFFICIAL_FILES"]
