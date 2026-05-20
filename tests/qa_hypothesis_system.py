"""QA System Verification Suite — Hypothesis Library + HypothesisDrivenGenerator.

Covers 8 verification dimensions:
  V1: Import chain integrity
  V2: YAML schema compliance (all 8 hypotheses)
  V3: Component unit functionality (6 sub-components)
  V4: Pipeline integration point (pipeline.py wiring)
  V5: GenerationMeta JSON roundtrip
  V6: EMA weight numerical precision
  V7: Edge cases & boundary conditions
  V8: Code quality (no duplicates, no TYPE_CHECKING traps)

Run: python -m pytest tests/qa_hypothesis_system.py -v
Or: python tests/qa_hypothesis_system.py (standalone)
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from unittest.mock import MagicMock, patch

# ── V1: Import Chain Integrity ────────────────────────────────────────

def test_v1_import_chain():
    """V1: All public symbols importable from both direct and __init__ paths."""
    errors = []

    # Direct imports
    try:
        from brain_alpha_ops.research.hypothesis_library import (
            HypothesisLibrary, Hypothesis, ExpressionFamily, FieldCategoryDef,
            AdaptationConfig, FailureMode, Rationale, ExperienceWeights,
            GenerationMeta,
        )
    except ImportError as e:
        errors.append(f"hypothesis_library direct import: {e}")

    try:
        from brain_alpha_ops.research.hypothesis_driven_generator import (
            HypothesisDrivenGenerator, GenerationModeRouter, HypothesisSelector,
            ExpressionFamilySelector, FieldSelector, ContextAdapter,
        )
    except ImportError as e:
        errors.append(f"hypothesis_driven_generator direct import: {e}")

    # __init__ re-exports
    try:
        from brain_alpha_ops.research import (
            HypothesisLibrary as HL, HypothesisDrivenGenerator as HDG,
            GenerationModeRouter as GMR, GenerationMeta as GM,
            HypothesisSelector as HS, ExpressionFamilySelector as EFS,
            FieldSelector as FS, ContextAdapter as CA,
        )
    except ImportError as e:
        errors.append(f"research.__init__ re-export: {e}")

    # Cross-module imports (what pipeline.py actually uses)
    try:
        from brain_alpha_ops.research.dataset_selector import DatasetSelector
        from brain_alpha_ops.research.experience import update_hypothesis_weights
    except ImportError as e:
        errors.append(f"cross-module import: {e}")

    assert not errors, f"Import chain broken:\n  " + "\n  ".join(errors)


# ── V2: YAML Schema Compliance ────────────────────────────────────────

def _get_hypotheses_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "brain_alpha_ops", "research", "hypotheses",
    )


def test_v2_all_eight_hypotheses_load():
    """V2: All 8 YAML files parse into valid Hypothesis objects."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    hyp_dir = _get_hypotheses_dir()
    lib = HypothesisLibrary(hyp_dir).load_all()

    assert lib.count == 8, f"Expected 8 hypotheses, got {lib.count}"

    expected_ids = {
        "earnings_revision_momentum", "quality_profitability", "value_reversal",
        "low_volatility_anomaly", "liquidity_premium", "sentiment_short_interest",
        "analyst_behavior_bias", "microstructure_order_flow",
    }
    actual_ids = set(lib.get_ids())
    missing = expected_ids - actual_ids
    extra = actual_ids - expected_ids
    assert not missing, f"Missing hypotheses: {missing}"
    assert not extra, f"Unexpected hypotheses: {extra}"


def test_v2_schema_required_fields():
    """V2: Each hypothesis has all required fields per _schema.yaml."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    required_fields = ["id", "name", "category", "version", "rationale",
                       "field_categories", "expression_families", "adaptation"]

    for hyp in lib.get_all():
        hyp_dict = hyp.to_dict()
        for field in required_fields:
            assert field in hyp_dict and hyp_dict[field] is not None, \
                f"Hypothesis '{hyp.id}' missing required field: {field}"


def test_v2_field_categories_min_2():
    """V2: Schema requires minItems=2 for field_categories."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    for hyp in lib.get_all():
        assert len(hyp.field_categories) >= 2, \
            f"'{hyp.id}': {len(hyp.field_categories)} field_cats (< 2)"


