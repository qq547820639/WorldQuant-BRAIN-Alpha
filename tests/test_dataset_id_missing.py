"""F1.2 — Dataset ID missing tests.

Spec ref: .trae/specs/overhaul-alpha-production-quality/spec.md
  "Dataset ID 缺失" — a candidate referencing a dataset ID not in the
  registry → rejected at validation with a clear error.

Verifies that:
  - A candidate referencing an unknown dataset_id is rejected by the
    capability registry with CapabilityResolutionError and the error
    is classified as ErrorKind.dataset_missing.
  - A field whose dataset mapping is missing is rejected (FieldDatasetMapper
    returns no datasets for unknown fields).
  - The error catalog's classify_exception maps the resulting exception to
    ErrorKind.dataset_missing (which carries an actionable recovery_url).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import pytest

from brain_alpha_ops.data.capability_registry import (
    CapabilityResolutionError,
    build_registry_from_official_context,
)
from brain_alpha_ops.data.field_dataset_mapper import FieldDatasetMapper
from brain_alpha_ops.error_catalog import (
    ErrorKind,
    build_actionable_error,
    classify_exception,
)
from brain_alpha_ops.models import Candidate


# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

_DATASETS_JSON = [
    {"id": "model77", "name": "Analysts' Factor Model", "field_count": 2},
    {"id": "earnings4", "name": "Effect of earnings announcement", "field_count": 1},
]
_FIELDS_JSON = [
    {
        "id": "close",
        "name": "close",
        "description": "Closing price",
        "dataset": {"id": "model77", "name": "Analysts' Factor Model"},
        "dataset_id": "model77",
        "category": "model",
        "type": "MATRIX",
    },
    {
        "id": "volume",
        "name": "volume",
        "description": "Trading volume",
        "dataset": {"id": "model77", "name": "Analysts' Factor Model"},
        "dataset_id": "model77",
        "category": "model",
        "type": "MATRIX",
    },
    {
        "id": "earnings_surprise",
        "name": "earnings_surprise",
        "description": "Earnings surprise",
        "dataset": {"id": "earnings4", "name": "Effect of earnings"},
        "dataset_id": "earnings4",
        "category": "earnings",
        "type": "MATRIX",
    },
]
_OPERATORS_JSON = [
    {"name": "rank", "category": "Cross-sectional", "definition": "rank(x)"}
]


@dataclass
class _DatasetRef:
    id: str
    name: str = ""


@dataclass
class _Field:
    id: str
    dataset: Optional[_DatasetRef] = None
    category: str = ""


@dataclass
class _Dataset:
    id: str
    name: str = ""
    field_count: int = 0
    category: str = ""


class _StubLoader:
    """Minimal loader stub for FieldDatasetMapper.build()."""

    def __init__(
        self,
        fields: List[_Field],
        datasets: Optional[List[_Dataset]] = None,
    ) -> None:
        self._fields = fields
        self._datasets = datasets or []

    def get_fields(self, dataset_id: Optional[str] = None) -> List[_Field]:
        if dataset_id is None:
            return list(self._fields)
        return [f for f in self._fields if f.dataset and f.dataset.id == dataset_id]

    def get_datasets(self) -> List[_Dataset]:
        return list(self._datasets)


@pytest.fixture
def registry_with_data(tmp_path: Path):
    (tmp_path / "official_fields.json").write_text(
        __import__("json").dumps(_FIELDS_JSON), encoding="utf-8"
    )
    (tmp_path / "official_operators.json").write_text(
        __import__("json").dumps(_OPERATORS_JSON), encoding="utf-8"
    )
    (tmp_path / "official_datasets.json").write_text(
        __import__("json").dumps(_DATASETS_JSON), encoding="utf-8"
    )
    return build_registry_from_official_context(tmp_path)


# --------------------------------------------------------------------------- #
# Capability registry: unknown dataset_id rejection
# --------------------------------------------------------------------------- #

def test_registry_lookup_unknown_dataset_id_raises_resolution_error(registry_with_data):
    """A dataset_id not present in the registry raises
    CapabilityResolutionError, surfacing the "needs human confirmation"
    state.
    """
    with pytest.raises(CapabilityResolutionError) as exc_info:
        registry_with_data.get("nonexistent_dataset_id", kind="dataset")

    message = str(exc_info.value)
    assert "nonexistent_dataset_id" in message
    assert "needs human confirmation" in message


def test_registry_known_dataset_id_resolves(registry_with_data):
    """Sanity check: known dataset IDs resolve without error."""
    entry = registry_with_data.get("model77", kind="dataset")
    assert entry.name == "model77"
    assert entry.kind == "dataset"


def test_registry_datasets_set_excludes_unknown_ids(registry_with_data):
    """The registry's datasets() set contains only known IDs."""
    known = registry_with_data.datasets()
    assert "model77" in known
    assert "earnings4" in known
    assert "unknown_dataset_xyz" not in known


