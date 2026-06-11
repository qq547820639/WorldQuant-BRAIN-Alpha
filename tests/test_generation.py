import logging
from types import SimpleNamespace

from brain_alpha_ops.config import ResearchBudget
from brain_alpha_ops.data import OfficialDataLoader
from brain_alpha_ops.data.schemas import OfficialField
from brain_alpha_ops.models import Candidate
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
from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.generator_metadata import expression_windows_within_constraints
from brain_alpha_ops.research.local_backtest_gate import local_backtest_support
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


def test_expression_window_guard_is_operator_specific():
    assert expression_windows_within_constraints("rank(ts_mean(close, 252))")
    assert expression_windows_within_constraints("rank(ts_rank(close, 252))")
    assert not expression_windows_within_constraints("rank(ts_delta(close, 180))")
    assert not expression_windows_within_constraints("rank(ts_decay_linear(close, 180))")
    assert not expression_windows_within_constraints("rank(ts_corr(close, volume, 8))")


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


def test_candidate_generator_skips_window_constraint_violations():
    class Loader:
        def get_operators(self):
            return [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "divide", "category": "Arithmetic"},
                {"name": "ts_delta", "category": "Time Series"},
                {"name": "ts_std_dev", "category": "Time Series"},
            ]

        def get_fields(self, dataset_id=None):
            return [
                OfficialField(id="close", coverage=1.0),
                OfficialField(id="volume", coverage=0.9),
            ]

    generator = CandidateGenerator(loader=Loader())
    generator._windows = [180, 120]

    candidates = generator.generate(1, dataset_id="pv1")

    assert candidates
    assert expression_windows_within_constraints(candidates[0].expression)
    assert "ts_delta(close, 180)" not in candidates[0].expression


def test_generation_field_pool_excludes_identifier_and_universe_metadata():
    fields = [
        OfficialField(id="open", coverage=1.0),
        OfficialField(id="sedol", coverage=1.0),
        OfficialField(id="cusip", coverage=1.0),
        OfficialField(id="identifier", coverage=1.0),
        OfficialField(id="isin", coverage=1.0),
        OfficialField(id="ticker", coverage=1.0),
        OfficialField(id="top", coverage=1.0),
        OfficialField(id="top200", coverage=1.0),
        OfficialField(id="top3000", coverage=1.0),
        OfficialField(id="topsp", coverage=1.0),
        OfficialField(id="topsp200", coverage=1.0),
        OfficialField(id="pv13_top", coverage=1.0),
        OfficialField(id="pv13_top200", coverage=1.0),
        OfficialField(id="pv13_topsp", coverage=1.0),
        OfficialField(id="pv13_topsp200", coverage=1.0),
        OfficialField(id="pv13_rha_foo", coverage=1.0),
        OfficialField(id="pv13_rha2_foo", coverage=1.0),
        OfficialField(id="pv13_rha2_min20_3000_513", coverage=1.0),
        OfficialField(id="pv13_rha2_min20_3000_513_sector", coverage=1.0),
        OfficialField(id="pv13_hierarchy_level", coverage=1.0),
        OfficialField(id="pv13_revere_parent", coverage=1.0),
        OfficialField(id="pv13_sector", coverage=1.0),
        OfficialField(id="pv13_isin", coverage=1.0),
        OfficialField(id="pv13_cusip", coverage=1.0),
        OfficialField(id="pv13_sedol", coverage=1.0),
        OfficialField(id="industry_relative_value_signal", coverage=0.9),
        OfficialField(id="pv13_alpha_signal", coverage=0.9),
    ]

    assert generation_field_ids(fields) == ["open", "industry_relative_value_signal", "pv13_alpha_signal"]


def test_candidate_generator_official_pool_excludes_identifier_and_universe_metadata():
    class Loader:
        def get_fields(self, dataset_id=None):
            return [
                OfficialField(id="sedol", coverage=1.0),
                OfficialField(id="identifier", coverage=1.0),
                OfficialField(id="top200", coverage=1.0),
                OfficialField(id="topsp200", coverage=1.0),
                OfficialField(id="pv13_top", coverage=1.0),
                OfficialField(id="pv13_top200", coverage=1.0),
                OfficialField(id="pv13_topsp", coverage=1.0),
                OfficialField(id="pv13_rha2_min20_3000_513", coverage=1.0),
                OfficialField(id="pv13_rha2_foo", coverage=1.0),
                OfficialField(id="pv13_isin", coverage=1.0),
                OfficialField(id="pv13_hierarchy_level", coverage=1.0),
                OfficialField(id="pv13_revere_parent", coverage=1.0),
                OfficialField(id="pv13_sector", coverage=1.0),
                OfficialField(id="open", coverage=0.8),
                OfficialField(id="pv13_alpha_signal", coverage=0.7),
            ]

    pool = CandidateGenerator(loader=Loader())._build_official_field_pool("pv1")

    assert pool == ["open", "pv13_alpha_signal"]


