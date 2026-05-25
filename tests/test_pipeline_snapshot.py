from types import SimpleNamespace

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_snapshot import (
    PipelineSnapshotBuilder,
    PipelineSnapshotServices,
    PipelineSnapshotState,
    backtest_slot_snapshot,
)


def _candidate(
    alpha_id: str,
    score: float,
    *,
    ready: bool = False,
    status: str = "created",
    simulation_id: str = "",
) -> Candidate:
    candidate = Candidate(
        alpha_id=alpha_id,
        expression=f"rank({alpha_id})",
        family="test",
        hypothesis="pipeline snapshot test",
        lifecycle_status=status,
        simulation_id=simulation_id,
        scorecard={"total_score": score},
    )
    if ready:
        candidate.gate = {"submission_ready": True}
    if simulation_id:
        candidate.submission = {"simulation_status": "RUNNING"}
    return candidate


def _config():
    return SimpleNamespace(
        budget=SimpleNamespace(
            retained_alpha_pool_size=2,
            official_backtest_batch_size=3,
            max_official_validations_per_cycle=4,
            max_official_simulations_per_cycle=5,
            max_official_concurrent_simulations=6,
            max_simulation_retries=2,
            enable_secondary_fusion=True,
            resume_persisted_backtests=True,
            min_prior_score_for_official_validation=60,
            min_prior_score_for_official_simulation=70,
            run_forever=False,
        )
    )


def _builder() -> PipelineSnapshotBuilder:
    return PipelineSnapshotBuilder(
        config=_config(),
        services=PipelineSnapshotServices(
            candidate_pool_candidates=lambda rows: [row for row in rows if row.lifecycle_status != "simulation_retry_pending"],
            pending_backtest_candidates=lambda rows: [row for row in rows if row.simulation_id],
            validation_targets=lambda rows: [row for row in rows if not row.validation and not row.simulation_id],
            active_backtest_limit=lambda: 3,
            poll_interval_seconds=lambda: 6.0,
            slot_snapshot=lambda: [{"slot": 1, "status": "EMPTY"}],
            current_strategy_profile=lambda: {"name": "profile-a", "label": "Profile A"},
            strategy_lifecycle_summary=lambda profile, index: {"active_profile": profile["name"], "active_index": index},
            strategy_plugin_summary=lambda: {"enabled": False, "plugins": []},
            observability_official_call_guard_snapshot=lambda: {"blocked": 0},
            assess_auto_submission=lambda candidate, _submitted: {
                "failed_reasons": ["manual block"] if candidate.alpha_id == "blocked" else []
            },
            smart_rank_candidates=lambda rows: sorted(rows, key=lambda row: row.scorecard.get("total_score", 0), reverse=True),
            smart_ranking_score=lambda candidate: candidate.scorecard.get("total_score", 0),
            cloud_correlation_risk=lambda candidate: {"level": "low", "alpha_id": candidate.alpha_id},
        ),
    )


def test_candidate_and_backtest_snapshots_preserve_contract():
    builder = _builder()
    candidate = _candidate("alpha_a", 81, ready=True, simulation_id="sim_a")
    candidate.official_alpha_id = "official_a"

    snapshot = builder.candidate_snapshot([candidate], retained=False)
    backtests = builder.backtest_snapshot([candidate])

    assert snapshot[0]["alpha_id"] == "alpha_a"
    assert snapshot[0]["pool_rank"] == 1
    assert snapshot[0]["in_retained_pool"] is False
    assert snapshot[0]["smart_rank_score"] == 81
    assert snapshot[0]["cloud_correlation_risk"]["level"] == "low"
    assert backtests == [
        {
            "alpha_id": "alpha_a",
            "simulation_id": "sim_a",
            "status": "RUNNING",
            "official_alpha_id": "official_a",
            "score": 81,
        }
    ]