def test_v2_expression_families_range():
    """V2: Schema requires 2-5 expression_families."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    for hyp in lib.get_all():
        n = len(hyp.expression_families)
        assert 2 <= n <= 5, \
            f"'{hyp.id}': {n} expr_families (must be 2-5)"


def test_v2_category_enum_valid():
    """V2: category must be one of DynamicThemeEngine-compatible values."""
    valid_categories = {
        "momentum", "quality", "reversal", "volatility", "liquidity",
        "value", "growth", "hybrid", "cross_sectional",
    }
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    for hyp in lib.get_all():
        assert hyp.category.lower() in valid_categories or hyp.category in valid_categories, \
            f"'{hyp.id}': invalid category='{hyp.category}'"


def test_v2_version_pattern():
    """V2: version must match semantic versioning pattern."""
    import re
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    pattern = re.compile(r"^\d+\.\d+\.\d+$")
    for hyp in lib.get_all():
        assert pattern.match(hyp.version), \
            f"'{hyp.id}': invalid version='{hyp.version}'"


def test_v2_yaml_files_exist_and_parse():
    """V2: All 9 YAML files (schema + 8 hypotheses) are valid YAML."""
    hyp_dir = _get_hypotheses_dir()
    yaml_files = sorted(p for p in os.listdir(hyp_dir) if p.endswith(".yaml"))
    assert len(yaml_files) >= 9, f"Expected >= 9 YAML files, got {len(yaml_files)}: {yaml_files}"

    for fname in yaml_files:
        fpath = os.path.join(hyp_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        assert data is not None, f"{fname}: parsed as None"
        assert isinstance(data, dict), f"{fname}: not a dict, got {type(data).__name__}"


# ── V3: Component Unit Functionality ──────────────────────────────────

def test_v3_router_distribution_convergence():
    """V3: Router converges to target ratio over 5000 calls."""
    from brain_alpha_ops.research.hypothesis_driven_generator import GenerationModeRouter

    router = GenerationModeRouter("70/20/10")
    for _ in range(5000):
        router.route()
    actual = router.actual_ratios

    # Allow ±5% tolerance at N=5000
    assert 0.65 <= actual["hypothesis_driven"] <= 0.75, \
        f"hypothesis_driven={actual['hypothesis_driven']:.3f}"
    assert 0.15 <= actual["experience_feedback"] <= 0.25, \
        f"experience_feedback={actual['experience_feedback']:.3f}"
    assert 0.05 <= actual["random_exploration"] <= 0.15, \
        f"random_exploration={actual['random_exploration']:.3f}"


def test_v3_router_invalid_ratio_defaults():
    """V3: Invalid ratio string falls back to defaults gracefully."""
    from brain_alpha_ops.research.hypothesis_driven_generator import GenerationModeRouter

    # Should not raise
    r1 = GenerationModeRouter("")
    r2 = GenerationModeRouter("abc/def/ghi")
    r3 = GenerationModeRouter("0/0/0")

    for r in [r1, r2, r3]:
        mode = r.route()
        assert mode in ("hypothesis_driven", "experience_feedback", "random_exploration")


def test_v3_selector_diversity():
    """V3: HypothesisSelector produces diverse selections over many calls."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisSelector

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    selector = HypothesisSelector(lib)

    seen = set()
    for _ in range(20):
        hyp = selector.select()
        assert hyp is not None, "Selector returned None"
        seen.add(hyp.id)
    assert len(seen) >= 3, f"Only {len(seen)} unique hypotheses in 20 picks"


