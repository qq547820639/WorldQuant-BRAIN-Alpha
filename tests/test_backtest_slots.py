from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.backtest_slots import BacktestSlotManager


def _candidate(alpha_id: str, expression: str, *, slot: int = 0) -> Candidate:
    candidate = Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="test",
        hypothesis="test candidate",
    )
    if slot:
        candidate.submission["backtest_slot"] = slot
    return candidate


def test_backtest_slot_manager_tracks_capacity_and_release():
    manager = BacktestSlotManager()
    first = _candidate("a1", "rank(close)")

    assert manager.open_slots(3) == [1, 2, 3]

    manager.assign(2, first)

    assert manager.active_count() == 1
    assert manager.open_slots(3) == [1, 3]
    assert manager.get(2) is first
    assert manager.release(2) is first
    assert manager.open_slots(3) == [1, 2, 3]


def test_backtest_slot_manager_next_candidate_skips_active_expression():
    manager = BacktestSlotManager()
    manager.assign(1, _candidate("active", "rank(close)"))

    next_candidate = manager.next_candidate(
        [
            _candidate("duplicate", "rank(close)"),
            _candidate("fresh", "rank(volume)"),
        ],
        key_fn=lambda candidate: candidate.expression,
    )

    assert next_candidate
    assert next_candidate.alpha_id == "fresh"


def test_backtest_slot_manager_recovers_active_records_without_overwriting_slots():
    manager = BacktestSlotManager()
    manager.assign(1, _candidate("existing", "rank(open)", slot=1))
    rows = [
        {
            "action": "submitted",
            "slot": 1,
            "alpha_id": "persisted_existing_slot",
            "simulation_id": "sim_existing",
            "status": "SUBMITTED",
            "expression": "rank(close)",
        },
        {
            "action": "running",
            "slot": 2,
            "alpha_id": "persisted_active",
            "simulation_id": "sim_active",
            "status": "RUNNING",
            "expression": "rank(volume)",
            "poll_count": 2,
        },
        {
            "action": "completed",
            "slot": 3,
            "alpha_id": "persisted_done",
            "simulation_id": "sim_done",
            "status": "COMPLETED",
            "expression": "rank(high)",
        },
        {
            "action": "running",
            "slot": 4,
            "alpha_id": "persisted_outside_limit",
            "simulation_id": "sim_outside_limit",
            "status": "RUNNING",
            "expression": "rank(low)",
        },
    ]

    recovered = manager.recover_from_records(rows, max_slots=3)

    assert manager.recovered_slot_count == 1
    assert [slot for slot, _ in recovered] == [2]
    assert manager.get(1).alpha_id == "existing"
    assert manager.get(2).alpha_id == "persisted_active"
    assert manager.get(2).submission["poll_count"] == 2
    assert manager.open_slots(3) == [3]