def test_runtime_data_contains_counts_policy_and_bandit_state():
    builder = _builder()
    ready = _candidate("ready", 90, ready=True)
    pending = _candidate("pending", 75, simulation_id="sim_pending")
    archived = {"LOCAL_STANDARD_REJECTED": 2}
    state = PipelineSnapshotState(
        produced_count=5,
        official_validation_attempted_count=3,
        official_validation_passed_count=2,
        recovered_backtest_slot_count=1,
        bandit_rewards={0: [0.25, 0.75]},
        bandit_counts={0: 2},
        strategy_switch_count=4,
        strategy_profile_index=0,
        active_dataset_id="fundamental6",
    )

    payload = builder.runtime_data(7, [ready, pending], [ready], archived, state, extra={"custom": True})

    assert payload["cycle"] == 7
    assert payload["candidate_pool_available_count"] == 2
    assert payload["pending_backtest_count"] == 1
    assert payload["rejected_count"] == 2
    assert payload["official_call_policy"]["active_backtest_slot_limit"] == 3
    assert payload["official_call_policy"]["poll_interval_seconds"] == 6.0
    assert payload["bandit"]["profile_rewards"] == {"0": 0.5}
    assert payload["strategy_lifecycle"]["active_index"] == 0
    assert payload["active_dataset_id"] == "fundamental6"
    assert payload["custom"] is True


def test_summary_counts_ready_auto_allowed_and_archived_candidates():
    builder = _builder()
    ready = _candidate("ready", 91, ready=True)
    blocked = _candidate("blocked", 88, ready=True)
    pending = _candidate("pending", 73, simulation_id="sim_pending")
    retry = _candidate("retry", 65, status="simulation_retry_pending")
    pool = {row.expression: row for row in [ready, blocked, pending, retry]}
    state = PipelineSnapshotState(
        produced_count=6,
        officially_simulated_count=2,
        official_validation_attempted_count=4,
        official_validation_passed_count=3,
        backtests_submitted=2,
        strategy_profile_index=1,
        user_profile={"tier": "consultant"},
    )

    summary = builder.summary([ready, blocked, pending, retry], 1, pool, {"REJECTED": 2}, state)

    assert summary["total_candidates"] == 6
    assert summary["retained_pool_size"] == 3
    assert summary["pending_backtest_count"] == 1
    assert summary["simulation_retry_pending"] == 1
    assert summary["submission_ready"] == 2
    assert summary["auto_submit_ready"] == 1
    assert summary["submitted_this_run"] == 1
    assert summary["officially_simulated"] == 2
    assert summary["strategy_lifecycle"]["active_index"] == 1
    assert summary["user_profile"] == {"tier": "consultant"}
    assert summary["score_distribution"]
    assert summary["gate_summary"]["quality_gate"]["pass"] == 2


def test_backtest_slot_snapshot_renders_empty_halted_and_active_slots():
    active = _candidate("active", 82, simulation_id="sim_active")
    active.family = "quality"
    active.hypothesis = "active slot"
    active.submission = {"simulation_status": "RUNNING", "next_poll_at": 105.0, "poll_count": 2}
    slots = {2: active}

    rows = backtest_slot_snapshot(
        active_limit=3,
        candidate_at_slot=lambda slot: slots.get(slot),
        official_calls_halted=False,
        official_halt_reason="",
        cloud_correlation_risk=lambda candidate: {"level": "low", "alpha_id": candidate.alpha_id},
        now=100.0,
    )

    assert rows[0]["status"] == "EMPTY"
    assert rows[0]["message"] == "Waiting for candidate backfill."
    assert rows[1]["alpha_id"] == "active"
    assert rows[1]["progress_percent"] == 65
    assert rows[1]["next_poll_seconds"] == 5.0
    assert rows[1]["cloud_correlation_risk"]["level"] == "low"
    assert rows[2]["status"] == "EMPTY"

    halted = backtest_slot_snapshot(
        active_limit=1,
        candidate_at_slot=lambda _slot: None,
        official_calls_halted=True,
        official_halt_reason="rate limit",
        cloud_correlation_risk=lambda _candidate: {},
        now=100.0,
    )

    assert halted[0]["status"] == "CAPACITY_WAIT"
    assert "rate limit" in halted[0]["message"]
