"""Singleton loader for official WorldQuant BRAIN context (fields, operators, datasets).

Loads ``data/official_*.json`` into memory on first access.  All other modules
query this loader instead of using hard-coded lists.

Usage::

    from brain_alpha_ops.data import OfficialDataLoader
    loader = OfficialDataLoader.instance()
    fields = loader.get_fields(dataset_id="analyst4")

Subpackage of ``brain_alpha_ops.data``. Splits the original ``loader.py``
monolith into focused modules while preserving the public API surface via
re-exports.
"""
from __future__ import annotations

# Re-export runtime_project_root on the package so tests can monkeypatch it:
#   monkeypatch.setattr("brain_alpha_ops.data.loader.runtime_project_root", ...)
from brain_alpha_ops.config import runtime_project_root  # noqa: F401

# Constants
from ._state import (
    PACKAGED_OFFICIAL_CONTEXT_FILES,
    REQUIRED_OFFICIAL_CONTEXT_FILES,
    SUPPLEMENTAL_OFFICIAL_CONTEXT_FILES,
    ensure_official_context_files,
)

# Loader class (combining base + refresh mixin)
from ._loader import OfficialDataLoaderBase
from ._refresh import _RefreshMixin


class OfficialDataLoader(OfficialDataLoaderBase, _RefreshMixin):
    """Singleton that loads official_fields/operators/datasets JSON files on first use.

    Combines the base loading/query logic from :class:`OfficialDataLoaderBase`
    with the refresh/staleness methods from :class:`_RefreshMixin`.
    """
    pass


__all__ = [
    "OfficialDataLoader",
    "PACKAGED_OFFICIAL_CONTEXT_FILES",
    "REQUIRED_OFFICIAL_CONTEXT_FILES",
    "SUPPLEMENTAL_OFFICIAL_CONTEXT_FILES",
    "ensure_official_context_files",
    "runtime_project_root",
]
