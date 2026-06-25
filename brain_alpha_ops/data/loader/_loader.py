"""OfficialDataLoader base class — singleton, loading, and query methods."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from brain_alpha_ops.runtime_constants import ContextRefreshDefaults

from ._state import _log, _resolve_data_root, ensure_official_context_files
from ..schemas import DatasetRef, OfficialDataset, OfficialField, OfficialOperator


class OfficialDataLoaderBase:
    """Singleton that loads official_fields/operators/datasets JSON files on first use."""

    _instance: Optional["OfficialDataLoaderBase"] = None
    _instance_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "OfficialDataLoaderBase":
        """Return (and auto-create) the singleton instance.

        Thread-safe: uses double-checked locking so that only one
        OfficialDataLoader is ever created even when multiple threads
        call instance() concurrently on first access.
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    loader = cls()
                    loader.load_all()
                    cls._instance = loader
        return cls._instance

    @classmethod
    def reload(cls) -> "OfficialDataLoaderBase":
        """Force re-load from disk (useful during development)."""
        with cls._instance_lock:
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
        self._loaded_root: Path | None = None
        self._data_lock = threading.RLock()

    def load_all(self, data_dir: str | Path = "data") -> None:
        """Read all three official JSON files and build in-memory indexes."""
        root = _resolve_data_root(data_dir)
        ensure_official_context_files(root)
        self._loaded_root = root
        self._load_fields(root / "official_fields.json")
        self._load_operators(root / "official_operators.json")
        self._load_datasets(root / "official_datasets.json")
        # Warn if all official JSON files failed to load — fallback will be used
        if not self._fields and not self._operators and not self._datasets:
            _log.warning(
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
        with self._data_lock:
            if dataset_id is None:
                return list(self._fields.values())
            exact = [
                f
                for f in self._fields.values()
                if f.dataset is not None and f.dataset.id == dataset_id
            ]
            if exact:
                return exact
            dataset = self._datasets.get(dataset_id)
            category = str(getattr(dataset, "category", "") or "").lower() if dataset else ""
            if not category:
                return []
            return [
                f
                for f in self._fields.values()
                if f.dataset is None and str(f.category or "").lower() == category
            ]

    # Future-proof alias: any code that writes loader.list_fields(...)
    # hits the same method as loader.get_fields(...).
    list_fields = get_fields

    def get_field_by_name(self, name: str) -> Optional[OfficialField]:
        """Return the first field whose id equals *name* (case-insensitive)."""
        with self._data_lock:
            results = self._fields_by_name.get(name.lower())
            if results:
                return results[0]
            return None

    def validate_field(self, name: str, dataset_id: Optional[str] = None) -> bool:
        """Check whether *name* is a known official field."""
        with self._data_lock:
            entries = self._fields_by_name.get(name.lower(), [])
            if not entries:
                return False
            if dataset_id is not None:
                if any(f.dataset and f.dataset.id == dataset_id for f in entries):
                    return True
                dataset = self._datasets.get(dataset_id)
                category = str(getattr(dataset, "category", "") or "").lower() if dataset else ""
                return bool(category) and any(
                    f.dataset is None and str(f.category or "").lower() == category
                    for f in entries
                )
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
        with self._data_lock:
            return list(self._operators.values())

    def get_operator(self, name: str) -> Optional[OfficialOperator]:
        with self._data_lock:
            return self._operators.get(name.lower())

    def validate_operator(self, name: str) -> bool:
        with self._data_lock:
            return name.lower() in self._operators

    # ------------------------------------------------------------------
    # Dataset queries
    # ------------------------------------------------------------------
    def get_datasets(self) -> List[OfficialDataset]:
        with self._data_lock:
            return list(self._datasets.values())

    def get_dataset(self, dataset_id: str) -> Optional[OfficialDataset]:
        with self._data_lock:
            return self._datasets.get(dataset_id)

    # ------------------------------------------------------------------
    # Counts
    # ------------------------------------------------------------------
    @property
    def field_count(self) -> int:
        with self._data_lock:
            return len(self._fields)

    @property
    def operator_count(self) -> int:
        with self._data_lock:
            return len(self._operators)

    @property
    def dataset_count(self) -> int:
        with self._data_lock:
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
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return
        for item in raw:
            if not isinstance(item, dict):
                continue
            field_id = str(item.get("id") or item.get("name") or item.get("field") or item.get("fieldId") or "").strip()
            if not field_id:
                continue
            ds_raw = item.get("dataset") if isinstance(item.get("dataset"), dict) else None
            cat_raw = item.get("category") if isinstance(item.get("category"), dict) else None
            try:
                field = OfficialField(
                    id=field_id,
                    description=str(item.get("description") or ""),
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
            except (TypeError, ValueError):
                continue
            self._fields[field.id] = field
            key = field.id.lower()
            self._fields_by_name.setdefault(key, []).append(field)

    def _load_operators(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
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
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, list):
            return
        for item in raw:
            cat_raw = item.get("category") if isinstance(item.get("category"), dict) else None
            ds = OfficialDataset(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                field_count=int(item.get("field_count", 0)),
                category=str(cat_raw.get("id", "") if cat_raw else item.get("category", "")),
            )
            self._datasets[ds.id] = ds
