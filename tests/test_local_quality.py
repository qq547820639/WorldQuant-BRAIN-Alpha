"""Tests for local_quality scoring module."""

import pytest
from brain_alpha_ops.scoring.local_quality import (
    LocalQualityConfig,
    extract_fields,
    local_quality,
    nesting_depth,
)
from brain_alpha_ops.models import Candidate, new_id


def test_config_defaults():
    cfg = LocalQualityConfig()
    assert cfg.base_score == 55.0
    assert cfg.penalty_no_fields == 30.0


def test_local_quality_passes_simple_expression():
    candidate = Candidate(
        alpha_id=new_id("test"),
        family="momentum",
        expression="rank(ts_mean(returns, 20))",
        hypothesis="momentum based on 20 day average returns",
    )
    result = local_quality(candidate, min_quality_level=4.0)
    assert result["passed"] is True
    assert result["score"] >= 40.0
    assert "passed_local_prefilter" in result["reasons"]


def test_local_quality_fails_no_fields():
    candidate = Candidate(
        alpha_id=new_id("test"),
        family="momentum",
        expression="rank(1)",
        hypothesis="test",
    )
    result = local_quality(candidate, min_quality_level=4.0)
    assert "no_known_data_field" in result["reasons"]


def test_extract_fields_with_returns():
    fields = extract_fields("rank(ts_mean(returns,20))")
    assert "returns" in fields


def test_nesting_depth():
    # rank(ts_mean(returns, 20)) → depth 2: rank contains ts_mean
    assert nesting_depth("rank(ts_mean(returns, 20))") == 2
