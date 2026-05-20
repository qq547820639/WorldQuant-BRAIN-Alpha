from brain_alpha_ops.config import ResearchBudget
from brain_alpha_ops.research.generator import CandidateGenerator, extract_fields, extract_operators, local_quality, nesting_depth
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.validated_generator import _passes_diversity, _tokenize, prefilter_quality


def test_generator_returns_structured_candidates():
    candidates = CandidateGenerator().generate(5)
    assert len(candidates) == 5
    assert candidates[0].expression
    assert candidates[0].hypothesis
    assert candidates[0].data_fields


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
