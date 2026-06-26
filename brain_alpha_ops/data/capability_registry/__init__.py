"""BRAIN capability registry — central source of truth for fields, operators,
datasets, regions, universes, delays, decays, neutralizations, truncations,
pasteurizations, NaN handling, unit handling, test periods, and visualization
settings.

The registry is intentionally offline. It reads the local
``data/official_*.json`` cache and combines it with the canonical BrainSettings
defaults. When a capability is missing or ambiguous, callers receive a
``CapabilityResolutionError`` so the upstream can surface a "needs human
confirmation" state instead of guessing.

Logger name is hardcoded to preserve module identity after the split.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import runtime_project_root
from brain_alpha_ops.data.capability_registry._defaults import (
    build_default_capability_entries,
)
from brain_alpha_ops.data.capability_registry._loaders import (
    OFFICIAL_FILES,
    build_registry_from_official_context,
)
from brain_alpha_ops.data.capability_registry._types import (
    CapabilityEntry,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResolutionError,
)

logger = logging.getLogger("brain_alpha_ops.data.capability_registry")

_REGISTRY_LOCK = threading.Lock()
_REGISTRY_INSTANCE: CapabilityRegistry | None = None


def get_registry() -> CapabilityRegistry:
    """Return the singleton CapabilityRegistry.

    Lazy-loaded and thread-safe via a module-level lock. The first call
    builds the registry from the local ``data/official_*.json`` cache plus
    the canonical BrainSettings defaults; subsequent calls return the cached
    instance.

    Subsequent calls return the cached instance. Use :func:`reset_registry`
    to force a rebuild (used by tests and registry refreshes).
    """
    global _REGISTRY_INSTANCE
    if _REGISTRY_INSTANCE is not None:
        return _REGISTRY_INSTANCE
    with _REGISTRY_LOCK:
        if _REGISTRY_INSTANCE is not None:
            return _REGISTRY_INSTANCE
        _REGISTRY_INSTANCE = _build_default_registry()
        return _REGISTRY_INSTANCE


def reset_registry() -> None:
    """Clear the cached singleton (used by tests and registry refreshes)."""
    global _REGISTRY_INSTANCE
    with _REGISTRY_LOCK:
        _REGISTRY_INSTANCE = None


def _build_default_registry() -> CapabilityRegistry:
    """Build the default registry: official context + BrainSettings defaults."""
    entries: list[CapabilityEntry] = list(build_default_capability_entries())
    built_at = datetime.now(timezone.utc).isoformat()
    try:
        data_dir = _resolve_data_dir()
        registry = build_registry_from_official_context(data_dir)
        entries.extend(registry.entries)
        if registry.built_at:
            built_at = registry.built_at
    except Exception as exc:
        logger.warning(
            "capability_registry: failed to load official context: %s", exc
        )
    return CapabilityRegistry(
        entries=tuple(entries),
        built_at=built_at,
        source_tag="official_context+brain_settings_defaults",
    )


def _resolve_data_dir() -> Path:
    """Resolve the official context data dir relative to the project root."""
    try:
        root = runtime_project_root()
    except Exception:
        root = Path.cwd()
    return (root / "data").resolve()


__all__ = [
    "CapabilityEntry",
    "CapabilityKind",
    "CapabilityRegistry",
    "CapabilityResolutionError",
    "OFFICIAL_FILES",
    "build_default_capability_entries",
    "build_registry_from_official_context",
    "get_registry",
    "reset_registry",
]
