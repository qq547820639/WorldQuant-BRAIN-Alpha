"""Fail-closed release readiness gate for final BRAIN Alpha delivery.

Re-export subpackage. The implementation has been split from the former
``scripts/final_release_gate.py`` monolith (deep-optimization-phase12,
Task A4) into responsibility-focused submodules. The public API is
re-exported here so ``from scripts.final_release_gate import ...`` continues
to resolve to the package directory. A thin ``scripts/final_release_gate.py``
shim remains for direct ``python scripts/final_release_gate.py`` CLI
invocation (Python prefers this package ``__init__.py`` over the sibling
shim for imports).
"""

from __future__ import annotations

from ._checks import (
    _call_name,
    _check_dataset_redline,
    _check_environment,
    _check_exact_thresholds,
    _check_official_api_alignment,
    _check_traceability_redline,
    _iter_release_source_files,
    _official_dataset_ids,
    _scan_custom_field_operator_expansion,
    _source_registers_custom_field_or_operator,
)
from ._config import (
    _check_config_loads,
    _load_config_json,
    _resolve_under_root,
    _validate_official_context,
)
from ._context_checks import (
    _check_capability_registry_redline,
    _check_official_context_redline,
    _check_refresh_status,
    _official_context_cache_complete,
    _official_context_files_complete,
    _official_context_has_fresh_refresh_evidence,
)
from ._manifest import _build_manifest_hash, _redline_summary
from ._models import (
    CUSTOM_EXTENSION_NAMES,
    DEFAULT_CONFIG,
    Finding,
    GateReport,
    LEGACY_SINGLE_DATASET_STRATEGIES,
    OFFICIAL_CONTEXT_FILES,
    OFFICIAL_CONTEXT_REQUIRED_METADATA,
    RELEASE_DATASET_STRATEGIES,
    REQUIRED_OFFICIAL_API,
    ROOT,
    SCHEMA_VERSION,
    _add_finding,
)
from ._runner import main, run_final_release_gate
from ._tracker import (
    _check_implementation_tracker_redline,
    _tracker_gate_matrix,
    _tracker_payload,
)

__all__ = [
    "CUSTOM_EXTENSION_NAMES",
    "DEFAULT_CONFIG",
    "Finding",
    "GateReport",
    "LEGACY_SINGLE_DATASET_STRATEGIES",
    "OFFICIAL_CONTEXT_FILES",
    "OFFICIAL_CONTEXT_REQUIRED_METADATA",
    "RELEASE_DATASET_STRATEGIES",
    "REQUIRED_OFFICIAL_API",
    "ROOT",
    "SCHEMA_VERSION",
    "main",
    "run_final_release_gate",
]
