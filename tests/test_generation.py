import logging

from brain_alpha_ops.config import ResearchBudget
from brain_alpha_ops.data import OfficialDataLoader
from brain_alpha_ops.data.schemas import OfficialField
from brain_alpha_ops.research.generator import (
    CandidateGenerator,
    extract_fields,
    extract_operators,
    local_quality,
    mutate_expression,
    nesting_depth,
)
from brain_alpha_ops.research.generator import _get_default_windows, _load_operators_windows
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.fallback_generation import build_bare_fallback_spec
from brain_alpha_ops.research.validated_generator import _passes_diversity, _tokenize, prefilter_quality


def test_generator_returns_structured_candidates():
    candidates = CandidateGenerator().generate(5)
    assert len(candidates) == 5
    assert candidates[0].expression
    assert candidates[0].hypothesis
    assert candidates[0].data_fields


def test_generator_windows_are_instance_properties_from_operator_metadata():
    class Loader:
        def get_operators(self):
            return [
                {
                    "name": "ts_mean",
                    "category": "Time Series",
                    "definition": "ts_mean(x, d)",
                    "parameters": [{"name": "d", "default": 17}],
                },
                {
                    "name": "winsorize",
                    "definition": "winsorize(x, std=5)",
                    "parameters": [{"name": "std", "default": 5}],
                },
            ]

    windows, winsor_stds = _load_operators_windows(Loader())
    generator = CandidateGenerator(loader=Loader())

    assert 17 in windows
    assert 5 in winsor_stds
    assert generator.windows == windows
    assert generator.winsor_stds == winsor_stds
    assert generator.windows is not generator.windows


def test_generator_logs_operator_metadata_fallback(caplog):
    class Loader:
        def get_operators(self):
            raise RuntimeError("operator metadata unavailable")

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.generator"):
        windows, winsor_stds = _load_operators_windows(Loader())

    assert windows == _get_default_windows()
    assert winsor_stds
    assert "operator metadata unavailable; using default generation windows" in caplog.text
    assert "operator metadata unavailable" in caplog.text


def test_default_windows_helper_returns_copy():
    windows = _get_default_windows()
    windows.append(999)

    assert 999 not in _get_default_windows()


def test_generator_fallback_filters_templates_to_official_operator_subset():
    class Loader:
        def get_operators(self):
            return [
                {"name": "rank", "category": "Cross Sectional"},
                {
                    "name": "ts_mean",
                    "category": "Time Series",
                    "definition": "ts_mean(x, d)",
                    "parameters": [{"name": "d", "default": 20}],
                },
            ]

        def get_fields(self, dataset_id=None):
            return [
                OfficialField(id="close", coverage=1.0),
                OfficialField(id="volume", coverage=0.9),
            ]

    candidates = CandidateGenerator(loader=Loader()).generate(3)

    assert candidates
    assert all(set(candidate.operators) <= {"rank", "ts_mean"} for candidate in candidates)


def test_local_prefilter_rejects_bad_candidate():
    candidate = CandidateGenerator().generate(1)[0]
    candidate.expression = "rank(1)"
    candidate.data_fields = []
    candidate.operators = ["rank"]
    result = local_quality(candidate, ResearchBudget().min_local_quality_score)
    assert not result["passed"]
    assert "no_known_data_field" in result["reasons"]


def test_ast_backed_field_operator_extraction_preserves_structure():
    expression = "Rank(TS_Delta(Close, 20)) + rank(ts_mean(volume, 10))"

    assert extract_fields(expression, {"close", "volume", "returns"}) == ["close", "volume"]
    assert extract_operators(expression) == ["rank", "ts_delta", "rank", "ts_mean"]
    assert nesting_depth(expression) >= 2


def test_extract_fields_fails_closed_without_official_context(monkeypatch):
    monkeypatch.setattr(
        OfficialDataLoader,
        "instance",
        staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("no official context"))),
    )

    assert extract_fields("rank(custom_f1)") == []


def test_validated_generator_diversity_uses_canonical_similarity():
    existing = [{"expression": "rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))"}]

    assert not _passes_diversity(
        "rank(ts_mean(volume, 10)) + rank(ts_delta(close, 20))",
        existing,
        threshold=0.90,
    )


def test_validated_generator_tokenize_uses_ast_semantic_tokens():
    tokens = set(_tokenize("rank(ts_delta(close, 20))"))

    assert "op:rank" in tokens
    assert "op:ts_delta" in tokens
    assert "field:close" in tokens
    assert "w:medium" in tokens


def test_prefilter_quality_reads_ast_profile():
    rows = prefilter_quality([
        {"expression": " Rank ( TS_Delta ( Close , 20 ) ) ", "theme": "momentum"},
        {"expression": "rank(close)", "theme": "value"},
    ])

    assert [row["theme"] for row in rows] == ["momentum"]


def test_generator_observability_guidance_skips_duplicate_expression():
    baseline = CandidateGenerator().generate(3)
    avoided = baseline[0].expression
    generator = CandidateGenerator()
    generator.set_observability_guidance(
        {
            "health_flags": ["duplicate_expression_history"],
            "duplicate_ratio": 0.5,
            "avoid_expressions": [
                {
                    "expression": avoided,
                    "expression_canonical": expression_key(avoided),
                }
            ],
        }
    )

    candidates = generator.generate(3)

    assert candidates
    assert all(expression_key(candidate.expression) != expression_key(avoided) for candidate in candidates)
    assert any(":observability" in candidate.template_source for candidate in candidates)


def test_candidate_generator_blocks_direct_returns_delta_risk(monkeypatch):
    generator = CandidateGenerator()
    generator.update_context(
        [{"name": "returns"}],
        [{"name": "rank"}, {"name": "ts_delta"}, {"name": "ts_mean"}],
    )
    monkeypatch.setattr(generator, "_build_official_field_pool", lambda dataset_id="": ["returns"])

    assert generator._expression_forbidden("rank(ts_delta(returns, 10))")
    assert not generator._expression_forbidden("rank(ts_corr(close, returns, 20))")

    candidates = generator._generate_fallback(4, "pv1")

    assert candidates
    assert not any("ts_delta(returns" in candidate.expression for candidate in candidates)


def test_candidate_generator_fallback_preserves_dataset_id(monkeypatch):
    generator = CandidateGenerator()
    generator.update_context(
        [{"name": "close"}],
        [{"name": "rank"}, {"name": "ts_mean"}],
    )
    monkeypatch.setattr(generator, "_build_official_field_pool", lambda dataset_id="": ["close"])

    candidates = generator.generate(2, dataset_id="pv1")

    assert candidates
    assert all(candidate.dataset_id == "pv1" for candidate in candidates)


def test_bare_fallback_spec_avoids_direct_returns_delta_when_returns_only():
    spec = build_bare_fallback_spec(
        fields=[],
        operators={"rank", "ts_delta", "ts_rank", "ts_mean"},
        windows=[10],
        cursor=0,
    )

    assert spec.expression != "rank(ts_delta(returns, 10))"
    assert "ts_delta(returns" not in spec.expression


def test_legacy_operator_substitute_never_introduces_non_official_operators():
    legacy = mutate_expression("rank(ts_std(close, 20))", 1, mode="operator_substitute")
    official = mutate_expression("rank(ts_std_dev(close, 20))", 2, mode="operator_substitute")

    assert "ts_var" not in legacy
    assert "truncation" not in legacy
    assert "ts_decay_exp" not in legacy
    assert "ts_var" not in official
    assert "truncation" not in official
    assert "ts_decay_exp" not in official