def test_candidate_generator_does_not_fallback_when_official_pool_is_only_metadata():
    class Loader:
        def get_fields(self, dataset_id=None):
            return [
                OfficialField(id="sedol", coverage=1.0),
                OfficialField(id="identifier", coverage=1.0),
                OfficialField(id="topsp200", coverage=1.0),
                OfficialField(id="pv13_revere_parent", coverage=1.0),
            ]

    assert CandidateGenerator(loader=Loader())._build_official_field_pool("pv1") == []


def test_candidate_generator_filters_update_context_fields():
    generator = CandidateGenerator()
    generator.update_context(
        [
            {"name": "open"},
            {"name": "sedol"},
            {"name": "identifier"},
            {"name": "top"},
            {"name": "top200"},
            {"name": "topsp"},
            {"name": "pv13_top"},
            {"name": "pv13_revere_parent"},
            {"name": "pv13_sector"},
            {"name": "pv13_rha2_min20_3000_513"},
            {"name": "pv13_rha2_foo"},
            {"name": "pv13_isin"},
            {"name": "pv13_top200"},
        ],
        [{"name": "rank"}],
    )

    assert generator._fields == {"open"}


def test_candidate_generator_filters_context_default_field_fallback(monkeypatch):
    monkeypatch.setattr(
        "brain_alpha_ops.brain_api.context_defaults.get_default_fields",
        lambda: [
            {"name": "top"},
            {"name": "topsp200"},
            {"name": "pv13_hierarchy_level"},
            {"name": "open"},
        ],
    )

    assert CandidateGenerator()._build_official_field_pool("") == ["open"]


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


def test_bare_fallback_spec_skips_window_constraint_violations():
    spec = build_bare_fallback_spec(
        fields=["close"],
        operators={"rank", "ts_delta"},
        windows=[180, 120],
        cursor=0,
    )

    assert spec.expression != "rank(ts_delta(close, 180))"
    assert expression_windows_within_constraints(spec.expression)


def test_legacy_operator_substitute_never_introduces_non_official_operators():
    legacy = mutate_expression("rank(ts_std(close, 20))", 1, mode="operator_substitute")
    official = mutate_expression("rank(ts_std_dev(close, 20))", 2, mode="operator_substitute")

    assert "ts_var" not in legacy
    assert "truncation" not in legacy
    assert "ts_decay_exp" not in legacy
    assert "ts_var" not in official
    assert "truncation" not in official
    assert "ts_decay_exp" not in official


def test_legacy_mutation_reverts_operator_specific_window_violations(monkeypatch):
    monkeypatch.setattr(
        "brain_alpha_ops.research.generator_mutation._load_official_operator_names",
        lambda: {"rank", "ts_delta"},
    )

    mutated = mutate_expression("rank(ts_delta(close, 20))", 3, mode="longer_window")

    assert mutated == "rank(ts_delta(close, 20))"


def test_candidate_generator_filters_preferred_fields_to_official_pool(monkeypatch):
    generator = CandidateGenerator()
    generator.update_context(
        [{"name": "close"}, {"name": "volume"}],
        [{"name": "rank"}],
    )
    monkeypatch.setattr(generator, "_build_official_field_pool", lambda dataset_id="": ["close", "volume"])

    generator.set_knowledge_constraints({
        "preferred_fields": ["close", "custom_non_official"],
        "preferred_operators": ["rank"],
    })

    assert generator._knowledge_constraints["preferred_fields"] == ["close"]
    assert "custom_non_official" not in generator._fields


def test_candidate_generator_includes_official_preferred_fields_outside_initial_pool(monkeypatch):
    generator = CandidateGenerator()
    generator.update_context(
        [{"name": "close"}, {"name": "volume"}],
        [{"name": "rank"}, {"name": "ts_mean"}],
    )
    monkeypatch.setattr(generator, "_build_official_field_pool", lambda dataset_id="": ["volume"])

    generator.set_knowledge_constraints({"preferred_fields": ["close"]})
    candidates = generator._generate_fallback(1, "pv1")

    assert candidates
    assert "close" in candidates[0].data_fields
    assert "close" in candidates[0].expression
    assert expression_windows_within_constraints(candidates[0].expression)


def test_candidate_generator_strict_preferred_fields_limits_fallback_pool(monkeypatch):
    generator = CandidateGenerator()
    generator.update_context(
        [{"name": "close"}, {"name": "volume"}, {"name": "pv13_alpha_signal"}],
        [{"name": "rank"}, {"name": "ts_delta"}, {"name": "ts_std_dev"}, {"name": "divide"}],
    )
    monkeypatch.setattr(
        generator,
        "_build_official_field_pool",
        lambda dataset_id="": ["close", "volume", "pv13_alpha_signal"],
    )

    generator.set_knowledge_constraints({
        "preferred_fields": ["close", "volume"],
        "strict_preferred_fields": True,
    })
    candidates = generator._generate_fallback(6, "pv1")

    assert candidates
    for candidate in candidates:
        assert set(candidate.data_fields) <= {"close", "volume"}
        assert "pv13_alpha_signal" not in candidate.expression


