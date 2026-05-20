"""Helpers for obtaining official BRAIN data-set metadata."""

from __future__ import annotations

from typing import Any, Callable


DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


def list_official_datasets_or_derive(
    api: Any,
    fields: list[dict[str, Any]],
    *,
    region: str = "",
    datasets_from_fields: DatasetsFromFields,
) -> list[dict[str, Any]]:
    """Prefer the official /data-sets API, falling back to official field metadata."""
    list_datasets = getattr(api, "list_datasets", None)
    if callable(list_datasets):
        try:
            datasets = list_datasets("all", region)
        except TypeError:
            datasets = list_datasets("all")
        except Exception:
            datasets = []
        if datasets:
            return datasets
    return datasets_from_fields(fields)
