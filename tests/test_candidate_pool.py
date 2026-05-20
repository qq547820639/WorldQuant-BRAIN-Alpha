from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.candidate_pool import CandidatePoolService


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
    validation = _candidate("validation", "rank(open)", 61)
    too_low = _candidate("too_low", "rank(low)", 59)
    ready = _candidate("ready", "rank(high)", 82)
    ready.validation = {"status": "PASS"}
    deferred = _candidate("deferred", "rank(volume)", 75, status="simulation_deferred_rate_limit")

    assert service.validation_targets([validation, too_low, ready]) == [validation]
    assert [row.alpha_id for row in service.pending_backtest_candidates([ready, deferred, too_low])] == ["ready", "deferred"]
    assert [row.alpha_id for row in service.backtest_targets([ready, deferred], batch_size=1)] == ["ready"]


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