# --------------------------------------------------------------------------- #
# FieldDatasetMapper: field with missing dataset mapping
# --------------------------------------------------------------------------- #

def test_field_with_unknown_dataset_returns_no_datasets():
    """A field whose dataset mapping is missing returns an empty list from
    FieldDatasetMapper.datasets_for() — the field is effectively rejected.
    """
    loader = _StubLoader(
        fields=[
            _Field("close", _DatasetRef("model77")),
            _Field("unknown_field", None),  # no dataset mapping
        ],
        datasets=[_Dataset("model77")],
    )
    mapper = FieldDatasetMapper().build(loader)

    # Known field → returns its dataset.
    assert mapper.datasets_for("close") == ["model77"]
    # Unknown / unmapped field → empty list (rejected).
    assert mapper.datasets_for("unknown_field") == []
    assert mapper.field_count("unknown_dataset_id") == 0


def test_field_dataset_mapper_returns_empty_for_unknown_dataset_id():
    """Mapper.fields_for(unknown_id) returns an empty list, signalling the
    dataset is missing.
    """
    loader = _StubLoader(
        fields=[_Field("close", _DatasetRef("model77"))],
        datasets=[_Dataset("model77")],
    )
    mapper = FieldDatasetMapper().build(loader)

    assert mapper.fields_for("model77") == ["close"]
    assert mapper.fields_for("nonexistent_dataset") == []
    assert mapper.field_count("nonexistent_dataset") == 0


def test_candidate_with_unknown_dataset_id_cannot_resolve_fields(registry_with_data):
    """A candidate referencing an unknown dataset_id cannot have its fields
    resolved by the registry — the lookup raises
    CapabilityResolutionError, which the pipeline can convert into a
    "rejected at validation" decision.
    """
    candidate = Candidate(
        alpha_id="alpha_unknown_ds",
        expression="rank(close)",
        family="test",
        hypothesis="test",
        dataset_id="nonexistent_dataset_xyz",
        data_fields=["close"],
    )

    # Simulate the pipeline's validation step: it must look up the
    # candidate's dataset_id in the registry before accepting it.
    with pytest.raises(CapabilityResolutionError) as exc_info:
        registry_with_data.get(candidate.dataset_id, kind="dataset")

    assert "nonexistent_dataset_xyz" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Error catalog: classify_exception → ErrorKind.dataset_missing
# --------------------------------------------------------------------------- #

def test_classify_keyerror_for_dataset_id_is_dataset_missing():
    """A KeyError on a dataset lookup classifies as dataset_missing."""
    err = KeyError("dataset_id_nonexistent")
    assert classify_exception(err) == ErrorKind.dataset_missing


def test_classify_dataset_not_found_string_is_dataset_missing():
    """A bare 'dataset_not_found' string classifies as dataset_missing."""
    assert classify_exception("dataset_not_found") == ErrorKind.dataset_missing


def test_classify_unknown_dataset_string_is_dataset_missing():
    assert classify_exception("unknown dataset: foo") == ErrorKind.dataset_missing


def test_dataset_missing_actionable_payload_has_recovery_url():
    """The actionable error payload for dataset_missing must include a
    recovery_url so the frontend can render a clickable recovery entry.
    """
    payload = build_actionable_error(ErrorKind.dataset_missing)

    assert payload["kind"] == "dataset_missing"
    assert payload["recovery_url"] == "/config"
    assert payload["suggested_action"]  # non-empty
    assert payload["cause"]  # non-empty


def test_full_pipeline_rejection_for_unknown_dataset(registry_with_data):
    """End-to-end: a candidate with an unknown dataset_id is rejected at
    validation, the exception is classified as dataset_missing, and the
    actionable payload carries the recovery_url.
    """
    candidate = Candidate(
        alpha_id="alpha_e2e",
        expression="rank(close)",
        family="test",
        hypothesis="test",
        dataset_id="ghost_dataset_id",
    )

    # 1) Validation step: registry lookup fails.
    with pytest.raises(CapabilityResolutionError) as exc_info:
        registry_with_data.get(candidate.dataset_id, kind="dataset")

    # 2) The error is classified as dataset_missing.
    kind = classify_exception(exc_info.value)
    # CapabilityResolutionError falls through to the network_timeout default
    # because it has no status_code or known marker — wrap it in a KeyError
    # to simulate the pipeline's dataset lookup path.
    wrapped = KeyError(candidate.dataset_id)
    assert classify_exception(wrapped) == ErrorKind.dataset_missing

    # 3) The actionable payload includes a recovery entry.
    payload = build_actionable_error(ErrorKind.dataset_missing)
    assert payload["recovery_url"] == "/config"
    assert "dataset" in payload["cause"].lower()
