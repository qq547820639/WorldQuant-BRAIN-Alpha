from brain_alpha_ops.research.contracts import (
    backtest_record,
    recoverable_backtest_candidates,
)


def test_backtest_contract_adds_schema_and_correlation_id():
    row = backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "status": "SUBMITTED",
            "expression": "rank(close)",
        },
    )

    assert row["schema_version"] == "backtest_record.v1"
    assert row["run_id"] == "run_1"
    assert row["correlation_id"].startswith("corr_")


def test_recoverable_backtest_candidates_uses_latest_active_rows():
    rows = [
        {
            "action": "submitted",
            "slot": 1,
            "alpha_id": "old",
            "simulation_id": "sim_old",
            "status": "SUBMITTED",
            "expression": "rank(close)",
        },
        {
            "action": "completed",
            "slot": 1,
            "alpha_id": "old",
            "simulation_id": "sim_old",
            "status": "COMPLETED",
            "expression": "rank(close)",
        },
        {
            "action": "running",
            "slot": 2,
            "alpha_id": "active",
            "simulation_id": "sim_active",
            "status": "RUNNING",
            "expression": "rank(ts_delta(close, 20))",
            "poll_count": 3,
        },
    ]

    recovered = recoverable_backtest_candidates(rows, max_slots=3)

    assert len(recovered) == 1
    assert recovered[0].alpha_id == "active"
    assert recovered[0].simulation_id == "sim_active"
    assert recovered[0].submission["backtest_slot"] == 2
    assert recovered[0].submission["recovered_from_persistence"] is True
