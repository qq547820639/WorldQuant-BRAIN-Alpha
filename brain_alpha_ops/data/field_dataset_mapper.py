"""Bidirectional field ↔ dataset mapping built from official_fields.json."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING  # N-04: use builtins dict/list with from __future__ import annotations

if TYPE_CHECKING:
    from .loader import OfficialDataLoader


# S-11: build() and _add_mapping() are not concurrency-safe;
# do not call them concurrently from multiple threads.
class FieldDatasetMapper:
    """Builds and queries a bidirectional mapping between fields and datasets.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
        mapper = FieldDatasetMapper()
        mapper.build(OfficialDataLoader.instance())
        fields = mapper.fields_for("model77")      # → field name list
        datasets = mapper.datasets_for("close")     # → dataset id list
    """

    def __init__(self) -> None:
        self._dataset_to_fields: dict[str, list[str]]
        self._field_to_datasets: dict[str, list[str]]
        self._lock = threading.RLock()
        self._clear()

    def _clear(self) -> None:
        self._dataset_to_fields = {}
        self._field_to_datasets = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self, loader: "OfficialDataLoader") -> "FieldDatasetMapper":
        """Populate both indexes from *loader*.  Call once during startup.

        P1-2: builds into local dicts then swaps atomically so readers
        never see a half-populated state.
        """
        new_ds_to_fields: dict[str, list[str]] = {}
        new_field_to_ds: dict[str, list[str]] = {}

        def _add(dataset_id: str, field_name: str) -> None:
            if not dataset_id or not field_name:
                return
            fields = new_ds_to_fields.setdefault(dataset_id, [])
            if field_name not in fields:
                fields.append(field_name)
            ds_list = new_field_to_ds.setdefault(field_name, [])
            if dataset_id not in ds_list:
                ds_list.append(dataset_id)

        list_datasets = getattr(loader, "get_datasets", None)
        if callable(list_datasets):
            for dataset in list_datasets():
                ds_id = str(dataset.id or "")
                if not ds_id:
                    continue
                try:
                    fields = loader.get_fields(ds_id)
                except TypeError:
                    fields = []
                for field in fields:
                    _add(ds_id, field.id.lower())

        for field in loader.get_fields():
            if field.dataset is None:
                continue
            ds_id = field.dataset.id
            _add(ds_id, field.id.lower())

        with self._lock:
            self._dataset_to_fields = new_ds_to_fields
            self._field_to_datasets = new_field_to_ds
        return self

    def _add_mapping(self, dataset_id: str, field_name: str) -> None:
        if not dataset_id or not field_name:
            return
        with self._lock:
            fields = self._dataset_to_fields.setdefault(dataset_id, [])
            if field_name not in fields:
                fields.append(field_name)
            ds_list = self._field_to_datasets.setdefault(field_name, [])
            if dataset_id not in ds_list:
                ds_list.append(dataset_id)

    # ------------------------------------------------------------------
    # dataset → fields
    # ------------------------------------------------------------------
    def fields_for(self, dataset_id: str) -> list[str]:
        """Return field names belonging to *dataset_id*."""
        with self._lock:
            return sorted(list(self._dataset_to_fields.get(dataset_id, [])))

    def field_count(self, dataset_id: str) -> int:
        """Number of fields in *dataset_id*."""
        with self._lock:
            return len(self._dataset_to_fields.get(dataset_id, []))

    # ------------------------------------------------------------------
    # field → datasets
    # ------------------------------------------------------------------
    def datasets_for(self, field_name: str) -> list[str]:
        """Return dataset ids that contain *field_name*."""
        with self._lock:
            return sorted(list(self._field_to_datasets.get(field_name.lower(), [])))

    def is_common_field(self, field_name: str, min_datasets: int = 3) -> bool:
        """True if *field_name* appears in at least *min_datasets* datasets."""
        return len(self.datasets_for(field_name)) >= min_datasets

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------
    def common_fields(self, dataset_ids: list[str]) -> list[str]:
        """Fields that appear in **all** listed datasets."""
        if not dataset_ids:
            return []
        with self._lock:
            sets = [set(self._dataset_to_fields.get(ds, [])) for ds in dataset_ids]
        return sorted(sets[0].intersection(*sets[1:]))

    def unique_fields(self, dataset_id: str, exclude_ids: list[str]) -> list[str]:
        """Fields in *dataset_id* that are **not** in any of *exclude_ids*."""
        with self._lock:
            own = set(self._dataset_to_fields.get(dataset_id, []))
            others: set = set()
            for ds in exclude_ids:
                others.update(self._dataset_to_fields.get(ds, []))
        return sorted(own - others)

    def dataset_overlap(self, ds1: str, ds2: str) -> float:
        """Jaccard similarity between two datasets (0.0 – 1.0)."""
        with self._lock:
            set1 = set(self._dataset_to_fields.get(ds1, []))
            set2 = set(self._dataset_to_fields.get(ds2, []))
        union = set1 | set2
        if not union:
            return 0.0
        return len(set1 & set2) / len(union)
