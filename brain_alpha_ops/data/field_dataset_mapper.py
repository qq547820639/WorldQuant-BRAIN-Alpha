"""Bidirectional field ↔ dataset mapping built from official_fields.json."""

from __future__ import annotations

from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .loader import OfficialDataLoader


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
        self._dataset_to_fields: Dict[str, List[str]] = {}
        self._field_to_datasets: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build(self, loader: "OfficialDataLoader") -> "FieldDatasetMapper":
        """Populate both indexes from *loader*.  Call once during startup."""
        self._dataset_to_fields.clear()
        self._field_to_datasets.clear()

        for field in loader.get_fields():
            if field.dataset is None:
                continue
            ds_id = field.dataset.id
            field_name = field.id.lower()

            self._dataset_to_fields.setdefault(ds_id, []).append(field_name)

            ds_list = self._field_to_datasets.setdefault(field_name, [])
            if ds_id not in ds_list:
                ds_list.append(ds_id)

        return self

    # ------------------------------------------------------------------
    # dataset → fields
    # ------------------------------------------------------------------
    def fields_for(self, dataset_id: str) -> List[str]:
        """Return field names belonging to *dataset_id*."""
        return sorted(self._dataset_to_fields.get(dataset_id, []))

    def field_count(self, dataset_id: str) -> int:
        """Number of fields in *dataset_id*."""
        return len(self._dataset_to_fields.get(dataset_id, []))

    # ------------------------------------------------------------------
    # field → datasets
    # ------------------------------------------------------------------
    def datasets_for(self, field_name: str) -> List[str]:
        """Return dataset ids that contain *field_name*."""
        return sorted(self._field_to_datasets.get(field_name.lower(), []))

    def is_common_field(self, field_name: str, min_datasets: int = 3) -> bool:
        """True if *field_name* appears in at least *min_datasets* datasets."""
        return len(self.datasets_for(field_name)) >= min_datasets

    # ------------------------------------------------------------------
    # Set operations
    # ------------------------------------------------------------------
    def common_fields(self, dataset_ids: List[str]) -> List[str]:
        """Fields that appear in **all** listed datasets."""
        if not dataset_ids:
            return []
        sets = [set(self._dataset_to_fields.get(ds, [])) for ds in dataset_ids]
        return sorted(sets[0].intersection(*sets[1:]))

    def unique_fields(self, dataset_id: str, exclude_ids: List[str]) -> List[str]:
        """Fields in *dataset_id* that are **not** in any of *exclude_ids*."""
        own = set(self._dataset_to_fields.get(dataset_id, []))
        others: set = set()
        for ds in exclude_ids:
            others.update(self._dataset_to_fields.get(ds, []))
        return sorted(own - others)

    def dataset_overlap(self, ds1: str, ds2: str) -> float:
        """Jaccard similarity between two datasets (0.0 – 1.0)."""
        set1 = set(self._dataset_to_fields.get(ds1, []))
        set2 = set(self._dataset_to_fields.get(ds2, []))
        union = set1 | set2
        if not union:
            return 0.0
        return len(set1 & set2) / len(union)
