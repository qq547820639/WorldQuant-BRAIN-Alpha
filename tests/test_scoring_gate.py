from brain_alpha_ops.config import QualityThresholds, ScoringConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import build_scorecard, decision_band, empirical_score, evaluate_quality_gate


def _candidate(metrics):
    c = Candidate(
        alpha_id="A1",
        expression="rank(ts_delta(close, 20) / ts_std(returns, 20)) + rank(ts_delta(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Risk-adjusted price strength is more robust when confirmed by normalized liquidity.",
        data_fields=["close", "returns", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_std"],
    )
    c.local_quality = {"passed": True, "score": 80}
    c.official_alpha_id = "official_1"
    c.official_metrics = metrics
    return c


def test_gate_accepts_strong_official_candidate():
    c = _candidate(
        {
            "sharpe": 1.8,
            "fitness": 1.3,
            "turnover": 0.25,
            "returns": 0.08,
            "drawdown": 0.08,
            "sub_universe_sharpe": 1.4,
            "correlation": 0.3,
            "weight_concentration": 0.08,
            "margin": 5.0,
            "pass_fail": "PASS",
        }
    )
    build_scorecard(c, QualityThresholds())
    gate = evaluate_quality_gate(c, QualityThresholds())
    assert gate["submission_ready"]


def test_gate_rejects_high_correlation():
    c = _candidate(
        {
            "sharpe": 1.8,
            "fitness": 1.3,
            "turnover": 0.25,
            "returns": 0.08,
            "drawdown": 0.08,
            "sub_universe_sharpe": 1.4,
            "correlation": 0.8,
            "weight_concentration": 0.2,
            "margin": 5.0,
            "pass_fail": "PASS",
        }
    )
    build_scorecard(c, QualityThresholds())
    gate = evaluate_quality_gate(c, QualityThresholds())
    assert not gate["submission_ready"]
    assert any("correlation" in reason for reason in gate["failed_reasons"])


def test_delay_zero_uses_official_delay_zero_thresholds():
    c = _candidate(
        {
            "sharpe": 1.8,
            "fitness": 1.2,
            "turnover": 0.25,
            "returns": 0.08,
            "drawdown": 0.08,
            "sub_universe_sharpe": 1.4,
            "correlation": 0.3,
            "weight_concentration": 0.08,
            "margin": 5.0,
            "pass_fail": "PASS",
        }
    )
    c.submission["settings"] = {"delay": 0}

    scorecard = build_scorecard(c, QualityThresholds())

    assert scorecard["empirical"]["delay"] == 0
    assert scorecard["empirical"]["hard_gate_failed"] is True
    assert any("sharpe >= 2.0" in reason for reason in scorecard["empirical"]["hard_gate_failures"])


def test_scorecard_includes_attribution_tree_failures_and_hints():
    c = _candidate(
        {
            "sharpe": 0.8,
            "fitness": 0.6,
            "turnover": 0.82,
            "returns": -0.02,
            "drawdown": 0.4,
            "sub_universe_sharpe": 0.4,
            "correlation": 0.91,
            "weight_concentration": 0.22,
            "margin": 1.0,
            "pass_fail": "FAIL",
        }
    )

    scorecard = build_scorecard(c, QualityThresholds())

    assert scorecard["attribution_tree"]["name"] == "total_score"
    assert scorecard["attribution_tree"]["children"]
    assert any(item["severity"] == "blocking" for item in scorecard["top_failures"])
    assert scorecard["improvement_hints"]


def test_empirical_score_keeps_official_thresholds_under_market_regime():
    metrics = {
        "sharpe": 1.3,
        "fitness": 1.05,
        "turnover": 0.25,
        "returns": 0.08,
        "drawdown": 0.08,
        "sub_universe_sharpe": 1.4,
        "correlation": 0.3,
        "weight_concentration": 0.08,
        "margin": 5.0,
        "pass_fail": "PASS",
    }

    result = empirical_score(metrics, QualityThresholds(market_regime="low_vol"), settings={"delay": 1})

    assert result["threshold_source"] == "BRAIN_Official"
    assert result["regime_adjustments_applied_to_hard_gates"] is False
    assert result["hard_gate_failed"] is False


def test_decision_band_uses_configurable_thresholds():
    scoring = ScoringConfig(decision_thresholds={"submit": 90, "optimize": 80, "research": 60})

    assert decision_band(88, scoring=scoring) == "optimize_before_submit"
    assert decision_band(92, scoring=scoring) == "submit_candidate"
    assert decision_band(58, scoring=scoring) == "abandon_or_rebuild"
    assert decision_band(92, hard_gate_failed=True, scoring=scoring) == "hard_gate_blocked"


def test_scorecard_passes_configurable_decision_thresholds():
    c = Candidate(
        alpha_id="local_threshold",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="Price momentum candidate.",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        local_quality={"passed": True, "score": 80},
    )

    default = build_scorecard(c, QualityThresholds())
    configured = build_scorecard(
        c,
        QualityThresholds(),
        ScoringConfig(decision_thresholds={"submit": 95, "optimize": 85, "research": 75}),
    )

    assert default["decision_band"] in {"optimize_before_submit", "submit_candidate"}
    assert configured["decision_band"] == "research_only"


def test_empirical_score_handles_zero_alpha_size_and_negative_sharpe():
    result = empirical_score(
        {
            "sharpe": -0.1,
            "fitness": 1.2,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "sub_universe_sharpe": 0.0,
            "correlation": 0.2,
            "weight_concentration": 0.02,
            "margin": 5.0,
            "alpha_size": 0,
            "sub_universe_size": 0,
        },
        QualityThresholds(),
    )

    item = next(row for row in result["items"] if row["name"] == "sub_universe_sharpe")
    assert item["target"] == 0.0
    assert item["passed"] is True


def test_local_scorecard_applies_strong_assistant_guidance_bonus():
    c = Candidate(
        alpha_id="guided_strong",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="Price momentum confirmed by strong historical assistant guidance.",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        local_quality={"passed": True, "score": 76},
        submission={
            "assistant_guidance_digest": "ag_score_strong",
            "assistant_guidance_confidence": 0.9,
            "assistant_guidance_outcome_status": "strong",
            "assistant_guidance_outcome": {
                "count": 4,
                "success_rate": 0.75,
                "avg_score": 84,
            },
        },
    )

    scorecard = build_scorecard(c, QualityThresholds())
    adjustment = scorecard["assistant_guidance_adjustment"]

    assert adjustment["adjustment"] > 0
    assert adjustment["applied_to_total"] is True
    assert adjustment["outcome_status"] == "strong"
    assert scorecard["total_score"] == round(scorecard["base_local_rank_score"] + adjustment["adjustment"], 2)


def test_local_scorecard_applies_weak_assistant_guidance_penalty():
    c = Candidate(
        alpha_id="guided_weak",
        expression="rank(ts_mean(volume, 5))",
        family="Liquidity",
        hypothesis="Volume pressure idea with weak historical assistant guidance.",
        data_fields=["volume"],
        operators=["rank", "ts_mean"],
        local_quality={"passed": True, "score": 76},
        submission={
            "assistant_guidance_digest": "ag_score_weak",
            "assistant_guidance_confidence": 0.95,
            "assistant_guidance_outcome_status": "weak",
            "assistant_guidance_outcome": {
                "count": 3,
                "success_rate": 0.0,
                "avg_score": 24,
            },
        },
    )

    scorecard = build_scorecard(c, QualityThresholds())
    adjustment = scorecard["assistant_guidance_adjustment"]

    assert adjustment["adjustment"] < 0
    assert adjustment["outcome_status"] == "weak"
    assert scorecard["total_score"] == round(scorecard["base_local_rank_score"] + adjustment["adjustment"], 2)


def test_assistant_guidance_score_adjustment_respects_scoring_config_caps_and_disable():
    c = Candidate(
        alpha_id="guided_configured",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="Price momentum with configurable assistant guidance scoring.",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        local_quality={"passed": True, "score": 76},
        submission={
            "assistant_guidance_digest": "ag_score_configured",
            "assistant_guidance_confidence": 1.0,
            "assistant_guidance_outcome_status": "strong",
            "assistant_guidance_outcome": {
                "count": 5,
                "success_rate": 0.9,
                "avg_score": 90,
            },
        },
    )

    capped = build_scorecard(
        c,
        QualityThresholds(),
        ScoringConfig(assistant_guidance_score_bonus_cap=1.25),
    )
    assert capped["assistant_guidance_adjustment"]["adjustment"] == 1.25
    assert capped["assistant_guidance_adjustment"]["configuration"]["bonus_cap"] == 1.25

    c.submission["assistant_guidance_confidence"] = 0.4
    low_confidence = build_scorecard(
        c,
        QualityThresholds(),
        ScoringConfig(assistant_guidance_score_min_confidence=0.8),
    )
    assert low_confidence["assistant_guidance_adjustment"]["adjustment"] == 0.0
    assert "confidence" in low_confidence["assistant_guidance_adjustment"]["reason"]

    c.submission["assistant_guidance_confidence"] = 1.0
    c.submission["assistant_guidance_outcome"]["count"] = 0
    low_evidence = build_scorecard(
        c,
        QualityThresholds(),
        ScoringConfig(assistant_guidance_score_min_outcome_count=1),
    )
    assert low_evidence["assistant_guidance_adjustment"]["adjustment"] == 0.0
    assert "historical outcome evidence" in low_evidence["assistant_guidance_adjustment"]["reason"]

    disabled = build_scorecard(
        c,
        QualityThresholds(),
        ScoringConfig(assistant_guidance_score_adjustment_enabled=False),
    )
    assert disabled["assistant_guidance_adjustment"]["adjustment"] == 0.0
    assert disabled["assistant_guidance_adjustment"]["source"] == "disabled"
    assert disabled["assistant_guidance_adjustment"]["applied_to_total"] is False
    assert disabled["total_score"] == disabled["base_local_rank_score"]
