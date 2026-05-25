from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_cloud import (
    build_cloud_similarity_rows,
    cloud_correlation_risk,
    cloud_status_for_candidate,
    remember_accepted,
    smart_rank_candidates,
    smart_ranking_score,
)


def _candidate(alpha_id: str, expression: str, score: float = 0.0) -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="test",
        hypothesis="pipeline cloud helper test",
        scorecard={"total_score": score},
    )


def test_cloud_similarity_rows_and_risk_use_token_and_ast_matching():
    cloud_rows = [
        {"id": "same", "status": "ACTIVE", "expression": "rank(ts_delta(close, 20))"},
        {"id": "other", "status": "UNSUBMITTED", "expression": "rank(ts_mean(volume, 10))"},
    ]
    rows = build_cloud_similarity_rows(cloud_rows)

    risk = cloud_correlation_risk(_candidate("candidate", "rank(ts_delta(close, 20))"), rows)

    assert rows[0]["id"] == "same"
    assert rows[0]["tokens"]
    assert risk["level"] == "high"
    assert risk["matched_alpha_id"] == "same"
    assert "bypass compliance" in risk["note"]


def test_cloud_risk_excludes_current_official_alpha_id():
    candidate = _candidate("candidate", "rank(ts_delta(close, 20))")
    candidate.official_alpha_id = "same"
    rows = build_cloud_similarity_rows(
        [
            {"id": "same", "status": "ACTIVE", "expression": "rank(ts_delta(close, 20))"},
            {"id": "near", "status": "UNSUBMITTED", "expression": "rank(ts_delta(close, 19))"},
        ]
    )

    risk = cloud_correlation_risk(candidate, rows)

    assert risk["matched_alpha_id"] != "same"


def test_cloud_status_matches_official_id_before_expression():
    candidate = _candidate("candidate", "rank(close)")
    candidate.official_alpha_id = "official_1"

    status = cloud_status_for_candidate(
        candidate,
        [
            {"id": "expr_match", "status": "UNSUBMITTED", "expression": "rank(close)"},
            {"id": "official_1", "status": "ACTIVE", "expression": "rank(volume)"},
        ],
    )

    assert status == {"id": "official_1", "status": "ACTIVE", "match": "official_id"}


def test_remember_accepted_dedupes_and_caps_by_score():
    accepted = [_candidate("existing", "rank(close)", 80)]
    duplicate = _candidate("duplicate", "rank(close)", 99)
    better = _candidate("better", "rank(volume)", 90)

    remember_accepted(accepted, duplicate, limit=2)
    remember_accepted(accepted, better, limit=2)

    assert [row.alpha_id for row in accepted] == ["better", "existing"]
    assert accepted[0].lifecycle_status == "submission_ready"
    assert duplicate not in accepted


def test_smart_rank_penalizes_high_cloud_risk():
    high_risk = _candidate("high", "rank(close)", 95)
    low_risk = _candidate("low", "rank(volume)", 80)
    high_risk.gate = {"submission_ready": True}
    low_risk.gate = {"submission_ready": True}

    ranked = smart_rank_candidates(
        [high_risk, low_risk],
        lambda candidate: {"level": "high" if candidate.alpha_id == "high" else "low"},
    )

    assert smart_ranking_score(high_risk, {"level": "high"}) == 65
    assert [row.alpha_id for row in ranked] == ["low", "high"]
