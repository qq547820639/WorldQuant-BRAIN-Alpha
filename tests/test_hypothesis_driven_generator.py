"""Tests for HypothesisDrivenGenerator — mode routing, generation, output compatibility."""

import logging
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch

from brain_alpha_ops.research.hypothesis_driven_generator import (
    HypothesisDrivenGenerator,
    GenerationModeRouter,
    HypothesisSelector,
    ExpressionFamilySelector,
    FieldSelector,
    ContextAdapter,
)
from brain_alpha_ops.research.hypothesis_library import (
    HypothesisLibrary,
    Hypothesis,
    ExpressionFamily,
    FieldCategoryDef,
    GenerationMeta,
)
from brain_alpha_ops.research.expression_ast import expression_key, parse_expression
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
    is_high_turnover_generation_risk,
)

HYPOTHESES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "brain_alpha_ops", "research", "hypotheses",
)


# ── Helpers ──

def _make_mock_library() -> HypothesisLibrary:
    """Create and load the real hypothesis library."""
    return HypothesisLibrary(HYPOTHESES_DIR).load_all()


def _make_mock_theme_engine():
    """Create a mock DynamicThemeEngine."""
    engine = MagicMock()
    from brain_alpha_ops.research.theme_engine import ThemeTemplate
    tmpl = ThemeTemplate(
        id="test_tmpl",
        name="Test Template",
        category="momentum",
        expression="ts_rank({FIELD}, {WINDOW})",
        field_slots=["{FIELD}"],
    )
    engine.generate.return_value = [tmpl]
    engine.mutate_expression.return_value = "rank(ts_delta(eps_fy1_3m_rev, 60))"
    return engine


def _make_mock_selector():
    """Create a mock DatasetSelector."""
    selector = MagicMock()
    selector.get_fields_by_category.return_value = [
        "eps_fy1_3m_rev", "sales_fy1_rev", "roe", "roic",
    ]
    return selector


def _make_mock_mapper():
    """Create a mock FieldDatasetMapper."""
    mapper = MagicMock()
    mapper.fields_for.return_value = ["eps_fy1_3m_rev", "sales_fy1_rev", "roe"]
    return mapper


# ── GenerationModeRouter ──

def test_router_parse_default_ratio():
    """Verify default ratio parsing."""
    router = GenerationModeRouter("70/20/10")
    assert router._hypothesis_ratio == 0.7
    assert router._experience_ratio == 0.2
    assert router._random_ratio == 0.1


def test_router_parse_custom_ratio():
    """Verify custom ratio parsing."""
    router = GenerationModeRouter("50/30/20")
    assert router._hypothesis_ratio == 0.5
    assert router._experience_ratio == 0.3
    assert router._random_ratio == 0.2


def test_router_returns_valid_mode():
    """Verify route() always returns a valid mode string."""
    router = GenerationModeRouter("70/20/10")
    for _ in range(100):
        mode = router.route()
        assert mode in GenerationModeRouter.VALID_MODES


def test_router_counts_are_reasonable():
    """Verify mode distribution approximately matches ratio over many calls."""
    router = GenerationModeRouter("70/20/10")
    for _ in range(1000):
        router.route()
    actual = router.actual_ratios
    total = sum(actual.values())
    # Allow ±15% tolerance
    assert 0.55 <= actual["hypothesis_driven"] <= 0.85, \
        f"hypothesis_driven ratio={actual['hypothesis_driven']:.2f}"
    assert 0.05 <= actual["experience_feedback"] <= 0.35, \
        f"experience_feedback ratio={actual['experience_feedback']:.2f}"


def test_router_reset():
    """Verify reset() zeros all counters."""
    router = GenerationModeRouter("70/20/10")
    router.route()
    router.route()
    router.reset()
    actual = router.actual_ratios
    assert actual["hypothesis_driven"] == 0.0
    assert actual["experience_feedback"] == 0.0
    assert actual["random_exploration"] == 0.0


# ── HypothesisSelector ──

def test_hypothesis_selector_returns_hypothesis():
    """Verify selector returns a valid Hypothesis from the library."""
    lib = _make_mock_library()
    selector = HypothesisSelector(lib)
    for _ in range(10):
        hyp = selector.select()
        assert hyp is not None
        assert hyp.id


def test_hypothesis_selector_excludes_recently_used():
    """Verify that recently used hypotheses are excluded (when possible)."""
    lib = _make_mock_library()
    selector = HypothesisSelector(lib)
    selector.exclude_recently_used(3)
    seen: set[str] = set()
    # With 8 hypotheses and max_recency=3, we should see diversity
    for _ in range(5):
        hyp = selector.select()
        seen.add(hyp.id)
    assert len(seen) >= 2, f"Expected diversity, only got {len(seen)} unique: {seen}"