def test_v3_expression_family_window_selection():
    """V3: Window selector returns values from family's defined windows."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.hypothesis_driven_generator import ExpressionFamilySelector

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    sel = ExpressionFamilySelector()

    for hyp_id in lib.get_ids()[:4]:  # Test first 4
        hyp = lib.get_by_id(hyp_id)
        family = sel.select(hyp)
        if family is None:
            continue
        window = sel.select_window(family)
        all_windows = family.get_all_windows()
        assert window in all_windows or not all_windows, \
            f"Window={window} not in family '{family.id}' windows={all_windows}"


def test_v3_field_selector_with_mock():
    """V3: FieldSelector resolves categories via DatasetSelector delegate."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.hypothesis_driven_generator import FieldSelector

    mock_sel = MagicMock()
    mock_sel.get_fields_by_category.return_value = [
        "eps_fy1_3m_rev", "sales_fy1_rev", "roe", "roic",
    ]
    fs = FieldSelector(mock_sel)

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    hyp = lib.get_by_id("earnings_revision_momentum")

    fields = fs.select_fields(hyp, dataset_id="analyst4", count=2)
    assert isinstance(fields, list), f"Expected list, got {type(fields)}"
    assert 1 <= len(fields) <= 2, f"Got {len(fields)} fields (expected 1-2)"
    assert all(isinstance(f, str) for f in fields)


def test_v3_context_adapter_default_fallbacks():
    """V3: ContextAdapter returns valid context even without configuration."""
    from brain_alpha_ops.research.hypothesis_driven_generator import ContextAdapter
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    adapter = ContextAdapter()
    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()

    for hyp_id in lib.get_ids():
        hyp = lib.get_by_id(hyp_id)
        ctx = adapter.adapt(hyp)
        assert "region" in ctx and ctx["region"], f"No region for {hyp_id}"
        assert "universe" in ctx and ctx["universe"], f"No universe for {hyp_id}"
        assert "delay" in ctx and isinstance(ctx["delay"], int), f"No delay for {hyp_id}"


# ── V4: Pipeline Integration Point ───────────────────────────────────

def test_v4_pipeline_import_path_exists():
    """V4: pipeline.py contains hypothesis library initialization block."""
    pipeline_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "brain_alpha_ops", "research", "pipeline.py",
    )
    with open(pipeline_path, "r", encoding="utf-8") as f:
        source = f.read()

    required_patterns = [
        "HypothesisLibrary",
        "HypothesisDrivenGenerator",
        "hypothesis_library_dir",
        "generation_mode_ratio",
        "_hypothesis_library",
        "ratio_str=ratio",
    ]
    for pat in required_patterns:
        assert pat in source, f"Pipeline missing pattern: '{pat}'"


def test_v4_config_has_required_attrs():
    """V4: config.ResearchBudget has required hypothesis config attributes."""
    # Import may fail if full dependency chain isn't available;
    # read source directly instead.
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "brain_alpha_ops", "config.py",
    )
    with open(config_path, "r", encoding="utf-8") as f:
        source = f.read()

    assert "generation_mode_ratio" in source, "config.py missing generation_mode_ratio"
    assert "hypothesis_library_dir" in source, "config.py missing hypothesis_library_dir"

    # No duplicate definitions
    lines = source.split("\n")
    gen_mode_lines = [l for l in lines if "generation_mode_ratio" in l]
    assert len(gen_mode_lines) == 1, \
        f"config.py has {len(gen_mode_lines)} generation_mode_ratio definitions (expected 1)"

    hyp_dir_lines = [l for l in lines if "hypothesis_library_dir" in l]
    assert len(hyp_dir_lines) == 1, \
        f"config.py has {len(hyp_dir_lines)} hypothesis_library_dir definitions (expected 1)"


# ── V5: GenerationMeta JSON Roundtrip ────────────────────────────────

