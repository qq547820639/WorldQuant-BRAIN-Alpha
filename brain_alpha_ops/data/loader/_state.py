"""Shared state, path helpers, and context-file provisioning for loader package."""
from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import runtime_project_root
from brain_alpha_ops.redaction import redact_error_message

_log = logging.getLogger("brain_alpha_ops.data.loader")

REQUIRED_OFFICIAL_CONTEXT_FILES = (
    "official_fields.json",
    "official_operators.json",
    "official_datasets.json",
)
SUPPLEMENTAL_OFFICIAL_CONTEXT_FILES = (
    "official_fields.meta.json",
    "official_operators.meta.json",
    "official_datasets.meta.json",
    "official_context_refresh_status.json",
)
PACKAGED_OFFICIAL_CONTEXT_FILES = REQUIRED_OFFICIAL_CONTEXT_FILES + SUPPLEMENTAL_OFFICIAL_CONTEXT_FILES


def _pkg() -> Any:
    """Return the parent package module so submodules can access
    ``runtime_project_root`` that tests may monkeypatch on the package."""
    return sys.modules["brain_alpha_ops.data.loader"]


def _resolve_data_root(data_dir: str | Path) -> Path:
    """Resolve *data_dir* against the runtime project root.

    Reads ``runtime_project_root`` from the package module so that
    ``monkeypatch.setattr("brain_alpha_ops.data.loader.runtime_project_root", ...)``
    in tests continues to take effect.
    """
    data_path = Path(data_dir)
    root = data_path if data_path.is_absolute() else _pkg().runtime_project_root() / data_path
    return root.resolve()


def _bundled_data_root() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return None
    root = Path(str(meipass)) / "data"
    return root if root.is_dir() else None


def _file_is_usable(path: Path, *, required: bool) -> bool:
    if not path.is_file():
        return False
    try:
        if path.stat().st_size <= 0:
            return False
    except OSError:
        return False
    if not required:
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, list) and bool(payload)


def ensure_official_context_files(data_dir: str | Path = "data") -> dict[str, object]:
    """Copy bundled official context files into the persistent runtime data dir.

    One-file EXE builds unpack bundled data under ``sys._MEIPASS`` while runtime
    paths resolve next to the executable.  This keeps packaged first-starts from
    falling back to empty official context when ``dist/data`` is incomplete.
    """
    target_root = _resolve_data_root(data_dir)
    bundled_root = _bundled_data_root()
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

    for filename in PACKAGED_OFFICIAL_CONTEXT_FILES:
        target = target_root / filename
        required = filename in REQUIRED_OFFICIAL_CONTEXT_FILES
        if _file_is_usable(target, required=required):
            present.append(filename)
            continue
        if bundled_root is None:
            missing.append(filename)
            continue

        source = bundled_root / filename
        if not _file_is_usable(source, required=required):
            missing.append(filename)
            continue

        try:
            target_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(filename)
        except OSError as exc:
            failed.append({"filename": filename, "error": redact_error_message(exc)})

    if copied:
        _log.info(
            "OfficialDataLoader: copied bundled official context files into %s: %s",
            target_root,
            ", ".join(str(item) for item in copied),
        )
    if failed:
        _log.warning(
            "OfficialDataLoader: failed to copy bundled official context files into %s: %s",
            target_root,
            failed,
        )
    return result
