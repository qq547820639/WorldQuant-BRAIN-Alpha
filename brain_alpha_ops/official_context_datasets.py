"""Helpers for obtaining official BRAIN data-set metadata."""

from __future__ import annotations

import logging
from typing import Any, Callable


DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]

logger = logging.getLogger(__name__)


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
            try:
                datasets = list_datasets("all")
            except Exception:
                logger.warning("official datasets API unavailable; deriving datasets from fields", exc_info=True)
                datasets = []
        except Exception:
            logger.warning("official datasets API unavailable; deriving datasets from fields", exc_info=True)
            datasets = []
        if datasets:
            return datasets
    return datasets_from_fields(fields)