# ── ExpressionFamilySelector ──

def test_expr_family_selector_returns_family():
    """Verify expression family selection works."""
    lib = _make_mock_library()
    hyp = lib.get_by_id("earnings_revision_momentum")
    sel = ExpressionFamilySelector()
    family = sel.select(hyp)
    assert family is not None
    assert family.id
    assert family.structure


def test_expr_family_selector_window():
    """Verify window selection returns a valid value."""
    lib = _make_mock_library()
    hyp = lib.get_by_id("earnings_revision_momentum")
    expr_sel = ExpressionFamilySelector()
    family = expr_sel.select(hyp)
    window = expr_sel.select_window(family)
    assert isinstance(window, int)
    assert window > 0


# ── FieldSelector ──

def test_field_selector_resolves_categories():
    """Verify field selector delegates to DatasetSelector."""
    mock_sel = _make_mock_selector()
    lib = _make_mock_library()
    hyp = lib.get_by_id("earnings_revision_momentum")
    field_sel = FieldSelector(mock_sel)

    fields = field_sel.select_fields(hyp, "analyst4", count=2)
    assert len(fields) >= 1, f"Expected at least 1 field, got {len(fields)}"
    assert all(isinstance(f, str) for f in fields)


def test_field_selector_respects_count():
    """Verify field selector returns at most count fields."""
    mock_sel = _make_mock_selector()
    lib = _make_mock_library()
    hyp = lib.get_by_id("earnings_revision_momentum")
    field_sel = FieldSelector(mock_sel)

    for count in [1, 2, 3]:
        fields = field_sel.select_fields(hyp, "analyst4", count=count)
        assert len(fields) <= count


