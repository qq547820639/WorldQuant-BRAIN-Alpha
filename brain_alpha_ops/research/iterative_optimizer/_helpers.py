"""Helper functions for the ``IterativeOptimizer`` subpackage.

Extracted from the original ``iterative_optimizer.py`` monolith. These
private helpers build the set of official operator names from either the
``OfficialDataLoader`` instance or the cached ``official_operators.json``
file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

# Preserve the original ``brain_alpha_ops.research.iterative_optimizer``
# logger name so downstream log filters and test caplog assertions keep
# working after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.iterative_optimizer")


def _current_official_operator_names() -> frozenset[str]:
    # NOTE: ``parents[3]`` (not ``parents[2]``) because this module now lives
    # one directory deeper (``research/iterative_optimizer/_helpers.py``)
    # than the original ``research/iterative_optimizer.py`` monolith. The
    # resolved path remains ``<project_root>/data/official_operators.json``.
    path = Path(__file__).resolve().parents[3] / "data" / "official_operators.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    return frozenset(
        str(item.get("name", "")).lower()
        for item in payload
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    )


def _operator_names_from_loader(loader: Any) -> set[str]:
    get_operators = getattr(loader, "get_operators", None)
    if not callable(get_operators):
        return set()
    try:
        return {
            str(getattr(op, "name", "")).lower()
            for op in get_operators()
            if str(getattr(op, "name", "")).strip()
        }
    except Exception:
        logger.exception("iterative_optimizer: unexpected error")
        logger.warning("official operator metadata unavailable for iterative optimizer", exc_info=True)
        return set()
