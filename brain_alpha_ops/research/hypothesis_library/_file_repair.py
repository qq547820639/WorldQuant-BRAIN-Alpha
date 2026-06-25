"""File-repair and YAML-loading helpers for the Hypothesis Library.

Extracted from the original ``hypothesis_library.py`` monolith. Handles
repair of missing packaged hypothesis YAML files from PyInstaller data
and provides the safe YAML loader that prefers PyYAML but falls back to
the bundled minimal parser.
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

from ._minimal_yaml import _minimal_yaml_load

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal production envs
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_HYPOTHESIS_LIBRARY_RELATIVE_DIR = Path("brain_alpha_ops") / "research" / "hypotheses"
PACKAGED_HYPOTHESIS_LIBRARY_FILES = (
    "_schema.yaml",
    "analyst_behavior.yaml",
    "cross_asset_spillover.yaml",
    "earnings_revision.yaml",
    "event_driven.yaml",
    "liquidity_premium.yaml",
    "low_volatility.yaml",
    "macro_sensitivity.yaml",
    "microstructure.yaml",
    "quality_profitability.yaml",
    "sentiment_short.yaml",
    "value_reversal.yaml",
)


def ensure_hypothesis_library_files(directory: str | Path) -> dict[str, object]:
    """Repair missing packaged hypothesis YAML files from PyInstaller data."""
    target_root = Path(directory)
    bundled_root = _bundled_hypothesis_root()
    result: dict[str, object] = {
        "target_root": str(target_root),
        "bundled_root": str(bundled_root) if bundled_root else "",
        "copied": [],
        "present": [],
        "missing": [],
        "failed": [],
    }
    copied = result["copied"]
    present = result["present"]
    missing = result["missing"]
    failed = result["failed"]
    if not isinstance(copied, list):
        raise TypeError(f"expected result['copied'] to be a list, got {type(copied).__name__}")
    if not isinstance(present, list):
        raise TypeError(f"expected result['present'] to be a list, got {type(present).__name__}")
    if not isinstance(missing, list):
        raise TypeError(f"expected result['missing'] to be a list, got {type(missing).__name__}")
    if not isinstance(failed, list):
        raise TypeError(f"expected result['failed'] to be a list, got {type(failed).__name__}")

    for filename in PACKAGED_HYPOTHESIS_LIBRARY_FILES:
        target = target_root / filename
        if _yaml_file_is_usable(target):
            present.append(filename)
            continue
        if bundled_root is None:
            missing.append(filename)
            continue
        source = bundled_root / filename
        if not _yaml_file_is_usable(source):
            missing.append(filename)
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(filename)
        except OSError as exc:
            from brain_alpha_ops.redaction import redact_error_message
            failed.append({"filename": filename, "error": redact_error_message(exc)})

    if copied:
        logger.info(
            "HypothesisLibrary: copied bundled hypothesis files into %s: %s",
            target_root,
            ", ".join(str(item) for item in copied),
        )
    if failed:
        logger.warning(
            "HypothesisLibrary: failed to copy bundled hypothesis files into %s: %s",
            target_root,
            failed,
        )
    return result


def _bundled_hypothesis_root() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    root = Path(str(meipass)) / DEFAULT_HYPOTHESIS_LIBRARY_RELATIVE_DIR
    return root if root.is_dir() else None


def _yaml_file_is_usable(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _safe_load_yaml(text: str) -> dict[str, Any]:
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return _minimal_yaml_load(text)
