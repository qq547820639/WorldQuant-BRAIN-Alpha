from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from brain_alpha_ops.data.schemas import OfficialDataset, OfficialField, OfficialOperator
from brain_alpha_ops.research.dataset_selector import DatasetSelector
from brain_alpha_ops.research.templates import AlphaTemplateRegistry
from brain_alpha_ops.research.theme_engine import (
    DynamicThemeEngine,
    _build_category_map,
    _normalize_operator_aliases,
)


class _Loader:
    def __init__(self):
        self.datasets = [
            OfficialDataset(id="analyst4", name="Analyst"),
            OfficialDataset(id="model77", name="Model"),
            OfficialDataset(id="pv1", name="Price Volume"),
        ]
        self.fields_by_dataset = {
            "analyst4": [
                OfficialField(id="eps_revision", category="analyst"),
                OfficialField(id="profit_margin", category="profitability_ratio"),
            ],
            "model77": [
                OfficialField(id="model_score", category="model"),
                OfficialField(id="debt_to_equity", category="valuation"),
            ],
            "pv1": [
                OfficialField(id="close", category="price"),
                OfficialField(id="volume", category="volume"),
            ],
        }
        self.operators = [
            OfficialOperator(name="rank", category="cross_sectional"),
            OfficialOperator(name="zscore", category="cross_sectional"),
            OfficialOperator(name="winsorize", category="cross_sectional"),
            OfficialOperator(name="ts_rank", category="time_series"),
            OfficialOperator(name="ts_delta", category="time_series"),
            OfficialOperator(name="ts_mean", category="time_series"),
            OfficialOperator(name="ts_std_dev", category="time_series"),
            OfficialOperator(name="ts_corr", category="time_series"),
            OfficialOperator(name="group_rank", category="group"),
            OfficialOperator(name="group_neutralize", category="group"),
            OfficialOperator(name="divide", category="arithmetic"),
            OfficialOperator(name="if_else", category="logical"),
        ]

    def get_datasets(self):
        return list(self.datasets)

    def get_fields(self, dataset_id: str = ""):
        if dataset_id:
            return list(self.fields_by_dataset.get(dataset_id, []))
        return [field for fields in self.fields_by_dataset.values() for field in fields]

    def get_operators(self):
        return list(self.operators)


class _Mapper:
    def __init__(self, fields_by_dataset):
        self.fields_by_dataset = fields_by_dataset

    def fields_for(self, dataset_id):
        return [field.id for field in self.fields_by_dataset.get(dataset_id, [])]


class _FailingFieldLoader(_Loader):
    def get_fields(self, dataset_id: str = ""):
        raise RuntimeError("field metadata unavailable")


def test_dataset_selector_strategies_and_rotation_are_deterministic():
    selector = DatasetSelector()
    selector.initialize(_Loader())

    assert selector.available_datasets == ["analyst4", "model77", "pv1"]
    assert selector.dataset_count == 3
    assert selector.current == "analyst4"
    assert selector.select("all") == ["analyst4", "model77", "pv1"]
    assert selector.rotate(advance=False) == "analyst4"
    assert selector.rotate() == "analyst4"
    assert selector.rotate() == "model77"
    assert selector.select("specific", dataset_ids=["missing", "pv1"]) == ["pv1"]
    assert selector.select("locked", dataset_ids=["analyst4"]) == ["analyst4"]
    assert selector.random_subset(n=10, seed=7) == selector.random_subset(n=10, seed=7)


def test_dataset_selector_category_index_supports_exact_substring_and_dataset_filters():
    selector = DatasetSelector()
    selector.initialize(_Loader())

    assert selector.get_fields_by_category("ANALYST") == ["eps_revision"]
    assert selector.get_fields_by_category("profit") == ["profit_margin"]
    assert selector.get_fields_by_category("profit", dataset_id="analyst4") == ["profit_margin"]
    assert selector.get_fields_by_category("profit", dataset_id="pv1") == []
    assert "profitability_ratio" in selector.get_all_categories()


def test_dataset_selector_handles_uninitialized_and_loader_failures():
    selector = DatasetSelector()
    assert selector.select("rotate") == []
    assert selector.rotate() == ""
    assert selector.current == ""

    selector.initialize(_FailingFieldLoader())
    assert selector.get_all_categories() == []
    assert selector.get_fields_by_category("anything") == []


