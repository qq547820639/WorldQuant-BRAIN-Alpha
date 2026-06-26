"""Types and constants for the official BRAIN context loading helpers.

Extracted from the original ``pipeline_official_context.py`` monolith.
Holds the public dataclasses, callback type aliases, and module-level
constants used across the subpackage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

# Preserve the original ``brain_alpha_ops.research.pipeline_official_context``
# logger name so downstream log filters and test caplog assertions keep
# working after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.pipeline_official_context")

ProgressCallback = Callable[..., None]
EventCallback = Callable[..., None]
HaltCallback = Callable[[str], None]

GENERAL_DATASET_FIELDS = {"returns", "sector", "industry", "subindustry", "market"}


@dataclass
class OfficialContextLoadResult:
    fields: list[dict]
    operators: list[dict]
    context_summary: dict[str, Any]
    generator: Any
    loader: Any = None
    mapper: Any = None
    theme_engine: Any = None
    selector: Any = None
    hypothesis_library: Any = None
    optimizer: Any = None
    active_dataset_id: str = ""


@dataclass
class OfficialContextValidationState:
    field_names: set[str]
    operator_names: set[str]
    dataset_field_names_cache: dict[str, set[str]]
