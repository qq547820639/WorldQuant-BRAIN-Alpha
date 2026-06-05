from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research import candidate_pool
from brain_alpha_ops.research.candidate_pool import (
    CandidatePoolService,
    candidate_official_work_blockers,
    is_active_backtest_candidate,
    pending_simulation_targets,
)
from brain_alpha_ops.research.pipeline_helpers import is_hard_backtest_blocked


def _candidate(alpha_id: str, expression: str, score: float, *, status: str = "created") -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="test",
        hypothesis="candidate pool test",
        scorecard={"total_score": score},
        lifecycle_status=status,
    )


def _service() -> CandidatePoolService:
    ranker = lambda rows: sorted(rows, key=lambda row: row.scorecard.get("total_score", 0), reverse=True)
    return CandidatePoolService(
        retained_alpha_pool_size=2,
        min_prior_score_for_official_validation=60,
        min_prior_score_for_official_simulation=70,
        ranker=ranker,
        smart_ranker=ranker,
    )


def test_candidate_pool_service_merges_best_expression_and_blocks_rejected_keys():
    service = _service()
    pool = {}
    blocked = set()
    low = _candidate("low", "rank(close)", 65)
    high = _candidate("high", "rank(close)", 80)

    skipped = service.merge_into_pool(pool, [low, high], blocked)

    assert skipped == []
    assert list(pool.values()) == [high]
    assert high.lifecycle_status == "candidate_pool_retained"

    blocked.add("rank(volume)")
    skipped = service.merge_into_pool(pool, [_candidate("blocked", "rank(volume)", 90)], blocked)

    assert skipped[0].lifecycle_status == "previously_rejected_expression_skipped"
    assert skipped[0].gate["status"] == "PREVIOUSLY_REJECTED_EXPRESSION_SKIPPED"


def test_candidate_pool_service_filters_validation_and_backtest_targets():
    service = _service()
    validation = _candidate("validation", "rank(open)", 72)
    validation_only_dead_end = _candidate("validation_only_dead_end", "rank(close)", 61)
    too_low = _candidate("too_low", "rank(low)", 59)
    ready = _candidate("ready", "rank(high)", 82)
    ready.validation = {"status": "PASS"}
    deferred = _candidate("deferred", "rank(volume)", 75, status="simulation_deferred_rate_limit")

    assert service.validation_targets([validation, validation_only_dead_end, too_low, ready]) == [validation]
    assert [row.alpha_id for row in service.pending_backtest_candidates([ready, deferred, too_low])] == ["ready", "deferred"]
    assert [row.alpha_id for row in service.backtest_targets([ready, deferred], batch_size=1)] == ["ready"]


def test_candidate_pool_blocks_known_local_risks_from_official_work():
    service = _service()
    high_turnover = _candidate("high_turnover", "rank(ts_delta(returns, 10))", 95)
    high_turnover.local_quality = {"passed": True}
    local_failed = _candidate("local_failed", "rank(ts_mean(close, 20))", 96)
    local_failed.local_quality = {
        "passed": False,
        "local_backtest": {"pass_local": False},
    }
    ready = _candidate("ready", "rank(ts_mean(volume, 20))", 90)
    ready.local_quality = {"passed": True}

    assert "high_turnover_generation_risk:direct_returns_delta_window=10" in candidate_official_work_blockers(high_turnover)
    assert candidate_official_work_blockers(local_failed) == ["local_backtest_failed", "local_quality_failed"]
    assert service.validation_targets([high_turnover, local_failed, ready]) == [ready]

    high_turnover.validation = {"status": "PASS"}
    local_failed.validation = {"status": "PASS"}
    ready.validation = {"status": "PASS"}

    assert service.pending_backtest_candidates([high_turnover, local_failed, ready]) == [ready]


def test_candidate_pool_blocks_official_context_warnings_from_official_work():
    service = _service()
    candidate = _candidate("context_warning", "rank(not_an_official_field)", 95)
    candidate.local_quality = {"passed": True}
    candidate.gate = {
        "status": "OFFICIAL_CONTEXT_WARNING",
        "warnings": ["field 'not_an_official_field' is not in official context"],
    }

    assert candidate_official_work_blockers(candidate) == [
        "official_context_warning:field 'not_an_official_field' is not in official context"
    ]
    assert service.validation_targets([candidate]) == []

    candidate.validation = {"status": "PASS"}

    assert service.pending_backtest_candidates([candidate]) == []


def test_candidate_pool_uses_shared_hard_backtest_block_helper():
    assert candidate_pool.is_hard_backtest_blocked is is_hard_backtest_blocked
    assert is_hard_backtest_blocked("simulation_failed") is True
    assert is_hard_backtest_blocked("simulation_deferred_rate_limit") is False


def test_candidate_pool_service_prunes_without_removing_active_or_pending():
    service = _service()
    service.retained_alpha_pool_size = 1
    active = _candidate("active", "rank(close)", 10, status="simulation_running")
    active.simulation_id = "sim_active"
    pending = _candidate("pending", "rank(open)", 71)
    pending.validation = {"status": "PASS"}
    keep = _candidate("keep", "rank(high)", 90)
    prune = _candidate("prune", "rank(low)", 65)
    pool = {row.expression: row for row in [active, pending, keep, prune]}

    pruned = service.prune_pool(
        pool,
        is_active_backtest_candidate=lambda row: bool(row.simulation_id and not row.official_metrics),
    )

    assert [row.alpha_id for row in pruned] == ["prune"]
    assert set(row.alpha_id for row in pool.values()) == {"active", "pending", "keep"}
    assert prune.lifecycle_status == "candidate_pool_pruned"


def test_candidate_pool_identifies_active_and_pending_simulation_targets():
    active = _candidate("active", "rank(close)", 80, status="simulation_running")
    active.simulation_id = "sim_active"
    completed = _candidate("completed", "rank(open)", 80, status="submission_ready")
    completed.simulation_id = "sim_completed"
    failed = _candidate("failed", "rank(low)", 80, status="simulation_failed")
    failed.simulation_id = "sim_failed"
    metriced = _candidate("metriced", "rank(high)", 80, status="simulation_running")
    metriced.simulation_id = "sim_metriced"
    metriced.official_metrics = {"sharpe": 1.2}

    assert is_active_backtest_candidate(active) is True
    assert is_active_backtest_candidate(completed) is False
    assert is_active_backtest_candidate(failed) is False
    assert is_active_backtest_candidate(metriced) is False
    assert pending_simulation_targets([completed, active, failed, metriced]) == [active]
