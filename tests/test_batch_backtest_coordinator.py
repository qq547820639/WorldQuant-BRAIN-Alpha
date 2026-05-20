from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.batch_backtest_coordinator import BatchBacktestCoordinator


def _candidate(alpha_id, score, expression="rank(close)", simulation_id="", official_metrics=None):
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="Momentum",
        hypothesis="batch coordinator test",
        scorecard={"total_score": score},
        simulation_id=simulation_id,
        official_metrics=official_metrics or {},
    )


def test_batch_backtest_coordinator_selects_ranked_capacity():
    coordinator = BatchBacktestCoordinator(
        ranker=lambda rows: sorted(rows, key=lambda row: row.scorecard["total_score"], reverse=True),
        min_score=70,
        batch_size=2,
    )

    plan = coordinator.plan([
        _candidate("low", 60, "rank(low)"),
        _candidate("top", 95, "rank(top)"),
        _candidate("mid", 80, "rank(mid)"),
    ])

    assert [candidate.alpha_id for candidate in plan.selected] == ["top", "mid"]
    assert plan.skipped[0]["reason"] == "score_below_threshold"
    assert plan.to_dict()["schema_version"] == "batch_backtest_plan.v1"


def test_batch_backtest_coordinator_skips_duplicates_and_existing_work():
    coordinator = BatchBacktestCoordinator(
        ranker=lambda rows: rows,
        min_score=70,
        batch_size=5,
    )

    plan = coordinator.plan([
        _candidate("a1", 90, "rank(close)"),
        _candidate("a2", 89, "rank(close)"),
        _candidate("a3", 88, "rank(volume)", simulation_id="sim_1"),
    ])

    assert [candidate.alpha_id for candidate in plan.selected] == ["a1"]
    assert {row["reason"] for row in plan.skipped} == {"duplicate_expression", "already_has_official_work"}
