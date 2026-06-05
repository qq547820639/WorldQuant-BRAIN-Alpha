"""Helpers for obtaining official BRAIN data-set metadata."""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPIError


DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
DatasetFallbackWarning = Callable[[str, Exception], None]

logger = logging.getLogger(__name__)


def list_official_datasets_or_derive(
    api: Any,
    fields: list[dict[str, Any]],
    *,
    region: str = "",
    datasets_from_fields: DatasetsFromFields,
    fallback_warning: DatasetFallbackWarning | None = None,
) -> list[dict[str, Any]]:
    """Prefer the official /data-sets API, falling back to official field metadata."""
    list_datasets = getattr(api, "list_datasets", None)
    api_error: Exception | None = None
    datasets: list[dict[str, Any]] = []
    if callable(list_datasets):
        try:
            datasets = list_datasets("all", region)
        except TypeError:
            try:
                datasets = list_datasets("all")
            except Exception as exc:
                _warn_dataset_fallback(exc, fallback_warning)
                api_error = exc
        except Exception as exc:
            _warn_dataset_fallback(exc, fallback_warning)
            api_error = exc
        if datasets:
            return datasets
    try:
        derived = datasets_from_fields(fields)
    except Exception as exc:
        if api_error is not None:
            raise BrainAPIError(
                "official datasets API unavailable and field-derived dataset fallback failed"
            ) from api_error
        raise BrainAPIError("field-derived dataset fallback failed") from exc
    if derived:
        return derived
    if api_error is not None:
        raise BrainAPIError(
            "official datasets API unavailable and field-derived dataset fallback returned no datasets"
        ) from api_error
    return []


def _warn_dataset_fallback(exc: Exception, fallback_warning: DatasetFallbackWarning | None) -> None:
    message = "official datasets API unavailable; deriving datasets from fields"
    logger.warning(message, exc_info=True)
    if fallback_warning is not None:
        fallback_warning(message, exc)
