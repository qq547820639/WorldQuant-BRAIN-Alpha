from __future__ import annotations

from dataclasses import dataclass

from brain_alpha_ops.data.field_dataset_mapper import FieldDatasetMapper


@dataclass
class _Dataset:
    id: str


@dataclass
class _Field:
    id: str
    dataset: _Dataset | None


class _Loader:
    def __init__(self, fields: list[_Field]) -> None:
        self._fields = fields

    def get_fields(self) -> list[_Field]:
        return self._fields


def test_field_dataset_mapper_builds_bidirectional_indexes_and_normalizes_fields():
    mapper = FieldDatasetMapper().build(
        _Loader(
            [
                _Field("Close", _Dataset("ds1")),
                _Field("Volume", _Dataset("ds1")),
                _Field("close", _Dataset("ds2")),
                _Field("OPEN", _Dataset("ds2")),
                _Field("ignored", None),
            ]
        )
    )

    assert mapper.fields_for("ds1") == ["close", "volume"]
    assert mapper.field_count("ds2") == 2
    assert mapper.datasets_for("CLOSE") == ["ds1", "ds2"]
    assert mapper.is_common_field("close", min_datasets=2) is True
    assert mapper.is_common_field("volume", min_datasets=2) is False


def test_field_dataset_mapper_set_operations_and_empty_overlap():
    mapper = FieldDatasetMapper().build(
        _Loader(
            [
                _Field("close", _Dataset("ds1")),
                _Field("volume", _Dataset("ds1")),
                _Field("close", _Dataset("ds2")),
                _Field("open", _Dataset("ds2")),
            ]
        )
    )

    assert mapper.common_fields([]) == []
    assert mapper.common_fields(["ds1", "ds2"]) == ["close"]
    assert mapper.unique_fields("ds1", ["ds2"]) == ["volume"]
    assert mapper.dataset_overlap("ds1", "ds2") == 1 / 3
    assert mapper.dataset_overlap("missing1", "missing2") == 0.0
