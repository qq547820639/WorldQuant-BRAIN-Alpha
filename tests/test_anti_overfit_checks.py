"""Tests for the anti-overfit checks (IC stability, regime, placebo, half-life, compliance)."""

from datetime import datetime, timedelta, timezone

from brain_alpha_ops.scoring.anti_overfit import checks as c
from brain_alpha_ops.scoring.anti_overfit.models import ComplianceGuardrailResult


def test_safe_mean_std():
    assert c._safe_mean([]) == 0.0
    assert c._safe_mean([1, 2, 3]) == 2.0
    assert c._safe_std([1]) == 0.0
    assert c._safe_std([1, 2, 3]) == 1.0


def test_pearson_r():
    assert c._pearson_r([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert c._pearson_r([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    # constant series -> 0
    assert c._pearson_r([1, 1, 1], [1, 2, 3]) == 0.0
    # too short -> 0
    assert c._pearson_r([1, 2], [1, 2]) == 0.0


def test_rank_transform_and_spearman():
    assert c._rank_transform([3, 1, 2]) == [3.0, 1.0, 2.0]
    assert c._rank_transform([1, 1, 2]) == [1.5, 1.5, 3.0]
    assert c._spearman_r([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert c._spearman_r([1, 2], [1, 2]) == 0.0


def test_rank_ic():
    assert c._rank_ic([], []) == [0.0]
    # short series -> single IC
    assert len(c._rank_ic([1, 2, 3], [1, 2, 3], window=5)) == 1
    # long series -> multiple windows
    vals = list(range(100))
    ics = c._rank_ic(vals, vals, window=21)
    assert len(ics) >= 4


def test_sharpe():
    assert c._sharpe([1, 2, 3, 4]) == 0.0  # n < 5
    # positive mean with variance -> positive sharpe
    returns = [0.01, 0.02, -0.005, 0.015, 0.01, 0.0, 0.02, 0.01, -0.01, 0.03]
    assert c._sharpe(returns) > 0
    assert c._sharpe([1, 1, 1, 1, 1]) == 0.0  # zero std


def test_auto_classify_regimes():
    assert c._auto_classify_regimes([]) == []
    returns = [1, 2, 3, 4, 5, 6]
    labels = c._auto_classify_regimes(returns)
    assert len(labels) == 6
    assert "bull" in labels and "bear" in labels


def test_candidate_report_and_metrics():
    report = c._candidate_report(ok=True, passed=False, recommendation="x", score=1.0, sample_size=5, data_source="s", reason="r")
    assert report["ok"] is True
    assert report["passed"] is False
    assert c._candidate_metrics({"official_metrics": {"sharpe": 1.0}}) == {"sharpe": 1.0}
    assert c._candidate_metrics({"official_metrics": "x"}) == {}
    assert c._candidate_value({"a": 1}, "a") == 1
    assert c._candidate_value("not-dict", "a") is None


def test_number_series():
    assert c._number_series([1, "2", "abc", float("inf")]) == [1.0, 2.0]
    assert c._number_series((1, 2)) == [1.0, 2.0]
    assert c._number_series("x") == []


def test_attach_submission_report_dict():
    candidate = {}
    c._attach_submission_report(candidate, "key", {"a": 1})
    assert candidate["submission"]["key"] == {"a": 1}
    candidate2 = {"submission": {"existing": True}}
    c._attach_submission_report(candidate2, "key", {"a": 1})
    assert candidate2["submission"]["existing"] is True


def test_compute_ic_stability_insufficient():
    out = c.compute_ic_stability([1, 2], [1, 2])
    assert out["passed"] is False
    assert "insufficient" in out["warning"]


def test_compute_ic_stability_ok():
    vals = list(range(100))
    out = c.compute_ic_stability(vals, vals)
    assert "ic_mean" in out
    assert "monthly_means" in out
    assert isinstance(out["passed"], bool)


def test_compute_regime_stress_insufficient():
    out = c.compute_regime_stress([1, 2], [1, 2])
    assert out["passed"] is False
    assert "insufficient" in out["warning"]


def test_compute_regime_stress_ok():
    vals = list(range(60))
    labels = ["bull", "bear", "sideways"] * 20
    out = c.compute_regime_stress(vals, vals, regime_labels=labels, min_samples_per_regime=5)
    assert "bull_sharpe" in out
    assert isinstance(out["passed"], bool)


def test_compute_regime_stress_auto():
    vals = list(range(60))
    out = c.compute_regime_stress(vals, vals, min_samples_per_regime=5)
    assert "regime_stability_score" in out


def test_compute_placebo_test_insufficient():
    out = c.compute_placebo_test([1, 2], [1, 2])
    assert out["passed"] is False


def test_compute_placebo_test_ok():
    vals = list(range(30))
    out = c.compute_placebo_test(vals, vals, trials=10)
    assert "p_value" in out
    assert "placebo_score" in out


def test_estimate_half_life_insufficient():
    out = c.estimate_half_life([1, 2], [1, 2])
    assert out["passed"] is False


def test_check_expression_similarity():
    a = c.check_expression_similarity("rank(close)", "rank(close)")
    assert a["score"] == 1.0
    assert a["blocked"] is True
    b = c.check_expression_similarity("rank(close)", "ts_rank(open, 5)")
    assert b["score"] < 1.0
    empty = c.check_expression_similarity("", "rank(close)")
    assert empty["score"] == 0.0
    assert empty["blocked"] is False


def test_tokenize_expression():
    assert c._tokenize_expression("Rank(Close) + 5") == {"rank", "close"}


def test_check_parameter_tweak():
    # no change
    assert c.check_parameter_tweak({"decay": 1}, {"decay": 1})["flagged"] is False
    # only decay changed, improvement below threshold
    out = c.check_parameter_tweak({"decay": 101, "delay": 1}, {"decay": 100, "delay": 1}, improvement_threshold=0.05)
    assert out["flagged"] is True  # ~1% improvement < 5%
    # large improvement not flagged
    out2 = c.check_parameter_tweak({"decay": 110, "delay": 1}, {"decay": 100, "delay": 1}, improvement_threshold=0.05)
    assert out2["flagged"] is False
    # non-decay key changed -> not flagged
    out3 = c.check_parameter_tweak({"sharpe": 2.0}, {"sharpe": 1.0}, improvement_threshold=0.05)
    assert out3["flagged"] is False


def test_check_duplicate_submission():
    now = datetime.now(timezone.utc).isoformat()
    history = [{"expression": "rank(close)", "submitted_at": now}]
    out = c.check_duplicate_submission(" rank(CLOSE) ", history)
    assert out["blocked"] is True
    # different expression
    out2 = c.check_duplicate_submission("rank(open)", history)
    assert out2["blocked"] is False
    # missing submitted_at skipped
    out3 = c.check_duplicate_submission("rank(close)", [{"expression": "rank(close)"}])
    assert out3["blocked"] is False
    # old submission not blocked
    old = datetime.now(timezone.utc) - timedelta(days=100)
    out4 = c.check_duplicate_submission("rank(close)", [{"expression": "rank(close)", "submitted_at": old.isoformat()}])
    assert out4["blocked"] is False
    # invalid timestamp skipped
    out5 = c.check_duplicate_submission("rank(close)", [{"expression": "rank(close)", "submitted_at": "not-a-date"}])
    assert out5["blocked"] is False


def test_check_high_frequency_retry():
    history = [{"expression": "rank(close)"}] * 5
    out = c.check_high_frequency_retry("rank(close)", history, threshold=3)
    assert out["blocked"] is True
    assert out["failure_count"] == 5
    out2 = c.check_high_frequency_retry("rank(close)", history, threshold=10)
    assert out2["blocked"] is False


def test_run_compliance_guardrails_empty():
    result = c.run_compliance_guardrails("rank(close)")
    assert result.overall_blocked is False
    assert result.block_reasons == []


def test_run_compliance_guardrails_similarity_block():
    result = c.run_compliance_guardrails(
        "rank(close)", reference_expressions=["rank(close)"]
    )
    assert result.similarity_block is True
    assert result.overall_blocked is True


def test_run_compliance_guardrails_parameter_tweak():
    result = c.run_compliance_guardrails(
        "rank(close)",
        candidate_metrics={"decay": 101},
        previous_metrics={"decay": 100},
        improvement_threshold=0.05,
    )
    assert result.parameter_tweak_flag is True


def test_run_compliance_guardrails_duplicate_and_retry():
    now = datetime.now(timezone.utc).isoformat()
    result = c.run_compliance_guardrails(
        "rank(close)",
        submission_history=[{"expression": "rank(close)", "submitted_at": now}],
        failure_history=[{"expression": "rank(close)"}] * 5,
        retry_threshold=3,
    )
    assert result.duplicate_block is True
    assert result.high_frequency_block is True
    assert result.overall_blocked is True


def test_compliance_guardrail_result_defaults():
    r = ComplianceGuardrailResult()
    assert r.overall_blocked is False
    assert r.block_reasons == []


import pytest  # noqa: E402