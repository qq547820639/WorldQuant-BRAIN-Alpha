import pytest

from brain_alpha_ops.research.expression_ast import (
    ExpressionParseError,
    canonical_expression,
    expression_fingerprint,
    expression_key,
    expression_profile_summary,
    expression_similarity,
    parse_expression,
    profile_expression,
)


def test_canonical_expression_removes_spacing_and_case_noise():
    assert canonical_expression(" Rank ( TS_Delta ( Close , 20 ) ) ") == "rank(ts_delta(close,20))"


def test_commutative_binary_ops_are_canonicalized():
    left = expression_key("rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))")
    right = expression_key("rank(ts_mean(volume, 10)) + rank(ts_delta(close, 20))")
    assert left == right
    assert expression_fingerprint(left) == expression_fingerprint(right)
    assert expression_similarity(left, right) == pytest.approx(1.0)


def test_function_argument_order_is_preserved():
    left = expression_key("ts_corr(close, volume, 20)")
    right = expression_key("ts_corr(volume, close, 20)")
    assert left != right
    assert expression_similarity(left, right) < 1.0


def test_profile_extracts_structural_features():
    profile = profile_expression("-rank(ts_delta(close, 20) / ts_std_dev(volume, 60))")
    assert profile.parsed is True
    assert profile.operators == ("rank", "ts_delta", "ts_std_dev")
    assert profile.fields == ("close", "volume")
    assert profile.windows == (20, 60)
    assert profile.max_depth >= 4
    assert profile.fingerprint


def test_expression_profile_summary_is_jsonl_ready():
    summary = expression_profile_summary(" Rank ( TS_Delta ( Close , 20 ) ) ")
    assert summary["expression_canonical"] == "rank(ts_delta(close,20))"
    assert summary["expression_fingerprint"]
    assert summary["expression_profile"]["schema_version"] == "expression-profile.v1"
    assert summary["expression_profile"]["parsed"] is True
    assert summary["expression_profile"]["operators"] == ["rank", "ts_delta"]
    assert summary["expression_profile"]["fields"] == ["close"]
    assert summary["expression_profile"]["windows"] == [20]


def test_invalid_expression_falls_back_to_lexical_profile():
    profile = profile_expression("rank(ts_delta(close, 20)")
    assert profile.parsed is False
    assert profile.canonical == "rank ( ts_delta ( close , 20 )"
    assert profile.parse_error
    with pytest.raises(ExpressionParseError):
        parse_expression("rank(ts_delta(close, 20)")