def test_candidate_generator_strict_preferred_operators_limits_fallback_templates(monkeypatch):
    generator = CandidateGenerator()
    generator.update_context(
        [{"name": "close"}, {"name": "volume"}],
        [
            {"name": "rank"},
            {"name": "ts_delta"},
            {"name": "ts_rank"},
            {"name": "ts_mean"},
            {"name": "reverse"},
            {"name": "multiply"},
            {"name": "divide"},
            {"name": "ts_std_dev"},
        ],
    )
    monkeypatch.setattr(generator, "_build_official_field_pool", lambda dataset_id="": ["close", "volume"])

    generator.set_knowledge_constraints({
        "preferred_operators": ["rank", "ts_delta", "ts_rank", "ts_mean"],
        "strict_preferred_operators": True,
    })
    candidates = generator._generate_fallback(6, "pv1")

    assert candidates
    for candidate in candidates:
        assert set(candidate.operators) <= {"rank", "ts_delta", "ts_rank", "ts_mean"}
        assert "reverse(" not in candidate.expression
        assert "multiply(" not in candidate.expression


def test_candidate_generator_strict_preferred_fields_filters_dynamic_mutations():
    class Loader:
        def get_operators(self):
            return [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "ts_mean", "category": "Time Series"},
            ]

    class ThemeEngine:
        def generate(self, dataset_id, n=1, seed=None):
            return [SimpleNamespace(expression="rank(ts_mean(close, 20))", category="demo") for _ in range(n)]

        def mutate_expression(self, expression, dataset_id, seed=0):
            if seed == 0:
                return "rank(ts_mean(pv13_alpha_signal, 20))"
            return "rank(ts_mean(close, 20))"

    generator = CandidateGenerator(loader=Loader(), theme_engine=ThemeEngine())
    generator.update_context(
        [{"name": "close"}, {"name": "pv13_alpha_signal"}],
        [{"name": "rank"}, {"name": "ts_mean"}],
    )
    generator.set_knowledge_constraints({
        "preferred_fields": ["close"],
        "strict_preferred_fields": True,
    })

    candidates = generator.generate(2, dataset_id="pv1")

    assert [candidate.expression for candidate in candidates] == ["rank(ts_mean(close, 20))"]
    assert all(set(candidate.data_fields) <= {"close"} for candidate in candidates)


def test_candidate_generator_strict_preferred_operators_filters_dynamic_mutations():
    class Loader:
        def get_operators(self):
            return [
                {"name": "rank", "category": "Cross Sectional"},
                {"name": "ts_mean", "category": "Time Series"},
                {"name": "winsorize", "category": "Cross Sectional"},
            ]

    class ThemeEngine:
        def generate(self, dataset_id, n=1, seed=None):
            return [SimpleNamespace(expression="rank(ts_mean(close, 20))", category="demo") for _ in range(n)]

        def mutate_expression(self, expression, dataset_id, seed=0):
            if seed == 0:
                return "rank(winsorize(ts_mean(close, 20), std=4))"
            return "rank(ts_mean(close, 20))"

    generator = CandidateGenerator(loader=Loader(), theme_engine=ThemeEngine())
    generator.update_context(
        [{"name": "close"}],
        [{"name": "rank"}, {"name": "ts_mean"}, {"name": "winsorize"}],
    )
    generator.set_knowledge_constraints({
        "preferred_operators": ["rank", "ts_mean"],
        "strict_preferred_operators": True,
    })

    candidates = generator.generate(2, dataset_id="pv1")

    assert [candidate.expression for candidate in candidates] == ["rank(ts_mean(close, 20))"]
    assert all(set(candidate.operators) <= {"rank", "ts_mean"} for candidate in candidates)


def test_local_backtest_support_merges_declared_and_expression_fields():
    class Engine:
        supported_fields = {"close"}
        supported_operators = {"rank"}

    candidate = Candidate(
        alpha_id="alpha_misreported_field",
        expression="rank(sedol)",
        family="test",
        hypothesis="Expression fields must be checked even if the candidate row omits them.",
        data_fields=["close"],
        operators=["rank"],
    )

    support = local_backtest_support(
        candidate,
        Engine(),
        extract_fields=lambda _expression: [],
        extract_operators=lambda _expression: [],
    )

    assert support["supported"] is False
    assert support["fields"] == ["close", "sedol"]
    assert support["unsupported_fields"] == ["sedol"]


def test_local_backtest_support_merges_declared_and_expression_operators():
    class Engine:
        supported_fields = {"close"}
        supported_operators = {"rank"}

    candidate = Candidate(
        alpha_id="alpha_misreported_operator",
        expression="rank(winsorize(close, std=4))",
        family="test",
        hypothesis="Expression operators must be checked even if the candidate row omits them.",
        data_fields=["close"],
        operators=["rank"],
    )

    support = local_backtest_support(
        candidate,
        Engine(),
        extract_fields=lambda _expression: ["close"],
        extract_operators=lambda _expression: [],
    )

    assert support["supported"] is False
    assert support["operators"] == ["rank", "winsorize"]
    assert support["unsupported_operators"] == ["winsorize"]
