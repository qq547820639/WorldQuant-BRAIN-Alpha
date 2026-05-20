"""Dynamic dataset selector — supports all/rotate/random/specific strategies."""

from __future__ import annotations

import random
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper


class DatasetSelector:
    """Select datasets using one of four strategies.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
        selector = DatasetSelector()
        selector.initialize(OfficialDataLoader.instance())
        ds = selector.select("rotate")     # → ["analyst4"] (next in rotation)
        ds = selector.select("all")        # → ["model77","analyst4",...] (all 16)
    """

    STRATEGIES = ("all", "rotate", "random", "specific")

    def __init__(self) -> None:
        self._datasets: List[str] = []
        self._rotation_index: int = 0
        self._category_index: Dict[str, List[str]] = {}
        self._all_categories: List[str] = []
        self._loader: Optional["OfficialDataLoader"] = None

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def initialize(self, loader: "OfficialDataLoader") -> None:
        """Populate available dataset IDs from the loader and build category index."""
        self._loader = loader
        self._datasets = sorted(ds.id for ds in loader.get_datasets())
        self._build_category_index()

    # ------------------------------------------------------------------
    # Select
    # ------------------------------------------------------------------
    def select(self, strategy: str = "all", **kwargs) -> List[str]:
        """Return dataset IDs per *strategy*.

        *strategy* values:
            "all"      — return all 16 dataset IDs
            "rotate"   — return the next single dataset in rotation
            "random"   — return *n* randomly chosen datasets
            "specific" — return the *dataset_ids* provided in kwargs
        """
        if strategy == "rotate":
            return self._select_rotate(advance=kwargs.get("advance", True))
        if strategy == "random":
            return self._select_random(
                n=kwargs.get("n", 3),
                seed=kwargs.get("seed"),
            )
        if strategy == "specific":
            ds_ids = kwargs.get("dataset_ids", [])
            return [d for d in ds_ids if d in self._datasets]
        # default: "all"
        return self._select_all()

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------
    def _select_all(self) -> List[str]:
        return list(self._datasets)

    def _select_rotate(self, advance: bool = True) -> List[str]:
        if not self._datasets:
            return []
        idx = self._rotation_index % len(self._datasets)
        if advance:
            self._rotation_index = (self._rotation_index + 1) % len(self._datasets)
        return [self._datasets[idx]]

    def _select_random(self, n: int = 3, seed: Optional[int] = None) -> List[str]:
        if seed is not None:
            random.seed(seed)
        k = min(n, len(self._datasets))
        return random.sample(self._datasets, k)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def rotate(self, advance: bool = True) -> str:
        """Return a single dataset ID from rotation.  Convenience wrapper."""
        result = self._select_rotate(advance=advance)
        return result[0] if result else ""

    def random_subset(self, n: int = 3, seed: Optional[int] = None) -> List[str]:
        """Return *n* random dataset IDs."""
        return self._select_random(n=n, seed=seed)

    # ------------------------------------------------------------------
    # Category index — hypothesis-driven field selection
    # ------------------------------------------------------------------
    def _build_category_index(self) -> None:
        """Build a category→fields index from OfficialField.category metadata.

        Group fields by their category attribute (case-insensitive).
        Falls back to an empty index if the loader is unavailable.
        """
        self._category_index.clear()
        if self._loader is None:
            return
        try:
            for field in self._loader.get_fields():
                cat = str(getattr(field, "category", "") or "").lower().strip()
                field_id = str(field.id).lower()
                if cat and field_id:
                    self._category_index.setdefault(cat, []).append(field_id)
        except Exception:
            pass

    def get_fields_by_category(self, category: str, dataset_id: str = "") -> List[str]:
        """Resolve a semantic field category name to concrete field IDs.

        Matching rules (case-insensitive):
          1. Exact match on OfficialField.category
          2. If no exact match, substring match (e.g., "profit" in "profitability_ratio")
          3. If still empty, returns an empty list

        Args:
            category: Semantic category name (e.g., "profitability_ratio", "margin").
            dataset_id: Optional dataset id. When supplied, results are limited
                to fields that actually belong to that dataset.

        Returns:
            List of field ID strings matching the category.
        """
        cat_lower = category.lower().strip()
        # Rule 1: exact match
        if cat_lower in self._category_index:
            results = list(self._category_index[cat_lower])
            if dataset_id and self._loader is not None:
                dataset_fields = {field.id.lower() for field in self._loader.get_fields(dataset_id)}
                results = [field for field in results if field.lower() in dataset_fields]
            return results

        # Rule 2: substring match — category appears in index key
        results: List[str] = []
        for idx_key, fields in self._category_index.items():
            if cat_lower in idx_key:
                results.extend(fields)

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: List[str] = []
        for f in results:
            if f not in seen:
                seen.add(f)
                deduped.append(f)
        if dataset_id and self._loader is not None:
            dataset_fields = {field.id.lower() for field in self._loader.get_fields(dataset_id)}
            deduped = [field for field in deduped if field.lower() in dataset_fields]
        return deduped

    def get_all_categories(self) -> List[str]:
        """Return all known category names from the index."""
        return sorted(self._category_index.keys())

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def available_datasets(self) -> List[str]:
        return list(self._datasets)

    @property
    def current(self) -> str:
        """Current rotation position dataset ID."""
        if not self._datasets:
            return ""
        return self._datasets[self._rotation_index % len(self._datasets)]

    @property
    def dataset_count(self) -> int:
        return len(self._datasets)
