import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive


class DatasetAPI:
    def __init__(self, *, datasets=None, error: Exception | None = None):
        self.datasets = datasets
        self.error = error

    def list_datasets(self, *_args):
        if self.error is not None:
            raise self.error
        return list(self.datasets or [])


def test_list_official_datasets_prefers_api_results():
    datasets = list_official_datasets_or_derive(
        DatasetAPI(datasets=[{"id": "official"}]),
        [{"id": "close"}],
        datasets_from_fields=lambda _fields: [{"id": "derived"}],
    )

    assert datasets == [{"id": "official"}]


def test_list_official_datasets_uses_field_fallback_with_warning():
    warnings = []

    datasets = list_official_datasets_or_derive(
        DatasetAPI(error=RuntimeError("datasets failed")),
        [{"id": "close"}],
        datasets_from_fields=lambda fields: [{"id": "derived", "field_count": len(fields)}],
        fallback_warning=lambda message, exc: warnings.append((message, str(exc))),
    )

    assert datasets == [{"id": "derived", "field_count": 1}]
    assert warnings == [
        ("official datasets API unavailable; deriving datasets from fields", "datasets failed")
    ]


def test_list_official_datasets_raises_when_api_and_fallback_both_empty():
    with pytest.raises(BrainAPIError, match="fallback returned no datasets"):
        list_official_datasets_or_derive(
            DatasetAPI(error=RuntimeError("datasets failed")),
            [{"id": "close"}],
            datasets_from_fields=lambda _fields: [],
        )


def test_list_official_datasets_raises_when_api_returns_empty_and_fallback_empty():
    with pytest.raises(BrainAPIError, match="official datasets API returned no datasets"):
        list_official_datasets_or_derive(
            DatasetAPI(datasets=[]),
            [{"id": "close"}],
            datasets_from_fields=lambda _fields: [],
        )


def test_list_official_datasets_raises_when_fallback_fails_after_api_error():
    with pytest.raises(BrainAPIError, match="fallback failed"):
        list_official_datasets_or_derive(
            DatasetAPI(error=RuntimeError("datasets failed")),
            [{"id": "close"}],
            datasets_from_fields=lambda _fields: (_ for _ in ()).throw(RuntimeError("derive failed")),
        )
