"""Singleton loader for official WorldQuant BRAIN context (fields, operators, datasets).

Loads ``data/official_*.json`` into memory on first access.  All other modules
query this loader instead of using hard-coded lists.

Usage::

    from brain_alpha_ops.data import OfficialDataLoader
    loader = OfficialDataLoader.instance()
    fields = loader.get_fields(dataset_id="analyst4")
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)
from typing import Dict, List, Optional

from brain_alpha_ops.config import runtime_project_root
from brain_alpha_ops.redaction import redact_error_message

from .schemas import DatasetRef, OfficialDataset, OfficialField, OfficialOperator


class OfficialDataLoader:
    """Singleton that loads official_fields/operators/datasets JSON files on first use."""

    _instance: Optional["OfficialDataLoader"] = None

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "OfficialDataLoader":
        """Return (and auto-create) the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.load_all()
        return cls._instance

    @classmethod
    def reload(cls) -> "OfficialDataLoader":
        """Force re-load from disk (useful during development)."""
        cls._instance = None
        return cls.instance()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def __init__(self) -> None:
        self._fields: Dict[str, OfficialField] = {}
        self._fields_by_name: Dict[str, List[OfficialField]] = {}
        self._operators: Dict[str, OfficialOperator] = {}
        self._datasets: Dict[str, OfficialDataset] = {}

    def load_all(self, data_dir: str | Path = "data") -> None:
        """Read all three official JSON files and build in-memory indexes."""
        data_path = Path(data_dir)
        root = data_path if data_path.is_absolute() else runtime_project_root() / data_path
        self._load_fields(root / "official_fields.json")
        self._load_operators(root / "official_operators.json")
        self._load_datasets(root / "official_datasets.json")
        # Warn if all official JSON files failed to load — fallback will be used
        if not self._fields and not self._operators and not self._datasets:
            import logging
            logging.warning(
                "OfficialDataLoader: No official data JSON files loaded "
                "(%s/*.json). Falling back to context_defaults built-in lists. "
                "Run pipeline with valid credentials to refresh from BRAIN API.",
                root,
            )

    # ------------------------------------------------------------------
    # Field queries
    # ------------------------------------------------------------------
    def get_fields(self, dataset_id: Optional[str] = None) -> List[OfficialField]:
        """Return all fields, optionally filtered by *dataset_id*."""
        if dataset_id is None:
            return list(self._fields.values())
        return [
            f
            for f in self._fields.values()
            if f.dataset is not None and f.dataset.id == dataset_id
        ]

    def get_field_by_name(self, name: str) -> Optional[OfficialField]:
        """Return the first field whose id equals *name* (case-insensitive)."""
        results = self._fields_by_name.get(name.lower())
        if results:
            return results[0]
        return None

    def validate_field(self, name: str, dataset_id: Optional[str] = None) -> bool:
        """Check whether *name* is a known official field."""
        entries = self._fields_by_name.get(name.lower(), [])
        if not entries:
            return False
        if dataset_id is not None:
            return any(f.dataset and f.dataset.id == dataset_id for f in entries)
        return True

    def search_fields(self, keyword: str, dataset_id: Optional[str] = None) -> List[OfficialField]:
        """Case-insensitive substring search across field ids and descriptions."""
        kw = keyword.lower()
        results: List[OfficialField] = []
        for f in self.get_fields(dataset_id):
            if kw in f.id.lower() or kw in f.description.lower():
                results.append(f)
        return results

    # ------------------------------------------------------------------
    # Operator queries
    # ------------------------------------------------------------------
    def get_operators(self) -> List[OfficialOperator]:
        return list(self._operators.values())

    def get_operator(self, name: str) -> Optional[OfficialOperator]:
        return self._operators.get(name.lower())

    def validate_operator(self, name: str) -> bool:
        return name.lower() in self._operators

    # ------------------------------------------------------------------
    # Dataset queries
    # ------------------------------------------------------------------
    def get_datasets(self) -> List[OfficialDataset]:
        return list(self._datasets.values())

    def get_dataset(self, dataset_id: str) -> Optional[OfficialDataset]:
        return self._datasets.get(dataset_id)

    # ------------------------------------------------------------------
    # P2-5: Context refresh
    # ------------------------------------------------------------------
    def refresh(self, data_dir: str | Path = "data", max_retries: int = 2) -> dict:
        """Reload official JSON files and return diff stats.

        Preserves existing data on failure. Retries up to *max_retries*
        times with 1s backoff between attempts for transient file I/O issues.

        Call periodically (e.g. every 24h) to pick up new fields/operators
        added to the BRAIN platform.
        """
        old_fields = self.field_count
        old_operators = self.operator_count
        old_datasets = self.dataset_count

        # Backup existing data in case reload fails
        backup_fields = dict(self._fields)
        backup_operators = dict(self._operators)
        backup_datasets = dict(self._datasets)

        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                self._fields.clear()
                self._fields_by_name.clear()
                self._operators.clear()
                self._datasets.clear()
                self.load_all(data_dir)
                
                # Verify loaded content is non-trivial
                if not self._fields and not self._operators and not self._datasets:
                    raise RuntimeError("refresh produced empty data sets")
                    
                # Success — return diff
                return {
                    "status": "refreshed",
                    "fields_delta": self.field_count - old_fields,
                    "operators_delta": self.operator_count - old_operators,
                    "datasets_delta": self.dataset_count - old_datasets,
                    "current": {
                        "fields": self.field_count,
                        "operators": self.operator_count,
                        "datasets": self.dataset_count,
                    },
                }
            except Exception as exc:
                last_error = redact_error_message(exc)
                if attempt < max_retries:
                    import time as _time
                    _log.warning(
                        "OfficialDataLoader.refresh() attempt %d/%d failed: %s. Retrying...",
                        attempt, max_retries, last_error[:120]
                    )
                    _time.sleep(1.0 * attempt)  # progressive backoff
                    # Restore backups for retry
                    self._fields = dict(backup_fields)
                    self._fields_by_name = self._rebuild_name_index(self._fields)
                    self._operators = dict(backup_operators)
                    self._datasets = dict(backup_datasets)

        # All retries exhausted — restore backup and report failure
        self._fields = backup_fields
        self._fields_by_name = self._rebuild_name_index(self._fields)
        self._operators = backup_operators
        self._datasets = backup_datasets
        _log.error(
            "OfficialDataLoader.refresh() FAILED after %d attempt(s): %s. "
            "Restored backup data (fields=%d, operators=%d, datasets=%d). "
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

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------
    @property
    def field_count(self) -> int:
        return len(self._fields)

    @property
    def operator_count(self) -> int:
        return len(self._operators)

    @property
    def dataset_count(self) -> int:
        return len(self._datasets)

    # ==================================================================
    # Internal helpers
    # ==================================================================

    @staticmethod
    def _rebuild_name_index(fields: dict) -> dict:
        """Rebuild the case-insensitive name index from field dict values."""
        result: dict = {}
        for f in fields.values():
            result.setdefault(f.id.lower(), []).append(f)
        return result

    def _load_fields(self, path: Path) -> None:
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        for item in raw:
            ds_raw = item.get("dataset") if isinstance(item.get("dataset"), dict) else None
            cat_raw = item.get("category") if isinstance(item.get("category"), dict) else None
            field = OfficialField(
                id=str(item.get("id", "")),
                description=str(item.get("description", "")),
                dataset=DatasetRef(id=str(ds_raw.get("id", "")), name=str(ds_raw.get("name", ""))) if ds_raw else None,
                category=str(cat_raw.get("id", "") if cat_raw else item.get("category", "")),
                region=str(item.get("region", "USA")),
                delay=int(item.get("delay", 1)),
                universe=str(item.get("universe", "TOP3000")),
                type=str(item.get("type", "MATRIX")),
                coverage=float(item.get("coverage", 0.0)),
                userCount=int(item.get("userCount", 0)),
                alphaCount=int(item.get("alphaCount", 0)),
            )
            self._fields[field.id] = field
            key = field.id.lower()
            self._fields_by_name.setdefault(key, []).append(field)

    def _load_operators(self, path: Path) -> None:
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return
        for item in raw:
            op = OfficialOperator(
                name=str(item.get("name", "")),
                category=str(item.get("category", "")),
                definition=str(item.get("definition", "")),
                description=str(item.get("description", "")),
            )
            self._operators[op.name.lower()] = op

    def _load_datasets(self, path: Path) -> None:
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return
        for item in raw:
            ds = OfficialDataset(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                field_count=int(item.get("field_count", 0)),
            )
            self._datasets[ds.id] = ds