def test_field_selector_semantic_fallback_uses_active_dataset_fields(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.dataset_selector import DatasetSelector

    (tmp_path / "official_fields.json").write_text(
        json.dumps(
            [
                {"name": "anl4_eps_previous_estimate_value", "category": "analyst"},
                {"name": "sales_estimate_stddev_quarterly", "category": "analyst"},
                {"name": "debt_ratio", "category": "fundamental"},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps(
            [
                {"id": "analyst4", "name": "Analyst", "field_count": 2, "category": {"id": "analyst"}},
                {"id": "fundamental6", "name": "Fundamental", "field_count": 1, "category": {"id": "fundamental"}},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(json.dumps([{"name": "rank"}]), encoding="utf-8")
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    selector = DatasetSelector()
    selector.initialize(loader)
    field_selector = FieldSelector(selector)
    hypothesis = Hypothesis.from_dict(
        {
            "id": "semantic",
            "name": "Semantic fallback",
            "rationale": {"theory": "Fine-grained categories should resolve to active official fields."},
            "field_categories": [
                {
                    "category": "earnings_estimate_revision",
                    "priority": "P0",
                    "examples": ["eps_previous_estimate_value", "earnings_per_share_estimate_count"],
                }
            ],
        }
    )

    fields = field_selector.select_fields(hypothesis, "analyst4", count=2)

    assert fields
    assert set(fields) <= {"anl4_eps_previous_estimate_value", "sales_estimate_stddev_quarterly"}
    assert "debt_ratio" not in fields


def test_field_selector_semantic_fallback_excludes_metadata_fields(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.dataset_selector import DatasetSelector

    (tmp_path / "official_fields.json").write_text(
        json.dumps(
            [
                {"name": "eps_reporting_currency", "category": "analyst", "coverage": 1.0},
                {"name": "anl4_eps_flag", "category": "analyst", "coverage": 1.0},
                {"name": "anl4_eps_previous_estimate_value", "category": "analyst", "coverage": 0.9},
                {"name": "sales_estimate_stddev_quarterly", "category": "analyst", "coverage": 0.8},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps([{"id": "analyst4", "name": "Analyst", "category": {"id": "analyst"}}]),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(json.dumps([{"name": "rank"}]), encoding="utf-8")
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    selector = DatasetSelector()
    selector.initialize(loader)
    field_selector = FieldSelector(selector)
    hypothesis = Hypothesis.from_dict(
        {
            "id": "semantic",
            "name": "Semantic fallback",
            "field_categories": [
                {
                    "category": "earnings_estimate_revision",
                    "priority": "P0",
                    "examples": ["eps_previous_estimate_value", "earnings_per_share_estimate_count"],
                }
            ],
        }
    )

    fields = field_selector.select_fields(hypothesis, "analyst4", count=3)

    assert set(fields) == {"anl4_eps_previous_estimate_value", "sales_estimate_stddev_quarterly"}


# ── ContextAdapter ──

def test_context_adapter_returns_valid_context():
    """Verify context adapter returns region/universe/delay."""
    lib = _make_mock_library()
    hyp = lib.get_by_id("earnings_revision_momentum")
    adapter = ContextAdapter()
    ctx = adapter.adapt(hyp)
    assert "region" in ctx
    assert "universe" in ctx
    assert "delay" in ctx
    assert ctx["region"] in hyp.adaptation.preferred_regions or ctx["region"] == "USA"
    assert ctx["delay"] in hyp.adaptation.preferred_delays


def test_context_adapter_filters_available():
    """Verify context adapter filters by available regions/universes."""
    lib = _make_mock_library()
    hyp = lib.get_by_id("earnings_revision_momentum")
    adapter = ContextAdapter()
    adapter.set_available_context(
        regions=["USA", "ASIA"],
        universes=["TOP3000"],
    )
    ctx = adapter.adapt(hyp)
    assert ctx["region"] in ["USA", "ASIA"]
    assert ctx["universe"] == "TOP3000"


# ── HypothesisDrivenGenerator ──

def test_generator_has_public_api():
    """Verify HypothesisDrivenGenerator has required public methods."""
    lib = _make_mock_library()
    engine = _make_mock_theme_engine()
    selector = _make_mock_selector()
    mapper = _make_mock_mapper()

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=mapper,
        theme_engine=engine,
        selector=selector,
        library=lib,
        ratio_str="70/20/10",
    )
    assert hasattr(gen, 'generate')
    assert hasattr(gen, 'update_context')
    assert hasattr(gen, 'set_dataset')
    assert hasattr(gen, 'set_experience_guidance')


def test_generator_generates_candidates():
    """Verify generate() returns Candidate objects."""
    lib = _make_mock_library()
    engine = _make_mock_theme_engine()
    selector = _make_mock_selector()
    mapper = _make_mock_mapper()

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=mapper,
        theme_engine=engine,
        selector=selector,
        library=lib,
        ratio_str="70/20/10",
    )
    gen.set_dataset("analyst4")
    gen.update_context(
        [{"name": "eps_fy1_3m_rev"}, {"name": "sales_fy1_rev"}, {"name": "roe"}],
        [{"name": "rank"}, {"name": "ts_delta"}, {"name": "ts_rank"}],
    )

    candidates = gen.generate(5, "analyst4")
    assert len(candidates) >= 1, f"Expected at least 1 candidate, got {len(candidates)}"
    for c in candidates:
        assert c.alpha_id.startswith("alpha_")
        assert c.expression
        assert len(c.source_tags) >= 1


def test_generator_retries_after_duplicate_expression_skips():
    """Direct generator calls should keep filling after duplicate skips."""
    from brain_alpha_ops.research.theme_engine import ThemeTemplate

    class DuplicateThenUniqueEngine:
        def __init__(self):
            self._expressions = iter(
                [
                    "rank(close)",
                    "rank(close)",
                    "rank(volume)",
                    "rank(volume)",
                    "rank(open)",
                ]
            )

        def generate(self, dataset_id, n=1):
            return [
                ThemeTemplate(
                    id="duplicate_probe",
                    name="Duplicate Probe",
                    category="momentum",
                    expression="rank({FIELD})",
                    field_slots=["close"],
                )
            ]

        def mutate_expression(self, expression, dataset_id, seed=None):
            return next(self._expressions)

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=DuplicateThenUniqueEngine(),
        selector=None,
        library=None,
        ratio_str="0/0/100",
    )
    gen.update_context(
        [{"name": "close"}, {"name": "volume"}, {"name": "open"}],
        [{"name": "rank"}],
    )

    candidates = gen.generate(3, "pv1")

    assert [candidate.expression for candidate in candidates] == [
        "rank(close)",
        "rank(volume)",
        "rank(open)",
    ]


def test_generated_candidate_has_source_tags():
    """Verify generated candidates have proper source tags."""
    lib = _make_mock_library()
    engine = _make_mock_theme_engine()
    selector = _make_mock_selector()
    mapper = _make_mock_mapper()

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=mapper,
        theme_engine=engine,
        selector=selector,
        library=lib,
        ratio_str="100/0/0",  # Force hypothesis_driven only
    )
    gen.set_dataset("analyst4")
    gen.update_context(
        [{"name": "eps_fy1_3m_rev"}, {"name": "sales_fy1_rev"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )

    candidates = gen.generate(5, "analyst4")
    for c in candidates:
        assert any(
            tag in c.source_tags
            for tag in ["hypothesis_driven", "experience_feedback", "random_exploration"]
        ), f"Expected source tag, got: {c.source_tags}"


def test_generated_candidate_template_source_has_meta():
    """Verify template_source contains GenerationMeta JSON."""
    lib = _make_mock_library()
    engine = _make_mock_theme_engine()
    selector = _make_mock_selector()
    mapper = _make_mock_mapper()

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=mapper,
        theme_engine=engine,
        selector=selector,
        library=lib,
        ratio_str="100/0/0",  # Force hypothesis_driven only
    )
    gen.set_dataset("analyst4")
    gen.update_context(
        [{"name": "eps_fy1_3m_rev"}, {"name": "sales_fy1_rev"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )

    candidates = gen.generate(5, "analyst4")
    for c in candidates:
        if "random_exploration" in c.source_tags:
            continue  # fallback might not have structured meta
        # Try to parse template_source as JSON
        try:
            meta_dict = json.loads(c.template_source)
            if c.template_source.startswith("{"):
                assert "gen_mode" in meta_dict or "mode" in meta_dict
        except json.JSONDecodeError:
            pass  # Some modes may use non-JSON template_source


def test_hypothesis_driven_generator_observability_guidance_skips_duplicate_expression():
    """Verify observability guidance avoids duplicate history in advanced generator."""
    engine = _make_mock_theme_engine()
    duplicate = "rank(ts_delta(eps_fy1_3m_rev, 60))"
    alternative = "rank(ts_delta(sales_fy1_rev, 20))"
    engine.mutate_expression.side_effect = [duplicate, alternative]
    selector = _make_mock_selector()
    mapper = _make_mock_mapper()

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=mapper,
        theme_engine=engine,
        selector=selector,
        library=None,
        ratio_str="0/0/100",
    )
    gen.set_dataset("analyst4")
    gen.update_context(
        [{"name": "eps_fy1_3m_rev"}, {"name": "sales_fy1_rev"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )
    gen.set_observability_guidance(
        {
            "health_flags": ["duplicate_expression_history"],
            "duplicate_ratio": 0.5,
            "avoid_expressions": [{"expression": duplicate}],
        }
    )

    candidates = gen.generate(1, "analyst4")

    assert len(candidates) == 1
    assert expression_key(candidates[0].expression) == expression_key(alternative)
    assert "observability_diversified" in candidates[0].source_tags
    assert json.loads(candidates[0].template_source)["observability_diversified"] is True


def test_dynamic_theme_generation_uses_category_only_official_fields(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

    (tmp_path / "official_fields.json").write_text(
        json.dumps([{"name": f"analyst_field_{index}", "category": "analyst"} for index in range(8)]),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps(
            [
                {
                    "id": "analyst4",
                    "name": "Analyst",
                    "field_count": 8,
                    "category": {"id": "analyst"},
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(
            [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "zscore", "category": "Cross Sectional"},
                {"name": "winsorize", "category": "Cross Sectional"},
                {"name": "ts_delta", "category": "Time Series"},
                {"name": "ts_mean", "category": "Time Series"},
                {"name": "ts_std_dev", "category": "Time Series"},
                {"name": "ts_sum", "category": "Time Series"},
                {"name": "group_rank", "category": "Group"},
                {"name": "group_neutralize", "category": "Group"},
                {"name": "divide", "category": "Arithmetic"},
                {"name": "if_else", "category": "Logical"},
                {"name": "greater", "category": "Logical"},
            ]
        ),
        encoding="utf-8",
    )
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    engine = DynamicThemeEngine(loader)
    engine.build_categories()

    themes = engine.generate("analyst4", n=5, seed=1)

    assert len(themes) == 5
    assert all(theme.field_slots for theme in themes)
    assert all(slot.startswith("analyst_field_") for theme in themes for slot in theme.field_slots)


def test_dynamic_theme_generation_seeds_high_structure_templates(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.models import Candidate
    from brain_alpha_ops.research.expression_ast import ordered_operators
    from brain_alpha_ops.research.scoring import prior_score
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

    field_names = ["alpha_value", "beta_growth", "quality_margin", "volatility_signal"]
    (tmp_path / "official_fields.json").write_text(
        json.dumps([{"name": name, "category": "analyst"} for name in field_names]),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps([{"id": "analyst4", "name": "Analyst", "field_count": 4, "category": {"id": "analyst"}}]),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(
            [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "zscore", "category": "Cross Sectional"},
                {"name": "winsorize", "category": "Cross Sectional"},
                {"name": "ts_delta", "category": "Time Series"},
                {"name": "ts_mean", "category": "Time Series"},
                {"name": "ts_std_dev", "category": "Time Series"},
                {"name": "group_rank", "category": "Group"},
            ]
        ),
        encoding="utf-8",
    )
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    engine = DynamicThemeEngine(loader)
    engine.build_categories()

    themes = engine.generate("analyst4", n=4, seed=1)
    high_structure = []
    for theme in themes:
        parse_expression(theme.expression)
        candidate = Candidate(
            alpha_id="structure_probe",
            expression=theme.expression,
            family=theme.category,
            hypothesis="Generated expression quality probe",
            data_fields=theme.field_slots,
            operators=ordered_operators(theme.expression),
        )
        score = prior_score(candidate)["score"]
        if len(set(theme.field_slots)) >= 4 and score >= 85:
            high_structure.append((theme, score))

    assert high_structure
    assert any(theme.category == "hybrid" for theme, _score in high_structure)


def test_dynamic_theme_generation_excludes_metadata_fields(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

    (tmp_path / "official_fields.json").write_text(
        json.dumps(
            [
                {"name": "actuals_reporting_currency", "category": "analyst", "coverage": 1.0},
                {"name": "anl4_eps_flag", "category": "analyst", "coverage": 1.0},
                {"name": "anl4_vector_blob", "category": "analyst", "type": "VECTOR", "coverage": 1.0},
                {"name": "sector", "category": "analyst", "coverage": 1.0},
                {"name": "subindustry", "category": "analyst", "coverage": 1.0},
                {"name": "industry_relative_value_signal", "category": "analyst", "coverage": 0.9},
                {"name": "actual_eps_value_quarterly", "category": "analyst", "coverage": 0.9},
                {"name": "sales_estimate_stddev_quarterly", "category": "analyst", "coverage": 0.8},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps([{"id": "analyst4", "name": "Analyst", "field_count": 5, "category": {"id": "analyst"}}]),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(
            [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "zscore", "category": "Cross Sectional"},
                {"name": "winsorize", "category": "Cross Sectional"},
                {"name": "ts_delta", "category": "Time Series"},
                {"name": "ts_mean", "category": "Time Series"},
                {"name": "ts_std_dev", "category": "Time Series"},
                {"name": "group_rank", "category": "Group"},
            ]
        ),
        encoding="utf-8",
    )
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    engine = DynamicThemeEngine(loader)
    engine.build_categories()

    themes = engine.generate("analyst4", n=20, seed=2)
    slots = [slot for theme in themes for slot in theme.field_slots]

    assert themes
    assert set(slots) <= {
        "actual_eps_value_quarterly",
        "industry_relative_value_signal",
        "sales_estimate_stddev_quarterly",
    }
    assert "actuals_reporting_currency" not in slots
    assert "anl4_eps_flag" not in slots
    assert "anl4_vector_blob" not in slots
    assert "sector" not in slots
    assert "subindustry" not in slots


def test_theme_engine_mutation_preserves_digits_inside_field_names(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

    (tmp_path / "official_fields.json").write_text(
        json.dumps([{"name": "analyst_field_15", "category": "analyst"}]),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps([{"id": "analyst4", "name": "Analyst", "field_count": 1, "category": {"id": "analyst"}}]),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(
            [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "ts_delta", "category": "Time Series"},
            ]
        ),
        encoding="utf-8",
    )
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    engine = DynamicThemeEngine(loader)
    engine.build_categories()

    mutated = engine.mutate_expression("rank(ts_delta(analyst_field_15, 20))", "analyst4", seed=2)

    assert "analyst_field_15" in mutated
    assert "analyst_field_150" not in mutated
    assert "analyst_field_152" not in mutated


def test_theme_engine_mutation_preserves_keyword_argument_numbers(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

    (tmp_path / "official_fields.json").write_text(
        json.dumps([{"name": "analyst_signal", "category": "analyst"}]),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps([{"id": "analyst4", "name": "Analyst", "field_count": 1, "category": {"id": "analyst"}}]),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(
            [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "winsorize", "category": "Cross Sectional"},
                {"name": "ts_delta", "category": "Time Series"},
            ]
        ),
        encoding="utf-8",
    )
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    engine = DynamicThemeEngine(loader)
    engine.build_categories()

    expression = "rank(winsorize(ts_delta(analyst_signal, 20), std=4))"

    for seed in range(8):
        mutated = engine.mutate_expression(expression, "analyst4", seed=seed)
        assert "std=4" in mutated.replace(" ", "")


def test_theme_engine_fills_numbered_window_placeholders(tmp_path):
    from brain_alpha_ops.data import OfficialDataLoader
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

    (tmp_path / "official_fields.json").write_text(
        json.dumps([{"name": "actual_eps_value_quarterly", "category": "analyst"}]),
        encoding="utf-8",
    )
    (tmp_path / "official_datasets.json").write_text(
        json.dumps([{"id": "analyst4", "name": "Analyst", "field_count": 1, "category": {"id": "analyst"}}]),
        encoding="utf-8",
    )
    (tmp_path / "official_operators.json").write_text(
        json.dumps(
            [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "ts_delta", "category": "Time Series"},
                {"name": "ts_mean", "category": "Time Series"},
                {"name": "ts_std_dev", "category": "Time Series"},
            ]
        ),
        encoding="utf-8",
    )
    loader = OfficialDataLoader()
    loader.load_all(tmp_path)
    engine = DynamicThemeEngine(loader)
    engine.build_categories()
    engine.windows = [20]

    filled = engine._fill_placeholders(
        "rank(ts_mean(ts_delta({FIELD}, {WINDOW}), {WINDOW2}) / ts_std_dev(ts_delta({FIELD}, {WINDOW}), {WINDOW3}))",
        ["analyst"],
        {"analyst": ["actual_eps_value_quarterly"]},
    )

    assert "{" not in filled
    assert "}" not in filled
    assert "{WINDOW3}" not in filled
    parse_expression(filled)


def test_hypothesis_expression_replaces_returns_when_absent_from_active_dataset():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [
            {"name": "anl4_eps_previous_estimate_value"},
            {"name": "sales_estimate_stddev_quarterly"},
        ],
        [{"name": "rank"}, {"name": "ts_corr"}],
    )
    family = ExpressionFamily(
        id="dataset_safe_corr",
        structure="rank(ts_corr({field}, returns, {window}))",
        windows=[20],
    )

    expression = gen._build_expression(
        family,
        ["anl4_eps_previous_estimate_value", "sales_estimate_stddev_quarterly"],
        20,
    )

    assert "returns" not in expression
    assert "anl4_eps_previous_estimate_value" in expression
    assert "sales_estimate_stddev_quarterly" in expression
    assert gen._extract_fields(expression) == [
        "anl4_eps_previous_estimate_value",
        "sales_estimate_stddev_quarterly",
    ]


def test_random_exploration_sanitizes_theme_returns_and_keeps_std_keyword():
    from brain_alpha_ops.research.theme_engine import ThemeTemplate

    engine = MagicMock()
    engine.generate.return_value = [
        ThemeTemplate(
            id="theme_returns",
            name="Theme Returns",
            category="hybrid",
            expression="{FIELD}",
            field_slots=["anl4_eps_previous_estimate_value"],
        )
    ]
    engine.mutate_expression.return_value = (
        "winsorize(rank(ts_corr(anl4_eps_previous_estimate_value, returns, 20)), std=5)"
    )
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=engine,
        selector=None,
        library=None,
        ratio_str="0/0/100",
    )
    gen.update_context(
        [
            {"name": "anl4_eps_previous_estimate_value"},
            {"name": "sales_estimate_stddev_quarterly"},
        ],
        [{"name": "rank"}, {"name": "ts_corr"}, {"name": "winsorize"}],
    )

    candidate = gen.generate(1, "analyst4")[0]

    assert "returns" not in candidate.expression
    assert "std=5" in candidate.expression
    assert candidate.data_fields == [
        "anl4_eps_previous_estimate_value",
        "sales_estimate_stddev_quarterly",
    ]


def test_hypothesis_expression_normalizes_semantic_call_templates():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [{"name": "actual_cashflow_per_share_value_quarterly"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )
    family = ExpressionFamily(
        id="semantic_call",
        structure="cashflow_per_share_estimate_count(12)",
        windows=[12],
    )

    expression = gen._build_expression(
        family,
        ["actual_cashflow_per_share_value_quarterly"],
        12,
    )

    assert expression == "rank(ts_delta(actual_cashflow_per_share_value_quarterly, 12))"
    assert "actual_cashflow_per_share_value_quarterly(" not in expression


def test_hypothesis_expression_normalizes_field_call_with_group_argument():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [
            {"name": "actual_cashflow_per_share_value_quarterly"},
            {"name": "anl4_eps_mean"},
        ],
        [{"name": "winsorize"}, {"name": "group_rank"}, {"name": "rank"}, {"name": "ts_delta"}],
    )

    expression = gen._normalize_wq_expression_shape(
        "winsorize(actual_cashflow_per_share_value_quarterly(anl4_eps_mean, subindustry), std=3)",
        12,
    )

    assert expression == "winsorize(group_rank(actual_cashflow_per_share_value_quarterly,subindustry),std=3)"
    assert "actual_cashflow_per_share_value_quarterly(" not in expression


def test_hypothesis_expression_normalizes_nested_field_call_expression():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [
            {"name": "actual_cashflow_per_share_value_quarterly"},
            {"name": "anl4_ebit_mean"},
        ],
        [
            {"name": "if_else"},
            {"name": "rank"},
            {"name": "ts_delta"},
            {"name": "ts_mean"},
        ],
    )

    expression = gen._normalize_wq_expression_shape(
        "if_else(actual_cashflow_per_share_value_quarterly(anl4_ebit_mean, ts_mean(anl4_ebit_mean, 8)), -1, 1)",
        12,
    )

    assert expression == "if_else(rank(ts_delta(actual_cashflow_per_share_value_quarterly,8)),-1,1)"
    assert "actual_cashflow_per_share_value_quarterly(" not in expression


def test_generated_expression_cleanup_normalizes_random_field_calls():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [
            {"name": "actual_cashflow_per_share_value_quarterly"},
            {"name": "anl4_eps_mean"},
        ],
        [{"name": "winsorize"}, {"name": "group_rank"}, {"name": "rank"}, {"name": "ts_delta"}],
    )

    expression = gen._normalize_generated_expression(
        "winsorize(actual_cashflow_per_share_value_quarterly(anl4_eps_mean, industry), std=3)"
    )

    assert expression == "winsorize(group_rank(actual_cashflow_per_share_value_quarterly,industry),std=3)"
    assert "actual_cashflow_per_share_value_quarterly(" not in expression


def test_hypothesis_expression_wraps_bare_arithmetic_with_rank():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [{"name": "sales_estimate_dispersion"}],
        [{"name": "rank"}],
    )
    family = ExpressionFamily(
        id="bare_dispersion",
        structure="-1 * estimate_dispersion",
        windows=[12],
    )

    expression = gen._build_expression(
        family,
        ["sales_estimate_dispersion"],
        12,
    )

    assert expression == "rank(-1 * sales_estimate_dispersion)"


def test_generator_fallback_when_no_library():
    """Verify generator falls back to ThemeEngine when no library is available."""
    engine = _make_mock_theme_engine()
    selector = _make_mock_selector()
    mapper = _make_mock_mapper()

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=mapper,
        theme_engine=engine,
        selector=selector,
        library=None,  # No library!
        ratio_str="70/20/10",
    )
    gen.set_dataset("analyst4")

    candidates = gen.generate(3, "analyst4")
    assert len(candidates) >= 1
    for c in candidates:
        # Without library, hypothesis_driven mode degrades to random_exploration;
        # experience_feedback and random_exploration work normally via ThemeEngine.
        assert "hypothesis_driven" not in c.source_tags, \
            f"Expected no hypothesis_driven tag without library, got: {c.source_tags}"


def test_bare_fallback_rotates_fields_and_templates_without_duplicates():
    """Last-resort fallback should not repeatedly emit one canonical expression."""
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
        ratio_str="0/0/100",
    )
    gen.update_context(
        [{"name": "returns"}, {"name": "close"}, {"name": "volume"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )

    candidates = gen.generate(5, "pv1")
    expressions = [candidate.expression for candidate in candidates]
    keys = [expression_key(expression) for expression in expressions]

    assert len(candidates) > 1
    assert len(keys) == len(set(keys))
    assert len(set(expressions)) == len(expressions)
    assert "rank(ts_delta(close, 3))" in expressions
    assert "rank(ts_delta(close, 10))" not in expressions


def test_bare_fallback_deduplicates_single_field_batch():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
        ratio_str="0/0/100",
    )
    gen.update_context(
        [{"name": "returns"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )

    candidates = gen.generate(5, "pv1")

    assert [candidate.expression for candidate in candidates] == [
        "rank(-returns)",
    ]
    assert not any("ts_delta(returns" in candidate.expression for candidate in candidates)


def test_generation_risk_blocks_direct_returns_delta_without_blocking_other_returns_usage():
    assert is_high_turnover_generation_risk("rank(ts_delta(returns, 10))")
    assert high_turnover_generation_risk_reasons("rank(ts_delta(returns, 10))") == [
        "direct_returns_delta_window=10",
    ]
    assert is_high_turnover_generation_risk("zscore(ts_delta( returns , 20 ))")
    assert is_high_turnover_generation_risk("rank(ts_delta(returns, 60))")
    assert not is_high_turnover_generation_risk("rank(ts_corr(close, returns, 20))")
    assert not is_high_turnover_generation_risk("rank(ts_delta(close, 10))")


def test_hypothesis_generator_skips_generation_risk_candidates(monkeypatch):
    from brain_alpha_ops.models import Candidate

    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
        ratio_str="0/0/100",
    )
    gen.update_context(
        [{"name": "close"}, {"name": "returns"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )
    emitted = iter([
        Candidate(
            alpha_id="alpha_risky",
            expression="rank(ts_delta(returns, 10))",
            family="momentum",
            hypothesis="Risky direct returns delta should not enter generated pool.",
            data_fields=["returns"],
            operators=["rank", "ts_delta"],
        ),
        Candidate(
            alpha_id="alpha_safe",
            expression="rank(close)",
            family="quality",
            hypothesis="Safe fallback candidate after risky structure is skipped.",
            data_fields=["close"],
            operators=["rank"],
        ),
    ])

    monkeypatch.setattr(gen, "_generate_random_exploration", lambda _dataset_id: next(emitted, None))

    candidates = gen.generate(1, "pv1")

    assert [candidate.alpha_id for candidate in candidates] == ["alpha_safe"]
    assert not any(is_high_turnover_generation_risk(candidate.expression) for candidate in candidates)


def test_generator_knowledge_constraints_block_fallback_fingerprint_and_similarity():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
        ratio_str="0/0/100",
    )
    gen.update_context(
        [{"name": "close"}, {"name": "returns"}, {"name": "volume"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )
    gen.set_knowledge_constraints(
        {
            "forbidden_patterns": [
                "rank( ts_delta ( close , 3 ) )",
                "rank(ts_delta(returns, 5))",
                "rank(ts_delta(volume, 3))",
            ],
        }
    )

    assert gen._expression_forbidden("rank(ts_delta(close, 3))")
    assert gen._expression_forbidden("rank(ts_delta(returns, 3))")

    candidates = gen.generate(3, "pv1")
    expressions = [candidate.expression for candidate in candidates]

    assert expressions == ["rank(-close)", "rank(-returns)", "rank(-volume)"]
    assert all("ts_delta" not in expression for expression in expressions)


def test_generator_update_context_preserves_fields():
    """Verify update_context populates internal field set."""
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [{"name": "eps_fy1_3m_rev"}, {"name": "sales_fy1_rev"}],
        [{"name": "rank"}, {"name": "ts_delta"}],
    )
    assert len(gen._fields) == 2
    assert "eps_fy1_3m_rev" in gen._fields


def test_generator_private_extractors_use_ast_profile():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.update_context(
        [{"name": "eps_fy1_3m_rev"}, {"name": "sales_fy1_rev"}],
        [{"name": "rank"}, {"name": "ts_delta"}, {"name": "ts_mean"}],
    )
    expression = "Rank(TS_Delta(eps_fy1_3m_rev, 20)) + rank(ts_mean(sales_fy1_rev, 10))"

    assert gen._extract_fields(expression) == ["eps_fy1_3m_rev", "sales_fy1_rev"]
    assert gen._extract_operators(expression) == ["rank", "ts_delta", "rank", "ts_mean"]


def test_generator_private_extract_fields_falls_back_without_known_field_set():
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )

    assert gen._extract_fields("rank(ts_delta(custom_field, 20))") == ["custom_field"]


def test_generator_private_extract_fields_logs_loader_failure(caplog):
    class Loader:
        def get_fields(self, dataset_id=None):
            raise RuntimeError(f"fields unavailable for {dataset_id}")

    gen = HypothesisDrivenGenerator(
        loader=Loader(),
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    gen.set_dataset("pv1")

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.hypothesis_driven_generator"):
        fields = gen._extract_fields("rank(ts_delta(custom_field, 20))")

    assert fields == ["custom_field"]
    assert "generator field extraction metadata unavailable for dataset_id=pv1" in caplog.text
    assert "fields unavailable for pv1" in caplog.text


def test_generator_set_experience_guidance():
    """Verify set_experience_guidance updates internal state."""
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    patterns = {
        "sample_size": 5,
        "top_operators": ["rank", "ts_delta"],
        "preferred_windows": [20, 60, 120],
        "field_combinations": [
            {"fields": ["eps_fy1_3m_rev", "roe"], "count": 3},
        ],
    }
    gen.set_experience_guidance(patterns)
    assert len(gen._experience_operators) == 2
    assert len(gen._experience_windows) == 3
    assert len(gen._experience_fields) == 2


def test_generator_set_experience_guidance_ignores_low_sample():
    """Verify set_experience_guidance ignores patterns with sample_size < 3."""
    gen = HypothesisDrivenGenerator(
        loader=None,
        mapper=None,
        theme_engine=None,
        selector=None,
        library=None,
    )
    patterns = {"sample_size": 2, "top_operators": ["rank"]}
    gen.set_experience_guidance(patterns)
    assert len(gen._experience_operators) == 0