def test_v5_meta_roundtrip_preserves_all_fields():
    """V5: to_json → from_dict preserves every field value."""
    from brain_alpha_ops.research.hypothesis_library import GenerationMeta

    original = GenerationMeta(
        mode="hypothesis_driven",
        hypothesis_id="test_hyp_001",
        hypothesis_name="Test Hypothesis Alpha",
        expression_family_id="revision_diff",
        field_category="earnings_estimate_revision",
        selected_fields=["eps_fy1_3m_rev", "sales_fy1_rev"],
        region="USA",
        universe="TOP3000",
        delay=2,
    )

    json_str = original.to_json()
    restored = GenerationMeta.from_dict(json.loads(json_str))

    assert restored.mode == original.mode
    assert restored.hypothesis_id == original.hypothesis_id
    assert restored.hypothesis_name == original.hypothesis_name
    assert restored.expression_family_id == original.expression_family_id
    assert restored.field_category == original.field_category
    assert restored.selected_fields == original.selected_fields
    assert restored.region == original.region
    assert restored.universe == original.universe
    assert restored.delay == original.delay


def test_v5_meta_json_keys_match_candidate_template_source():
    """V5: JSON output is compatible with Candidate.template_source storage."""
    from brain_alpha_ops.research.hypothesis_library import GenerationMeta

    meta = GenerationMeta(mode="test", hypothesis_id="h1")
    json_str = meta.to_json()

    # Must be valid JSON
    obj = json.loads(json_str)
    assert isinstance(obj, dict)
    assert "mode" in obj  # Key used by downstream consumers
    assert "hypothesis_id" in obj
    assert "timestamp" in obj  # Auto-generated


# ── V6: EMA Weight Numerical Precision ────────────────────────────────

def test_v6_ema_formula_correctness():
    """V6: new_weight = 0.8 * old + 0.2 * update (exact formula)."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()

    # Set a known initial state
    hyp = lib.get_by_id("earnings_revision_momentum")
    for fc in hyp.field_categories:
        fc.weight = 1.0
    for ef in hyp.expression_families:
        ef.weight = 1.0
    hyp.experience_weights.overall = 1.0

    # Apply update with winner_ratio=1.0 → new = 0.8*1.0 + 0.2*1.0 = 1.0
    lib.update_weights("earnings_revision_momentum",
                       field_cat_weights={"earnings_estimate_revision": 1.0},
                       expr_fam_weights={"revision_diff": 1.0})

    hyp = lib.get_by_id("earnings_revision_momentum")
    # With 100% winner ratio, weights should stay at ~1.0 (or very close)
    for fc in hyp.field_categories:
        if fc.category == "earnings_estimate_revision":
            assert abs(fc.weight - 1.0) < 1e-9, \
                f"EMA error: weight={fc.weight}, expected ≈1.0"

    # Apply update with winner_ratio=0.0 → new = 0.8*old + 0.2*0.0 = 0.8*old
    lib.update_weights("earnings_revision_momentum",
                       field_cat_weights={"earnings_estimate_revision": 0.0})
    hyp = lib.get_by_id("earnings_revision_momentum")
    for fc in hyp.field_categories:
        if fc.category == "earnings_estimate_revision":
            assert abs(fc.weight - 0.8) < 1e-9, \
                f"EMA decay error: weight={fc.weight}, expected 0.8"


def test_v6_ema_non_negative_constraint():
    """V6: Weights never go negative after any sequence of updates."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()

    # Apply extreme negative updates repeatedly
    for _ in range(100):
        lib.update_weights("earnings_revision_momentum",
                           field_cat_weights={"earnings_estimate_revision": -999.0})

    hyp = lib.get_by_id("earnings_revision_momentum")
    assert hyp.experience_weights.overall >= 0.0
    for fc in hyp.field_categories:
        assert fc.weight >= 0.0
    for ef in hyp.expression_families:
        assert ef.weight >= 0.0


# ── V7: Edge Cases & Boundary Conditions ──────────────────────────────

def test_v7_empty_library_safe():
    """V7: Generator handles empty/null library without crashing."""
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator

    gen = HypothesisDrivenGenerator(library=None)
    candidates = gen.generate(3, "analyst4")
    # Should produce 0 or fallback candidates, but never crash
    assert isinstance(candidates, list)


