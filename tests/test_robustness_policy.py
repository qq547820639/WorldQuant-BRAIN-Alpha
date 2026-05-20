from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.robustness_policy import RobustnessPolicy


def test_robustness_policy_allows_clean_reports():
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum robustness policy test",
        scorecard={"total_score": 88.0},
        gate={"submission_ready": True, "warnings": [], "failed_reasons": []},
    )

    payload = RobustnessPolicy().apply(
        candidate,
        {"recommendation": "pass", "score": 100},
        {"status": "pass", "passed": True, "score": 90},
    )

    assert payload["action"] == "allow"
    assert candidate.gate["submission_ready"] is True
    assert candidate.scorecard["total_score"] == 88.0


def test_robustness_policy_downgrades_caution_without_blocking():
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum robustness policy test",
        scorecard={"total_score": 80.0},
        gate={"submission_ready": True, "warnings": [], "failed_reasons": []},
    )

    payload = RobustnessPolicy(caution_multiplier=0.8).apply(
        candidate,
        {"recommendation": "caution", "score": 50},
        {"status": "pass", "passed": True, "score": 80},
    )

    assert payload["action"] == "downgrade"
    assert payload["blocked"] is False
    assert candidate.scorecard["total_score"] == 64.0
    assert candidate.scorecard["robustness_original_total_score"] == 80.0
    assert any("anti-overfit" in item for item in candidate.gate["warnings"])


def test_robustness_policy_blocks_high_overfit_risk():
    candidate = Candidate(
        alpha_id="a1",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="price momentum robustness policy test",
        scorecard={"total_score": 90.0},
        gate={"submission_ready": True, "warnings": [], "failed_reasons": []},
    )

    payload = RobustnessPolicy().apply(
        candidate,
        {"recommendation": "block", "score": 25},
        {"status": "pass", "passed": True, "score": 80},
    )

    assert payload["action"] == "block"
    assert payload["blocked"] is True
    assert candidate.gate["submission_ready"] is False
    assert candidate.gate["status"] == "ROBUSTNESS_BLOCKED"
    assert candidate.scorecard["total_score"] == 0.0
