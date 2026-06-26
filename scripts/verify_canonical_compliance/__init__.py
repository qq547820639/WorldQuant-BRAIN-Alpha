"""Automated BRAIN canonical compliance verification.

Performs zero-deviation comparison between:
1. Configured thresholds vs BRAIN canonical thresholds
2. Configured API paths vs BRAIN canonical API paths
3. Configured settings vs BRAIN allowed enum values
4. Scoring simulation output vs BRAIN official API output
5. Field/operator definitions vs BRAIN official context

Usage:
    python scripts/verify_canonical_compliance.py
    python scripts/verify_canonical_compliance.py --json
    python scripts/verify_canonical_compliance.py --strict
"""

from __future__ import annotations

from ._checks import (
    _check_api_paths,
    _check_settings_enums,
    _check_thresholds,
)
from ._checks_more import (
    _check_dataset_ids,
    _check_no_custom_extension,
    _check_scoring_simulation,
)
from ._config import (
    _SCRIPT_DIR,
    _PROJECT_ROOT,
    _context_validation_for_data_dir,
    _load_config,
)
from ._report import (
    _format_report,
    main,
    verify_all,
)

__all__ = [
    "_PROJECT_ROOT",
    "_SCRIPT_DIR",
    "_check_api_paths",
    "_check_dataset_ids",
    "_check_no_custom_extension",
    "_check_scoring_simulation",
    "_check_settings_enums",
    "_check_thresholds",
    "_context_validation_for_data_dir",
    "_format_report",
    "_load_config",
    "main",
    "verify_all",
]
