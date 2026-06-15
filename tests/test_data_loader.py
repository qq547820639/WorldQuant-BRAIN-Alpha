from __future__ import annotations

from brain_alpha_ops.data.loader import OfficialDataLoader
from brain_alpha_ops.data.schemas import OfficialDataset, OfficialField, OfficialOperator


def test_refresh_preserves_existing_data_when_reload_fails(monkeypatch):
    loader = OfficialDataLoader()
    loader._fields = {"old": OfficialField(id="old", description="old field")}
    loader._fields_by_name = loader._rebuild_name_index(loader._fields)
    loader._operators = {"rank": OfficialOperator(name="rank")}
    loader._datasets = {"ds": OfficialDataset(id="ds", name="Dataset")}

    def fail_load_all(self, data_dir="data"):
        assert loader.get_fields()[0].id == "old"
        raise RuntimeError("broken context")

    monkeypatch.setattr(OfficialDataLoader, "load_all", fail_load_all)

    result = loader.refresh("data", max_retries=1)

    assert result["status"] == "refresh_failed"
    assert loader.get_fields()[0].id == "old"
    assert loader.get_operator("rank") is not None
    assert loader.get_dataset("ds") is not None


def test_refresh_replaces_existing_data_after_successful_fresh_load(monkeypatch):
    loader = OfficialDataLoader()
    loader._fields = {"old": OfficialField(id="old", description="old field")}
    loader._fields_by_name = loader._rebuild_name_index(loader._fields)
    loader._operators = {"oldop": OfficialOperator(name="oldop")}
    loader._datasets = {"old_ds": OfficialDataset(id="old_ds", name="Old")}

    def load_fresh(self, data_dir="data"):
        self._fields = {"new": OfficialField(id="new", description="new field")}
        self._fields_by_name = self._rebuild_name_index(self._fields)
        self._operators = {"rank": OfficialOperator(name="rank")}
        self._datasets = {"ds": OfficialDataset(id="ds", name="Dataset")}

    monkeypatch.setattr(OfficialDataLoader, "load_all", load_fresh)

    result = loader.refresh("data", max_retries=1)

    assert result["status"] in ("refreshed", "no_change")
    assert [field.id for field in loader.get_fields()] == ["new"]
    assert loader.get_operator("rank") is not None
    assert loader.get_dataset("ds") is not None


def test_load_fields_normalizes_none_description(tmp_path):
    path = tmp_path / "official_fields.json"
    path.write_text('[{"id": "close", "description": null}]', encoding="utf-8")

    loader = OfficialDataLoader()
    loader._load_fields(path)

    field = loader.get_field_by_name("close")
    assert field is not None
    assert field.description == ""
