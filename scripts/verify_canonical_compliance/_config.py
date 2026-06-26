"""Config loading helpers for canonical compliance verification."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _SCRIPT_DIR.parent


def _load_config(config_path: str | None = None) -> Any:
    """Load RunConfig from the specified or default config path."""
    sys.path.insert(0, str(_PROJECT_ROOT))
    from brain_alpha_ops.config import load_run_config

    return load_run_config(
        Path(config_path) if config_path else None
    )


def _context_validation_for_data_dir(data_dir: Path) -> dict[str, Any]:
    """Validate persisted official context without falling back to heuristics."""
    from brain_alpha_ops.data.official_context_validation import validate_official_context

    return validate_official_context(data_dir=data_dir)
