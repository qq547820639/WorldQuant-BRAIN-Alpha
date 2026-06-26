"""Data access mixin for OfficialBrainAPI."""

from __future__ import annotations

from typing import Any


class _OfficialDataAccessMixin:
    """Data discovery and alpha query thin wrappers.

    These methods delegate to ``self._context_data`` (an
    ``_OfficialContextDataClient`` bound component).
    """

    def list_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        progress_callback=None,
    ) -> list[dict]:
        """List all available data fields from BRAIN platform.

        Args:
            query: Search query (default: "all" for all fields)
            region: Geographic region filter (e.g., "USA", "JAPAN")
            dataset: Dataset ID filter
            progress_callback: Optional callback for pagination progress

        Returns:
            List of field dictionaries with id, name, category, etc.
        """
        return self._context_data.list_fields(
            query,
            region,
            dataset=dataset,
            progress_callback=progress_callback,
        )

    def list_datasets(
        self,
        query: str = "all",
        region: str = "",
        progress_callback=None,
    ) -> list[dict]:
        return self._context_data.list_datasets(query, region, progress_callback=progress_callback)

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        return self._context_data.list_operators(query, progress_callback=progress_callback)

    def list_data_categories(self, progress_callback=None) -> list[dict]:
        return self._context_data.list_data_categories(progress_callback=progress_callback)

    def search_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        **filters,
    ) -> dict:
        return self._context_data.search_datasets_limited(
            query,
            region,
            **filters,
            limit=limit,
            offset=offset,
        )

    def discover_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        options: dict[str, Any] | None = None,
        **filters,
    ) -> dict:
        return self._context_data.discover_datasets_limited(
            query,
            region,
            options=options,
            **filters,
        )

    def search_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.search_datasets(
            query,
            region,
            **filters,
            limit=limit,
            offset=offset,
            progress_callback=progress_callback,
        )

    def discover_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        options: dict[str, Any] | None = None,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.discover_datasets(
            query,
            region,
            options=options,
            progress_callback=progress_callback,
            **filters,
        )

    def search_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        **filters,
    ) -> dict:
        return self._context_data.search_fields_limited(
            query,
            region,
            dataset=dataset,
            **filters,
            limit=limit,
            offset=offset,
        )

    def discover_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        dataset_id: str = "",
        options: dict[str, Any] | None = None,
        **filters,
    ) -> dict:
        return self._context_data.discover_fields_limited(
            query,
            region,
            dataset=dataset,
            dataset_id=dataset_id,
            options=options,
            **filters,
        )

    def search_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.search_fields(
            query,
            region,
            dataset=dataset,
            **filters,
            limit=limit,
            offset=offset,
            progress_callback=progress_callback,
        )

    def discover_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        dataset_id: str = "",
        options: dict[str, Any] | None = None,
        progress_callback=None,
        **filters,
    ) -> list[dict]:
        return self._context_data.discover_fields(
            query,
            region,
            dataset=dataset,
            dataset_id=dataset_id,
            options=options,
            progress_callback=progress_callback,
            **filters,
        )

    def locate_dataset(self, dataset_id: str) -> dict:
        return self._context_data.locate_dataset(dataset_id)

    def locate_field(self, field_id: str) -> dict:
        return self._context_data.locate_field(field_id)

    def locate_alpha(self, alpha_id: str) -> dict:
        return self._context_data.locate_alpha(alpha_id)

    def get_dataset(self, dataset_id: str = "", *, id: str = "") -> dict:
        return self._context_data.get_dataset(dataset_id, id=id)

    def get_field(self, field_id: str = "", *, id: str = "") -> dict:
        return self._context_data.get_field(field_id, id=id)

    def get_alpha(self, alpha_id: str = "", *, id: str = "") -> dict:
        return self._context_data.get_alpha(alpha_id, id=id)

    def filter_alphas_limited(self, **filters) -> dict:
        return self._context_data.filter_alphas_limited(**filters)

    def query_alphas_limited(self, *, options: dict[str, Any] | None = None, **filters) -> dict:
        return self._context_data.query_alphas_limited(options=options, **filters)

    def filter_alphas(self, progress_callback=None, **filters) -> list[dict]:
        return self._context_data.filter_alphas(progress_callback=progress_callback, **filters)

    def patch_properties(
        self,
        alpha_id: str,
        *,
        name: str | None = None,
        alpha_type: str | None = None,
        decay: int | None = None,
        neutralization: str | None = None,
        pasteurization: str | None = None,
        truncation: Any = None,
        unit_handling: str | None = None,
        nan_handling: str | None = None,
        hidden: bool | None = None,
        favorite: bool | None = None,
        category: str | None = None,
        color: str | None = None,
        tag: str | None = None,
        stage: str | None = None,
        **extra: Any,
    ) -> dict:
        return self._context_data.patch_properties(
            alpha_id,
            name=name,
            alpha_type=alpha_type,
            decay=decay,
            neutralization=neutralization,
            pasteurization=pasteurization,
            truncation=truncation,
            unit_handling=unit_handling,
            nan_handling=nan_handling,
            hidden=hidden,
            favorite=favorite,
            category=category,
            color=color,
            tag=tag,
            stage=stage,
            **extra,
        )

    def query_alphas(
        self,
        progress_callback=None,
        *,
        options: dict[str, Any] | None = None,
        **filters,
    ) -> list[dict]:
        return self._context_data.query_alphas(
            progress_callback=progress_callback,
            options=options,
            **filters,
        )

    def list_user_alphas(
        self,
        sync_range: str = "all",
        progress_callback=None,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        return self._context_data.list_user_alphas(
            sync_range,
            progress_callback=progress_callback,
            force_refresh=force_refresh,
        )