def test_template_registry_loads_builtin_templates_and_instantiates_placeholders():
    loader = _Loader()
    registry = AlphaTemplateRegistry(loader, _Mapper(loader.fields_by_dataset))
    registry.load_templates("missing_templates.json")

    all_templates = registry.get_all()
    assert {template.id for template in all_templates} >= {"momentum_price", "cross_sectional"}
    assert registry.get("momentum_price") is not None
    assert registry.get_for_dataset("pv1")

    expr = registry.instantiate("cross_sectional", dataset_id="pv1", seed=1)
    assert "{FIELD_1}" not in expr
    assert "{GROUP}" not in expr
    assert any(field in expr for field in ["close", "volume"])


def test_template_registry_loads_custom_file_and_handles_invalid_json(tmp_path):
    custom = tmp_path / "custom_templates.json"
    custom.write_text(
        json.dumps([
            {
                "id": "custom_quality",
                "name": "Custom Quality",
                "description": "custom",
                "expression_template": "rank({FIELD_1}) + ts_rank({FIELD_2}, {WINDOW})",
                "required_field_types": ["quality"],
                "applicable_datasets": ["analyst4"],
                "tags": ["quality"],
            }
        ]),
        encoding="utf-8",
    )
    loader = _Loader()
    registry = AlphaTemplateRegistry(loader, _Mapper(loader.fields_by_dataset))
    registry.load_templates(str(custom))

    assert [template.id for template in registry.get_for_dataset("analyst4")] == ["custom_quality"]
    assert registry.get_for_dataset("pv1") == []
    expr = registry.instantiate("custom_quality", "analyst4", seed=2)
    assert "{WINDOW}" not in expr
    assert "eps_revision" in expr or "profit_margin" in expr

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    fallback = AlphaTemplateRegistry(loader, _Mapper(loader.fields_by_dataset))
    fallback.load_templates(str(invalid))
    assert fallback.get("momentum_price") is not None


def test_template_registry_unknown_and_empty_field_cases():
    loader = _Loader()
    mapper = _Mapper(loader.fields_by_dataset)
    registry = AlphaTemplateRegistry(loader, mapper)
    registry.load_templates("missing_templates.json")

    with pytest.raises(KeyError):
        registry.instantiate("missing", "pv1")

    mapper.fields_by_dataset["empty"] = []
    template = registry.get("momentum_price")
    assert template is not None
    assert registry.instantiate("momentum_price", "empty") == template.expression_template


def test_dynamic_theme_engine_builds_auto_skeletons_and_generates_templates():
    loader = _Loader()
    engine = DynamicThemeEngine(loader)
    engine.build_categories()

    assert "price" in engine.categories
    assert engine.auto_skeletons
    assert _build_category_map()["momentum"]

    generated = engine.generate("pv1", n=5, seed=3)
    assert len(generated) == 5
    assert all(template.id.startswith("theme_pv1_") for template in generated)
    assert all(template.field_slots for template in generated)
    assert not any("phantom_field" in template.expression for template in generated)
    assert engine.generate("missing", n=2) == []


def test_dynamic_theme_engine_mutates_aliases_windows_and_tracks_usage(monkeypatch):
    engine = DynamicThemeEngine(_Loader())
    engine.windows = [5]
    assert engine.windows == [5]

    monkeypatch.setattr("random.randint", lambda _low, _high: 1)
    monkeypatch.setattr("random.choice", lambda values: values[0])
    mutated = engine.mutate_expression("ts_std(close, 20) + ts_argmax(volume, 30)", "pv1", seed=4)

    assert mutated.startswith("winsorize(")
    assert "ts_std_dev" in mutated
    assert "ts_arg_max" in mutated
    assert "20" not in mutated
    assert "30" not in mutated

    engine.record_skeleton_usage("rank(close)", "momentum")
    engine.record_skeleton_usage("rank(close)", "momentum", blocked=True)
    assert engine.get_blocked_skeleton_count() == 1
    assert engine.is_skeleton_overused("rank(open)", "momentum", max_usage=2) is True


def test_dynamic_theme_engine_fill_validation_replaces_phantom_fields(monkeypatch):
    loader = _Loader()
    engine = DynamicThemeEngine(loader)
    cat_fields = {"price": ["close"], "volume": ["volume"]}

    monkeypatch.setattr("random.choice", lambda values: values[0])
    filled = engine._fill_placeholders(
        "rank({FIELD}) + rank(phantom_field) + ts_cov({FIELD}, returns, {WINDOW})",
        ["price"],
        cat_fields,
    )

    assert "close" in filled
    assert "phantom_field" not in filled
    assert "ts_covariance" in filled


def test_normalize_operator_aliases_only_rewrites_function_names():
    expr = _normalize_operator_aliases("ts_std(close, 20) + not_ts_std + ts_cov(open, close, 5)")
    assert "ts_std_dev(close, 20)" in expr
    assert "not_ts_std" in expr
    assert "ts_covariance(open, close, 5)" in expr
