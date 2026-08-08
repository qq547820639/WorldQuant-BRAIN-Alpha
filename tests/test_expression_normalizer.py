"""Tests for expression normalization, dedup, and AST similarity scoring."""

import pytest

from brain_alpha_ops.expression_normalizer import (
    are_duplicates,
    ast_edit_distance,
    dedup_check,
    find_similar_groups,
    normalize_expression,
    similarity_score,
)


def test_normalize_expression_produces_canonical_form():
    norm = normalize_expression(" Rank ( TS_Delta ( Close , 20 ) ) ")
    assert norm.original == " Rank ( TS_Delta ( Close , 20 ) ) "
    assert norm.canonical == "rank(ts_delta(close,20))"
    assert isinstance(norm.fingerprint, str) and norm.fingerprint
    assert "rank" in norm.operators
    assert "close" in norm.fields
    assert norm.parse_error == ""


def test_normalize_expression_sets_parse_error_on_unparseable_input():
    norm = normalize_expression("rank(close @@")
    assert norm.parse_error != ""
    assert norm.canonical  # falls back to lexical normalization


def test_equivalent_expressions_have_same_fingerprint():
    a = normalize_expression("rank(ts_delta(close, 20)) + rank(ts_mean(volume, 10))")
    b = normalize_expression("rank(ts_mean(volume,10)) + rank(ts_delta(close,20))")
    assert a.fingerprint == b.fingerprint


def test_dedup_check_detects_duplicate_groups():
    expressions = [
        "rank(ts_delta(close, 20))",
        "rank(ts_mean(volume, 10))",
        "rank(ts_delta(close, 20))",
    ]
    duplicates = dedup_check(expressions)
    assert len(duplicates) == 1
    index, canonical, dup_indices = duplicates[0]
    assert index == 0
    assert dup_indices == [2]
    assert canonical == "rank(ts_delta(close,20))"


def test_dedup_check_returns_empty_for_unique():
    assert dedup_check(["rank(close)", "rank(volume)", "abs(close)"]) == []


def test_ast_edit_distance_identical_is_one():
    assert ast_edit_distance("rank(close)", "rank(close)") == pytest.approx(1.0)


def test_ast_edit_distance_different_is_less_than_one():
    assert ast_edit_distance("rank(close)", "abs(volume)") < 1.0


def test_ast_edit_distance_falls_back_to_string_similarity_on_parse_errors():
    val = ast_edit_distance("rank(@@@", "rank(@@@")
    assert 0.0 <= val <= 1.0
    assert val == pytest.approx(1.0)


def test_similarity_score_matches_ast_edit_distance():
    assert similarity_score("rank(close)", "rank(close)") == pytest.approx(1.0)


def test_are_duplicates_respects_threshold():
    assert are_duplicates("rank(close)", "rank(close)") is True
    assert are_duplicates("rank(close)", "abs(volume)", threshold=0.99) is False


def test_find_similar_groups_groups_close_expressions():
    # Whitespace/case variants of the same expression hash to similarity 1.0
    # and must cluster together, while a disjoint expression stays separate.
    expressions = [
        "rank(ts_delta(close, 20))",
        "Rank ( TS_Delta ( Close , 20 ) )",
        "abs(volume)",
        "rank(ts_delta(close,21))",
    ]
    groups = find_similar_groups(expressions, threshold=0.90)
    all_indices = sorted(i for group in groups for i in group)
    assert 0 in all_indices and 1 in all_indices
    assert 2 not in all_indices
    assert 3 not in all_indices


def test_find_similar_groups_returns_empty_for_no_similar():
    assert find_similar_groups(["rank(close)", "abs(volume)", "ts_rank(open, 5)"], threshold=0.99) == []