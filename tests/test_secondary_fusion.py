from dataclasses import dataclass

from brain_alpha_ops.config import OpsConfig, ResearchBudget
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.secondary_fusion import SecondaryFusionService


def _parent(expression: str = "rank(ts_delta(close, 20))") -> Candidate:
    return Candidate(
        alpha_id="parent_alpha",
        expression=expression,
        family="Momentum",
        hypothesis="Price momentum weakened after official backtest.",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        source_tags=["official"],
        official_alpha_id="official_parent",
        official_metrics={"sharpe": 0.5, "fitness": 0.4, "turnover": 0.2},
        gate={"failed_reasons": ["LOW_SHARPE"]},
        submission={"simulation_retry_count": 1},
    )


@dataclass
class _Mutation:
    expression: str


class _Optimizer:
    def __init__(self, expressions):
        self.expressions = expressions

    def optimize(self, candidate, diagnostic, max_mutations=6):
        return [_Mutation(expression) for expression in self.expressions]


def _service(*, config=None, optimizer=None, lifecycle=None, events=None):
    lifecycle = lifecycle if lifecycle is not None else []
    events = events if events is not None else []
    return SecondaryFusionService(
        config=config or OpsConfig(budget=ResearchBudget(require_cloud_sync=False)),
        scoring_params=None,
        optimizer=optimizer,
        record_lifecycle=lambda candidate, stage, note="": lifecycle.append((candidate, stage, note)),
        event=lambda *args, **kwargs: events.append((args, kwargs)),
        retry_count=lambda candidate: int(candidate.submission.get("simulation_retry_count", 0) or 0),
    )


def test_secondary_fusion_service_creates_child_from_optimizer_expression():
    lifecycle = []
    events = []
    parent = _parent()
    pool = {}
    service = _service(
        optimizer=_Optimizer(["rank(ts_delta(volume, 30))"]),
        lifecycle=lifecycle,
        events=events,
    )

    outcome = service.create(
        parent,
        pool_by_expression=pool,
        blocked_expressions=set(),
        reason="official backtest result needs another research iteration",
    )

    child = outcome.candidate
    assert child is not None
    assert outcome.produced_increment == 1
    assert child.parent_id == "parent_alpha"
    assert child.mutation_type == "secondary_fusion"
    assert child.lifecycle_status == "secondary_fusion_pending"
    assert "secondary_fusion" in child.source_tags
    assert child.submission["parent_alpha_id"] == "parent_alpha"
    assert parent.submission["secondary_fusion_child_id"] == child.alpha_id
    assert pool
    assert lifecycle[0][1] == "secondary_fusion_created"
    assert events[0][0][0] == "secondary_fusion_created"


def test_secondary_fusion_service_respects_disabled_config():
    config = OpsConfig(
        budget=ResearchBudget(require_cloud_sync=False, enable_secondary_fusion=False)
    )
    events = []
    outcome = _service(config=config, events=events).create(
        _parent(),
        pool_by_expression={},
        blocked_expressions=set(),
        reason="disabled",
    )

    assert outcome.candidate is None
    assert outcome.skipped is True
    assert outcome.reason == "secondary fusion disabled"
    assert events == []


def test_secondary_fusion_service_skips_duplicate_and_blocked_expressions():
    events = []
    parent = _parent()
    duplicate = "rank(ts_delta(volume, 30))"
    blocked = "rank(ts_delta(open, 40))"
    pool = {"rank(ts_delta(volume,30))": Candidate(alpha_id="existing", expression=duplicate, family="x", hypothesis="x")}
    service = _service(
        optimizer=_Optimizer([duplicate, blocked, parent.expression]),
        events=events,
    )

    outcome = service.create(
        parent,
        pool_by_expression=pool,
        blocked_expressions={"rank(ts_delta(open,40))"},
        reason="no eligible variant",
    )

    assert outcome.candidate is None
    assert outcome.skipped is True
    assert outcome.produced_increment == 0
    assert events[-1][0][0] == "secondary_fusion_skipped"
