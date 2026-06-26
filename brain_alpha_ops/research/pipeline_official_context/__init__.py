"""Re-export from the ``pipeline_official_context`` subpackage.

The original monolithic ``pipeline_official_context.py`` was split into:
  - ``_types``       : dataclasses, callback type aliases, ``GENERAL_DATASET_FIELDS``
  - ``_validators``  : field/operator/dataset validation helpers
  - ``_api_mixin``   : ``_OfficialContextAPIMixin`` carrying ``_load_from_api``
                       plus the two private helpers ``_active_dataset_from_context``
                       and ``_context_degraded_reason``
  - ``_service``     : ``OfficialContextLoadService`` class assembly

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.pipeline_official_context import ...``
continue to work.
"""

from __future__ import annotations

from brain_alpha_ops.research.pipeline_official_context._types import (  # noqa: F401
    GENERAL_DATASET_FIELDS,
    EventCallback,
    HaltCallback,
    OfficialContextLoadResult,
    OfficialContextValidationState,
    ProgressCallback,
    logger,
)
from brain_alpha_ops.research.pipeline_official_context._validators import (  # noqa: F401
    active_dataset_field_names,
    configured_official_context_files_exist,
    official_context_reasons,
    refresh_context_validation_cache,
)
from brain_alpha_ops.research.pipeline_official_context._service import (  # noqa: F401
    OfficialContextLoadService,
)
from brain_alpha_ops.research.pipeline_official_context._api_mixin import (  # noqa: F401
    _OfficialContextAPIMixin,
    _active_dataset_from_context,
    _context_degraded_reason,
)

__all__ = [
    # Data structures
    "OfficialContextLoadResult",
    "OfficialContextValidationState",
    "OfficialContextLoadService",
    # Constants / type aliases
    "GENERAL_DATASET_FIELDS",
    "ProgressCallback",
    "EventCallback",
    "HaltCallback",
    "logger",
    # Public helpers
    "configured_official_context_files_exist",
    "refresh_context_validation_cache",
    "active_dataset_field_names",
    "official_context_reasons",
    # Private helpers (re-exported for test monkeypatch compatibility)
    "_OfficialContextAPIMixin",
    "_active_dataset_from_context",
    "_context_degraded_reason",
]