def test_v7_zero_count_generate():
    """V7: generate(0) returns empty list without error."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    engine = MagicMock()
    engine.generate.return_value = []
    engine.mutate_expression.return_value = "rank(returns)"

    gen = HypothesisDrivenGenerator(theme_engine=engine, library=lib)
    result = gen.generate(0)
    assert result == []


def test_v7_single_hypothesis_library():
    """V7: System works with minimal single-hypothesis library."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary, Hypothesis, Rationale
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisSelector

    # Create minimal in-memory library
    lib = HypothesisLibrary.__new__(HypothesisLibrary)
    lib._hypotheses = {
        "only_one": Hypothesis(
            id="only_one", name="Only", category="momentum",
            expression_families=[], field_categories=[],
            rationale=Rationale(theory="test"),
        ),
    }
    lib._by_category = {"momentum": [lib._hypotheses["only_one"]]}

    selector = HypothesisSelector(lib)
    hyp = selector.select()
    assert hyp is not None
    assert hyp.id == "only_one"


def test_v7_experience_guidance_low_sample_ignored():
    """V7: set_experience_guidance ignores sample_size < 3."""
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator

    gen = HypothesisDrivenGenerator()
    gen.set_experience_guidance({"sample_size": 0})
    assert len(gen._experience_operators) == 0

    gen.set_experience_guidance({"sample_size": 2, "top_operators": ["rank"]})
    assert len(gen._experience_operators) == 0  # Ignored

    gen.set_experience_guidance({"sample_size": 5, "top_operators": ["rank", "ts_delta"]})
    assert len(gen._experience_operators) == 2  # Accepted


def test_v7_update_weights_nonexistent_id_no_crash():
    """V7: Updating nonexistent hypothesis ID is a no-op."""
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    count_before = lib.count
    lib.update_weights("NONEXISTENT_HYPOTHESIS_12345",
                       field_cat_weights={"x": 1.0})
    assert lib.count == count_before


def test_v7_context_adapter_empty_available():
    """V7: ContextAdapter falls back when available lists are empty."""
    from brain_alpha_ops.research.hypothesis_driven_generator import ContextAdapter
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    adapter = ContextAdapter()
    adapter.set_available_context(regions=[], universes=[], delays=[])

    lib = HypothesisLibrary(_get_hypotheses_dir()).load_all()
    hyp = lib.get_by_id("earnings_revision_momentum")

    # Should still produce output using internal defaults
    ctx = adapter.adapt(hyp)
    assert "region" in ctx


# ── V8: Code Quality Checks ──────────────────────────────────────────

def test_v8_no_type_checking_trap():
    """V8: No runtime NameError from TYPE_CHECKING-guarded imports."""
    # Verify source-level: GenerationMeta imported outside TYPE_CHECKING
    source = inspect_source("hypothesis_driven_generator.py", subdir="research")
    assert "from brain_alpha_ops.research.hypothesis_library import (" in source, \
        "GenerationMeta must be imported outside TYPE_CHECKING"
    assert "GenerationMeta," in source, \
        "GenerationMeta must be in the non-TYPE_CHECKING import"


def test_v8_experience_no_duplicate_functions():
    """V8: experience.py has exactly one update_hypothesis_weights definition."""
    source = inspect_source("experience.py", subdir="research")
    count = source.count("def update_hypothesis_weights(")
    assert count == 1, \
        f"experience.py has {count} update_hypothesis_weights defs (expected 1)"


def test_v8_config_no_duplicate_lines():
    """V8: config.py ResearchBudget has no duplicate attribute definitions."""
    source = inspect_source("config.py")
    for attr in ["generation_mode_ratio", "hypothesis_library_dir"]:
        lines = [l.strip() for l in source.split("\n") if attr in l and l.strip().startswith(attr)]
        assert len(lines) <= 1, \
            f"config.py: {len(lines)} '{attr}' definitions (expected ≤1)"


