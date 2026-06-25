"""Refresh and staleness-check methods for OfficialDataLoader."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runtime_constants import ContextRefreshDefaults

from ._state import _log, _resolve_data_root


class _RefreshMixin:
    """Mixin providing ``refresh`` and ``is_stale`` for OfficialDataLoader.

    These methods are split out from the main loader class to keep each
    submodule under the 350-line limit while preserving the exact same
    public API.
    """

    def refresh(
        self,
        data_dir: str | Path = "data",
        max_retries: int | None = None,
        retry_base_seconds: float | None = None,
    ) -> dict:
        """Reload official JSON files and return diff stats.

        Preserves existing data on failure. Retries up to *max_retries*
        times with *retry_base_seconds* backoff between attempts for transient
        file I/O issues.

        Call periodically (e.g. every 24h) to pick up new fields/operators
        added to the BRAIN platform.

        P0-1 fix (2026-06-13): defaults now sourced from
        :class:`ContextRefreshDefaults` (stall-detection window, not
        total timeout).  Retries use progressive backoff.  The old 120s
        wall-clock SIGALRM no longer kills slow-but-progressing fetches.
        """
        if max_retries is None:
            max_retries = ContextRefreshDefaults.DEFAULT_MAX_RETRIES
        if retry_base_seconds is None:
            retry_base_seconds = ContextRefreshDefaults.DEFAULT_RETRY_BASE_SECONDS
        old_fields = self.field_count
        old_operators = self.operator_count
        old_datasets = self.dataset_count
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                # Late import to avoid circular reference: OfficialDataLoader
                # is defined in the package __init__ which imports this module.
                from brain_alpha_ops.data.loader import OfficialDataLoader

                fresh = OfficialDataLoader()
                fresh.load_all(data_dir)

                # Verify loaded content is non-trivial
                if not fresh._fields and not fresh._operators and not fresh._datasets:
                    raise RuntimeError("refresh produced empty data sets")
                # Verify each category loaded individually to detect partial
                # failures masked by the combined emptiness check above.
                if old_fields > 0 and not fresh._fields:
                    raise RuntimeError("refresh dropped all fields")
                if old_operators > 0 and not fresh._operators:
                    raise RuntimeError("refresh dropped all operators")
                if old_datasets > 0 and not fresh._datasets:
                    raise RuntimeError("refresh dropped all datasets")

                with self._data_lock:
                    self._fields = dict(fresh._fields)
                    self._fields_by_name = self._rebuild_name_index(self._fields)
                    self._operators = dict(fresh._operators)
                    self._datasets = dict(fresh._datasets)
                    self._loaded_root = fresh._loaded_root

                # Success — return diff
                _f_delta = self.field_count - old_fields
                _o_delta = self.operator_count - old_operators
                _d_delta = self.dataset_count - old_datasets
                # P3-29 fix: distinguish "no change" from "refreshed" so
                # callers can tell whether the reload actually picked up new
                # data or was a silent no-op.
                _status = "no_change" if (_f_delta == 0 and _o_delta == 0 and _d_delta == 0) else "refreshed"
                return {
                    "status": _status,
                    "fields_delta": _f_delta,
                    "operators_delta": _o_delta,
                    "datasets_delta": _d_delta,
                    "current": {
                        "fields": self.field_count,
                        "operators": self.operator_count,
                        "datasets": self.dataset_count,
                    },
                }
            except Exception as exc:
                last_error = redact_error_message(exc)
                if attempt < max_retries:
                    _log.warning(
                        "OfficialDataLoader.refresh() attempt %d/%d failed: %s. Retrying...",
                        attempt, max_retries, last_error[:120]
                    )
                    time.sleep(retry_base_seconds * attempt)  # progressive backoff

        # All retries exhausted — existing data was never mutated.
        _log.error(
            "OfficialDataLoader.refresh() FAILED after %d attempt(s): %s. "
            "Preserved existing data (fields=%d, operators=%d, datasets=%d). "
            "Check that data/official_*.json files exist and are valid JSON.",
            max_retries, last_error[:200], old_fields, old_operators, old_datasets
        )
        return {
            "status": "refresh_failed",
            "error": last_error[:200],
            "attempts": max_retries,
            "fields_delta": 0,
            "operators_delta": 0,
            "datasets_delta": 0,
        }

    def is_stale(
        self,
        status_path: str | Path = "data/official_context_refresh_status.json",
        stale_hours: float | None = None,
    ) -> bool:
        """True when the cached context has not been refreshed within
        ``stale_hours`` (default 24h from :class:`ContextRefreshDefaults`).

        P0-1 fix (2026-06-13): this helper lets callers surface a clear
        "context is stale" warning instead of silently using old data.
        """
        if stale_hours is None:
            stale_hours = ContextRefreshDefaults.DEFAULT_STALE_HOURS
        path = Path(status_path)
        if not path.is_file():
            return True
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True
        generated_at = payload.get("generated_at")
        if not isinstance(generated_at, str) or not generated_at:
            return True
        try:
            ts = datetime.fromisoformat(generated_at)
        except ValueError:
            return True
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - ts
        return age.total_seconds() > stale_hours * 3600
