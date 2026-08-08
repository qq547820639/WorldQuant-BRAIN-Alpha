"""Tests for multi-dimensional retrospective attribution."""

import pytest

from brain_alpha_ops.scoring._attribution_multi import (
    DimensionSummary,
    build_multi_dimensional_attribution,
)


def _card(alpha_id="A1", total=10.0, items=None, gate=None):
    return {
        "alpha_id": alpha_id,
        "total_score": total,
        "empirical": {"items": items or []},
        "gate": gate or {"submission_ready": True, "failed_reasons": []},
    }


def _candidate(alpha_id, **overrides):
    class C:
        pass
    c = C()
    c.alpha_id = alpha_id
    c.submission = overrides.get("submission", {})
    c.validation = overrides.get("validation", {})
    c.extra_fields = overrides.get("extra_fields", {})
    c.created_at = overrides.get("created_at", "2026-01-15T10:00:00Z")
    return c


def test_build_multi_dimensional_attribution_aggregates_by_gate():
    cards = [
        _card("A1", items=[
            {"name": "sharpe", "points": 1.0, "passed": True},
            {"name": "hard_cap", "points": 0.0, "passed": False, "is_hard_gate": True},
        ]),
        _card("A2", items=[
            {"name": "sharpe", "points": 0.5, "passed": True},
        ]),
    ]
    result = build_multi_dimensional_attribution(cards)
    assert result["schema_version"] == "multi_dim_attribution.v1"
    assert result["total_scorecards"] == 2
    by_gate = {d["value"]: d for d in result["dimensions"]["by_gate"]}
    assert by_gate["sharpe"]["count"] == 2
    assert by_gate["sharpe"]["pass_count"] == 2
    assert by_gate["hard_cap"]["fail_count"] == 1
    assert "hard_cap" in by_gate["hard_cap"]["top_failures"]


def test_build_multi_dimensional_attribution_by_metric():
    cards = [
        _card(items=[{"name": "fitness", "actual": 1.2, "passed": True}]),
        _card(items=[{"name": "fitness", "actual": None, "passed": False}]),
        _card(items=[{"name": "fitness", "actual": "bad", "passed": False}]),
    ]
    result = build_multi_dimensional_attribution(cards)
    by_metric = {d["value"]: d for d in result["dimensions"]["by_metric"]}
    assert by_metric["fitness"]["count"] == 2  # None-typed actual is skipped
    assert by_metric["fitness"]["pass_count"] == 1
    assert by_metric["fitness"]["fail_count"] == 1


def test_build_multi_dimensional_attribution_by_context_with_candidates():
    cards = [
        _card("A1", total=20.0, gate={"submission_ready": True, "failed_reasons": []}),
        _card("A2", total=5.0, gate={"submission_ready": False, "failed_reasons": ["sharpe_low"]}),
    ]
    candidates = [
        _candidate("A1", submission={"settings": {"dataset": "cn"}}),
        _candidate("A2", submission={"settings": {"dataset": "cn"}}),
    ]
    result = build_multi_dimensional_attribution(cards, candidates=candidates)
    by_dataset = {d["value"]: d for d in result["dimensions"]["by_dataset"]}
    assert by_dataset["cn"]["count"] == 2
    assert by_dataset["cn"]["pass_count"] == 1
    assert by_dataset["cn"]["fail_count"] == 1
    assert "sharpe_low" in by_dataset["cn"]["top_failures"]


def test_build_multi_dimensional_attribution_by_region_and_time():
    cards = [
        _card("A1", total=10.0, gate={"submission_ready": True, "failed_reasons": []}),
    ]
    candidates = [
        _candidate(
            "A1",
            validation={"settings": {"region": "apac"}},
            created_at="2026-02-05T00:00:00Z",
        ),
    ]
    result = build_multi_dimensional_attribution(cards, candidates=candidates)
    by_region = {d["value"]: d for d in result["dimensions"]["by_region"]}
    assert by_region["apac"]["count"] == 1
    by_time = {d["value"]: d for d in result["dimensions"]["by_time"]}
    assert by_time["2026-02"]["count"] == 1


def test_build_multi_dimensional_attribution_skips_unknown_ids():
    cards = [_card("A1", total=10.0)]
    result = build_multi_dimensional_attribution(cards, candidates=[])
    assert result["dimensions"]["by_dataset"] == []
    assert result["dimensions"]["by_time"] == []
    assert result["dimensions"]["by_region"] == []


def test_dimension_summary_to_dict_rounds_avg():
    s = DimensionSummary(dimension="by_gate", value="sharpe", count=1, avg_score=1.234)
    d = s.to_dict()
    assert d["avg_score"] == 1.23
    assert d["dimension"] == "by_gate"