def test_v8_init_py_exports_all_symbols():
    """V8: research/__init__.py exports all new public symbols."""
    source = inspect_source("__init__.py", subdir="research")

    required_exports = [
        "HypothesisLibrary", "Hypothesis", "ExpressionFamily",
        "FieldCategoryDef", "AdaptationConfig", "FailureMode",
        "Rationale", "ExperienceWeights", "GenerationMeta",
        "HypothesisDrivenGenerator", "GenerationModeRouter",
        "HypothesisSelector", "ExpressionFamilySelector",
        "FieldSelector", "ContextAdapter",
    ]
    for sym in required_exports:
        assert sym in source, f"__init__.py missing export: {sym}"


# ── Helpers ───────────────────────────────────────────────────────────

def inspect_source(filename: str, subdir: str = "") -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parts = ["brain_alpha_ops"]
    if subdir:
        parts.append(subdir)
    parts.append(filename)
    fpath = os.path.join(base, *parts)
    with open(fpath, "r", encoding="utf-8") as f:
        return f.read()


# ── Runner ────────────────────────────────────────────────────────────

ALL_TESTS = [
    # V1: Import chain (1)
    "test_v1_import_chain",

    # V2: YAML schema compliance (7)
    "test_v2_all_eight_hypotheses_load",
    "test_v2_schema_required_fields",
    "test_v2_field_categories_min_2",
    "test_v2_expression_families_range",
    "test_v2_category_enum_valid",
    "test_v2_version_pattern",
    "test_v2_yaml_files_exist_and_parse",

    # V3: Component units (6)
    "test_v3_router_distribution_convergence",
    "test_v3_router_invalid_ratio_defaults",
    "test_v3_selector_diversity",
    "test_v3_expression_family_window_selection",
    "test_v3_field_selector_with_mock",
    "test_v3_context_adapter_default_fallbacks",

    # V4: Pipeline integration (2)
    "test_v4_pipeline_import_path_exists",
    "test_v4_config_has_required_attrs",

    # V5: Meta roundtrip (2)
    "test_v5_meta_roundtrip_preserves_all_fields",
    "test_v5_meta_json_keys_match_candidate_template_source",

    # V6: EMA precision (2)
    "test_v6_ema_formula_correctness",
    "test_v6_ema_non_negative_constraint",

    # V7: Edge cases (6)
    "test_v7_empty_library_safe",
    "test_v7_zero_count_generate",
    "test_v7_single_hypothesis_library",
    "test_v7_experience_guidance_low_sample_ignored",
    "test_v7_update_weights_nonexistent_id_no_crash",
    "test_v7_context_adapter_empty_available",

    # V8: Code quality (4)
    "test_v8_no_type_checking_trap",
    "test_v8_experience_no_duplicate_functions",
    "test_v8_config_no_duplicate_lines",
    "test_v8_init_py_exports_all_symbols",
]


def run_qa():
    """Execute all QA tests and produce structured report."""
    failed_tests = []
    passed_tests = []
    errors_detail = []

    for test_name in ALL_TESTS:
        test_fn = globals()[test_name]
        try:
            test_fn()
            passed_tests.append(test_name)
            print(f"  PASS: {test_name}")
        except Exception as exc:
            failed_tests.append(test_name)
            detail = "".join(traceback.format_exception(exc))[-500:]
            errors_detail.append((test_name, detail))
            print(f"  FAIL: {test_name}: {exc}")

    total = len(ALL_TESTS)
    print(f"\n{'='*60}")
    print(f"QA RESULTS: {len(passed_tests)}/{total} passed, {len(failed_tests)} failed")
    print(f"{'='*60}")

    if failed_tests:
        print("\nFAILED TEST DETAILS:")
        for name, detail in errors_detail:
            print(f"\n--- {name} ---")
            print(detail[:800])

    return len(failed_tests) == 0


if __name__ == "__main__":
    ok = run_qa()
    sys.exit(0 if ok else 1)
