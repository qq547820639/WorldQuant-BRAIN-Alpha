"""Official-context defaults sourced from data/official_*.json via OfficialDataLoader.

Backward-compatible: DEFAULT_FIELDS and DEFAULT_OPERATORS are still list-of-dict
module-level names, but populated from the official JSON files at first access.
"""

from __future__ import annotations

from typing import List

# Lazy-loaded caches — populated on first access
_DEFAULTS_CACHE: dict = {"fields": [], "operators": []}
_LOADED: bool = False


def _ensure_loaded() -> None:
    """Populate caches from OfficialDataLoader on first call."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        from brain_alpha_ops.data import OfficialDataLoader

        loader = OfficialDataLoader.instance()

        _DEFAULTS_CACHE["fields"] = [
            {
                "name": f.id,
                "category": f.category,
                "delay": f.delay,
                "coverage": f.coverage,
                "source": "official_fields.json",
            }
            for f in loader.get_fields()
        ]

        _DEFAULTS_CACHE["operators"] = [
            {
                "name": op.name,
                "category": op.category,
                "definition": op.definition,
                "description": op.description,
                "source": "official_operators.json",
            }
            for op in loader.get_operators()
        ]
    except Exception:
        # P0-1: No silent fallback to hardcoded lists.
        # When OfficialDataLoader fails (missing / corrupt JSON, no network),
        # return empty lists so the pipeline explicitly blocks rather than
        # silently generating alphas from an incomplete 23-field subset.
        import logging
        logging.critical(
            "context_defaults: OfficialDataLoader failed to load fields/operators "
            "from data/official_*.json. Context is EMPTY — pipeline will not "
            "generate alphas from incomplete data. Run pipeline with valid "
            "credentials to populate official JSON files from BRAIN API."
        )
        _DEFAULTS_CACHE["fields"] = []
        _DEFAULTS_CACHE["operators"] = []


def _lazy_list(key: str) -> List[dict]:
    _ensure_loaded()
    return list(_DEFAULTS_CACHE.get(key, []))


# Module-level "constants" — lazy-loaded from official JSON only.
# No hardcoded fallback; empty list when official data is unavailable.
# Other modules import these names directly (e.g. from context_defaults import DEFAULT_FIELDS).
# They behave like lists but auto-populate on first iteration/index access.

class _LazyDefaultList:
    """List-like wrapper that populates from OfficialDataLoader on first access."""

    def __init__(self, key: str) -> None:
        self._key = key

    def __iter__(self):
        return iter(_lazy_list(self._key))

    def __len__(self) -> int:
        return len(_lazy_list(self._key))

    def __bool__(self) -> bool:
        return bool(_lazy_list(self._key))

    def __getitem__(self, index):
        return _lazy_list(self._key)[index]

    def __repr__(self) -> str:
        return repr(_lazy_list(self._key))


DEFAULT_FIELDS = _LazyDefaultList("fields")  # type: ignore[assignment]
DEFAULT_OPERATORS = _LazyDefaultList("operators")  # type: ignore[assignment]


def get_default_fields() -> List[dict]:
    """Explicit getter (preferred for new code)."""
    return _lazy_list("fields")


def get_default_operators() -> List[dict]:
    """Explicit getter (preferred for new code)."""
    return _lazy_list("operators")
