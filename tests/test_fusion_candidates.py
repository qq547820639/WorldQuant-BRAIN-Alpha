from brain_alpha_ops.config import OpsConfig, ResearchBudget
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.fusion_candidates import FusionCandidateService, _fusion_expression_key
from brain_alpha_ops.research.scoring import build_scorecard


def _candidate(alpha_id: str, expression: str, score: float = 80.0, *, official: bool = True) -> Candidate:
    candidate = Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="Momentum",
        hypothesis=f"{alpha_id} hypothesis",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        local_quality={"passed": True, "score": 75},
        official_metrics={"sharpe": 1.4, "fitness": 1.1} if official else {},
        scorecard={"total_score": score},
    )
    if official:
        build_scorecard(candidate, OpsConfig().thresholds)
    return candidate


def _service(*, lifecycle=None, events=None, config=None):
    lifecycle = lifecycle if lifecycle is not None else []
    events = events if events is not None else []
    return FusionCandidateService(
        config=config or OpsConfig(budget=ResearchBudget(require_cloud_sync=False)),
        scoring_params=None,
        record_lifecycle=lambda candidate, stage, note="": lifecycle.append((candidate, stage, note)),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
    )


def test_fusion_candidate_service_creates_top_candidate_fusions():
    lifecycle = []
    events = []
    first = _candidate("a1", "rank(ts_delta(close, 20))", 90)
    second = _candidate("a2", "rank(ts_delta(volume, 20))", 85)
    pool = {
        _fusion_expression_key(first.expression): first,
        _fusion_expression_key(second.expression): second,
    }

    outcome = _service(lifecycle=lifecycle, events=events).create_top_candidate_fusions(
        pool,
        set(),
        cycle=7,
    )

    assert outcome.created_count == 2
    assert len(outcome.candidates) == 2
    assert all(candidate.mutation_type == "fusion" for candidate in outcome.candidates)
    assert all(candidate.lifecycle_status == "fusion_pending" for candidate in outcome.candidates)
    assert all(candidate.submission["fusion_cycle"] == 7 for candidate in outcome.candidates)
    assert lifecycle and all(row[1] == "fusion_created" for row in lifecycle)
    assert events and all(row[0][0] == "fusion_created" for row in events)
    assert len(pool) == 4


def test_fusion_candidate_service_requires_official_metrics():
    first = _candidate("a1", "rank(ts_delta(close, 20))", 90, official=False)
    second = _candidate("a2", "rank(ts_delta(volume, 20))", 85, official=False)
    pool = {
        _fusion_expression_key(first.expression): first,
        _fusion_expression_key(second.expression): second,
    }

    outcome = _service().create_top_candidate_fusions(pool, set(), cycle=1)

    assert outcome.created_count == 0
    assert outcome.candidates == []
    assert len(pool) == 2


def test_fusion_candidate_service_skips_blocked_duplicate_and_long_expressions(monkeypatch):
    first = _candidate("a1", "rank(close)", 90)
    second = _candidate("a2", "rank(volume)", 85)
    duplicate_expression = "rank(close) + rank(volume)"
    blocked_expression = "rank(open) + rank(high)"
    long_expression = "rank(" + "x" * 501 + ")"
    pool = {
        _fusion_expression_key(first.expression): first,
        _fusion_expression_key(second.expression): second,
        _fusion_expression_key(duplicate_expression): _candidate("existing", duplicate_expression, 70),
    }

    monkeypatch.setattr(
        "brain_alpha_ops.research.fusion.generate_fusion_expressions",
        lambda c1, c2: {
            "duplicate": duplicate_expression,
            "blocked": blocked_expression,
            "long": long_expression,
        },
    )

    outcome = _service().create_top_candidate_fusions(
        pool,
        {_fusion_expression_key(blocked_expression)},
        cycle=1,
    )

    assert outcome.created_count == 0
    assert outcome.candidates == []
    assert len(pool) == 3
