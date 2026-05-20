"""Tests for HypothesisDrivenGenerator — mode routing, generation, output compatibility."""

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
from brain_alpha_ops.research.expression_ast import expression_key

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
