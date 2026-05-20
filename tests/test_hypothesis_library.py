"""Tests for HypothesisLibrary — loading, querying, and weight management."""

import pytest
from pathlib import Path

from brain_alpha_ops.research.hypothesis_library import (
    HypothesisLibrary,
    Hypothesis,
    ExpressionFamily,
    FieldCategoryDef,
    AdaptationConfig,
    FailureMode,
    Rationale,
    ExperienceWeights,
    GenerationMeta,
)


# ── Helpers ─────────────────────────────────────────────────────────

HYPOTHESES_DIR = Path(__file__).resolve().parents[1] / "brain_alpha_ops" / "research" / "hypotheses"


def _require_yaml_dir():
    if not HYPOTHESES_DIR.exists():
        pytest.skip(f"Hypotheses directory not found: {HYPOTHESES_DIR}")


# ── Loading Tests ───────────────────────────────────────────────────

def test_library_loads_all_eight_hypotheses():
    """T02 acceptance: load_all() loads 8 hypotheses."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    assert lib.count == 8, f"Expected 8 hypotheses, got {lib.count}"
    assert len(lib.get_all()) == 8


def test_library_get_ids_returns_all():
    """get_ids() returns all hypothesis IDs."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    ids = lib.get_ids()
    assert len(ids) == 8
    assert "earnings_revision_momentum" in ids
    assert "quality_profitability" in ids
    assert "value_reversal" in ids
    assert "low_volatility_anomaly" in ids
    assert "liquidity_premium" in ids
    assert "sentiment_short_interest" in ids
    assert "analyst_behavior_bias" in ids
    assert "microstructure_order_flow" in ids


def test_library_skips_schema_file():
    """_schema.yaml should not be loaded as a hypothesis."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    assert "_schema" not in lib.get_ids()
    for hyp in lib.get_all():
        assert not hyp.id.startswith("_")


# ── Query Tests ─────────────────────────────────────────────────────

def test_get_by_id_returns_correct_hypothesis():
    """T02 acceptance: get_by_id returns full Hypothesis with all sub-fields."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    hyp = lib.get_by_id("earnings_revision_momentum")
    assert hyp is not None
    assert hyp.name == "Earnings Revision Momentum"
    assert hyp.category == "momentum"
    assert hyp.version == "1.0.0"
    assert len(hyp.field_categories) >= 2
    assert len(hyp.expression_families) >= 2
    assert len(hyp.expected_failure_modes) >= 1
    assert len(hyp.adaptation.preferred_regions) >= 1
    assert hyp.rationale.theory != ""


def test_get_by_id_nonexistent_returns_none():
    """get_by_id for unknown ID returns None."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    assert lib.get_by_id("nonexistent_hypothesis") is None


def test_get_by_category_returns_matching():
    """get_by_category filters by category field."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    momentum = lib.get_by_category("momentum")
    assert len(momentum) >= 1
    assert any(h.id == "earnings_revision_momentum" for h in momentum)

    quality = lib.get_by_category("quality")
    assert len(quality) >= 1
    assert any(h.id == "quality_profitability" for h in quality)


def test_get_by_category_case_insensitive():
    """get_by_category is case-insensitive."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    upper = lib.get_by_category("MOMENTUM")
    lower = lib.get_by_category("momentum")
    assert len(upper) == len(lower)


def test_all_hypotheses_have_required_fields():
    """Every hypothesis has all required fields from the architecture."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    for hyp in lib.get_all():
        assert hyp.id, f"Empty id in hypothesis"
        assert hyp.name, f"Empty name in {hyp.id}"
        assert hyp.category, f"Empty category in {hyp.id}"
        assert len(hyp.field_categories) >= 1, f"No field_categories in {hyp.id}"
        assert len(hyp.expression_families) >= 2, f"Less than 2 expression_families in {hyp.id}"
        assert 2 <= len(hyp.expression_families) <= 5, f"Expression families outside 2-5 range in {hyp.id}"
        assert hyp.rationale.theory, f"Empty rationale theory in {hyp.id}"


# ── Weight Management Tests ─────────────────────────────────────────

def test_update_weights_applies_ema():
    """T02 acceptance: update_weights applies EMA smoothing correctly."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    hyp = lib.get_by_id("earnings_revision_momentum")
    assert hyp is not None

    old_overall = hyp.experience_weights.overall
    old_fc_weight = hyp.field_categories[0].weight

    lib.update_weights(
        "earnings_revision_momentum",
        field_cat_weights={hyp.field_categories[0].category: 0.5},
        expr_fam_weights={hyp.expression_families[0].id: 0.8},
        window_weights={"3": 0.6},
    )

    # EMA: new = 0.8 * old + 0.2 * update
    expected_fc = 0.8 * old_fc_weight + 0.2 * 0.5
    assert abs(hyp.field_categories[0].weight - expected_fc) < 0.001, \
        f"Field category EMA mismatch: {hyp.field_categories[0].weight} vs {expected_fc}"

    # Overall should have changed
    assert hyp.experience_weights.overall != old_overall


def test_update_weights_nonexistent_no_error():
    """update_weights on nonexistent hypothesis logs warning but no error."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    # Should not raise
    lib.update_weights("nonexistent", field_cat_weights={"test": 0.5})


def test_reload_restores_original_state():
    """reload() reloads from disk, discarding runtime weight changes."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    hyp = lib.get_by_id("earnings_revision_momentum")
    assert hyp is not None
    original_weight = hyp.field_categories[0].weight

    lib.update_weights(
        "earnings_revision_momentum",
        field_cat_weights={hyp.field_categories[0].category: 0.1},
    )
    assert hyp.field_categories[0].weight != original_weight

    lib.reload()
    hyp2 = lib.get_by_id("earnings_revision_momentum")
    assert hyp2 is not None
    assert hyp2.field_categories[0].weight == 1.0, \
        "After reload, weights should reset to file defaults (1.0)"


# ── Data Model Tests ────────────────────────────────────────────────

def test_generation_meta_to_json():
    """GenerationMeta.to_json() produces valid JSON with all fields."""
    meta = GenerationMeta(
        mode="hypothesis_driven",
        hypothesis_id="test_hypothesis",
        hypothesis_name="Test",
        expression_family_id="test_family",
        field_category="test_category",
        selected_fields=["f1", "f2"],
        region="USA",
        universe="TOP3000",
        delay=1,
    )
    json_str = meta.to_json()
    assert '"mode"' in json_str
    assert '"hypothesis_id"' in json_str
    assert '"test_hypothesis"' in json_str


def test_expression_family_get_all_windows():
    """get_all_windows() merges regular, short, and long windows."""
    ef = ExpressionFamily(
        id="test",
        structure="test_expr",
        windows=[1, 3, 6],
        windows_short=[1, 2],
        windows_long=[12],
    )
    all_win = ef.get_all_windows()
    assert 1 in all_win
    assert 6 in all_win
    assert 12 in all_win


def test_hypothesis_from_dict_and_to_dict_roundtrip():
    """Hypothesis.to_dict() → from_dict() roundtrip preserves data."""
    _require_yaml_dir()
    lib = HypothesisLibrary(str(HYPOTHESES_DIR)).load_all()
    hyp = lib.get_by_id("quality_profitability")
    assert hyp is not None
    d = hyp.to_dict()
    hyp2 = Hypothesis.from_dict({"hypothesis": d})
    assert hyp2.id == hyp.id
    assert hyp2.name == hyp.name
    assert len(hyp2.field_categories) == len(hyp.field_categories)
    assert len(hyp2.expression_families) == len(hyp.expression_families)
