from brain_alpha_ops.config import OpsConfig, ResearchBudget
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.alpha_checks import AlphaCheckRegistry
from brain_alpha_ops.research.backtest_finalization import BacktestFinalizationService
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate


def _candidate(metrics=None, *, status="official_simulated") -> Candidate:
    candidate = Candidate(
        alpha_id="alpha_final",
        expression="rank(ts_delta(close, 20) / ts_std(returns, 20)) + rank(ts_delta(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Risk-adjusted price strength confirmed by normalized liquidity.",
        data_fields=["close", "returns", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_std"],
        official_alpha_id="official_final",
        official_metrics=dict(metrics or {}),
        lifecycle_status=status,
        local_quality={"passed": True, "score": 80},
    )
    return candidate


def _strong_metrics():
    return {
        "sharpe": 1.8,
        "fitness": 1.3,
        "turnover": 0.25,
        "returns": 0.08,
        "drawdown": 0.08,
        "sub_universe_sharpe": 1.4,
        "correlation": 0.3,
        "weight_concentration": 0.08,
        "margin": 5.0,
        "pass_fail": "PASS",
    }


def _weak_metrics():
    return {
        "sharpe": 0.4,
        "fitness": 0.2,
        "turnover": 0.9,
        "returns": -0.01,
        "drawdown": 0.4,
        "sub_universe_sharpe": 0.2,
        "correlation": 0.95,
        "weight_concentration": 0.4,
        "margin": 0.2,
        "pass_fail": "FAIL",
    }


def _expr_key(candidate: Candidate) -> str:
    return " ".join(candidate.expression.split()).lower()


class _Harness:
    def __init__(self, *, auto_submit_increment=0, retry_result=False, secondary_child=None):
        self.lifecycle = []
        self.archived = []
        self.accepted_seen = []
        self.auto_submit_increment = auto_submit_increment
        self.retry_result = retry_result
        self.secondary_child = secondary_child

    def service(self, config=None):
        registry = AlphaCheckRegistry()
        registry.build_default_checks()
        return BacktestFinalizationService(
            config=config or OpsConfig(budget=ResearchBudget(require_cloud_sync=False)),
            check_registry=registry,
            scoring_params=None,
            record_lifecycle=lambda candidate, stage, note="": self.lifecycle.append((candidate.alpha_id, stage, note)),
            remember_accepted=self._remember_accepted,
            retry_simulation=self._retry,
            create_secondary_fusion=self._secondary,
            archive=self._archive,
            try_auto_submit=lambda candidate, count: self.auto_submit_increment,
            should_remove_after_official_result=self._should_remove,
            event=lambda *args, **kwargs: None,
            expression_key=_expr_key,
        )

    def _remember_accepted(self, accepted, candidate):
        self.accepted_seen.append(candidate.alpha_id)
        candidate.lifecycle_status = "submission_ready"
        accepted.append(candidate)

    def _retry(self, candidate, pool, reason):
        if self.retry_result:
            candidate.lifecycle_status = "simulation_retry_pending"
            pool["retry"] = candidate
        return self.retry_result

    def _secondary(self, candidate, pool, blocked, reason):
        if self.secondary_child is not None:
            pool["secondary"] = self.secondary_child
            return self.secondary_child
        return None

    def _archive(self, archive_stats, archive_samples, candidates):
        self.archived.extend(candidate.alpha_id for candidate in candidates)
        archive_stats["ARCHIVED"] = archive_stats.get("ARCHIVED", 0) + len(candidates)

    def _should_remove(self, candidate):
        if not candidate.official_metrics:
            return candidate.lifecycle_status in {"simulation_failed", "simulation_poll_failed", "simulation_request_failed"}
        if candidate.gate.get("submission_ready"):
            candidate.lifecycle_status = "submission_ready"
            return False
        candidate.lifecycle_status = "official_standard_rejected"
        return True


def test_backtest_finalization_accepts_submission_ready_candidate(tmp_path):
    config = OpsConfig(budget=ResearchBudget(require_cloud_sync=False), storage_dir=str(tmp_path))
    harness = _Harness(auto_submit_increment=1)
    service = harness.service(config)
    candidate = _candidate(_strong_metrics())
    pool = {_expr_key(candidate): candidate}
    accepted = []

    outcome = service.finalize(
        candidate,
        pool_by_expression=pool,
        accepted_candidates=accepted,
        archive_stats={},
        archive_samples=[],
        blocked_expressions=set(),
        submitted_this_run=2,
        auto_submit=True,
    )

    assert outcome.ready_increment == 1
    assert outcome.accepted is True
    assert outcome.submitted_this_run == 3
    assert outcome.auto_submitted_increment == 1
    assert pool == {}
    assert accepted == [candidate]
    assert harness.lifecycle[-1][1] == "submission_ready"
    assert candidate.gate["submission_ready"] is True
    assert candidate.gate["check_summary"]["passed"] is True


def test_backtest_finalization_retries_failed_candidate_without_metrics():
    harness = _Harness(retry_result=True)
    service = harness.service()
    candidate = _candidate({}, status="simulation_failed")
    candidate.official_alpha_id = ""
    pool = {_expr_key(candidate): candidate}
    archive_stats = {}
    blocked = set()

    outcome = service.finalize(
        candidate,
        pool_by_expression=pool,
        accepted_candidates=[],
        archive_stats=archive_stats,
        archive_samples=[],
        blocked_expressions=blocked,
        submitted_this_run=0,
        auto_submit=False,
    )

    assert outcome.retried is True
    assert outcome.archived is False
    assert outcome.rejection_increment == 0
    assert archive_stats == {}
    assert blocked == set()
    assert candidate.lifecycle_status == "simulation_retry_pending"


def test_backtest_finalization_archives_official_rejection_and_records_secondary_child():
    child = Candidate(alpha_id="child", expression="rank(open)", family="Hybrid", hypothesis="secondary")
    harness = _Harness(secondary_child=child)
    service = harness.service()
    candidate = _candidate(_weak_metrics())
    build_scorecard(candidate, service.config.thresholds, service.config.scoring)
    evaluate_quality_gate(candidate, service.config.thresholds)
    pool = {_expr_key(candidate): candidate}
    archive_stats = {}
    blocked = set()

    outcome = service.finalize(
        candidate,
        pool_by_expression=pool,
        accepted_candidates=[],
        archive_stats=archive_stats,
        archive_samples=[],
        blocked_expressions=blocked,
        submitted_this_run=0,
        auto_submit=False,
    )

    assert outcome.rejection_increment == 1
    assert outcome.archived is True
    assert outcome.secondary_fusion_created is True
    assert "candidate" not in pool
    assert pool["secondary"] is child
    assert blocked
    assert archive_stats["ARCHIVED"] == 1
    assert harness.archived == ["alpha_final"]
    assert harness.lifecycle[-1][1] == "backtest_failed"
    assert candidate.lifecycle_status == "official_standard_rejected"
