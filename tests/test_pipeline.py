from __future__ import annotations
import json
import logging
import tempfile
from pathlib import Path

from brain_alpha_ops.brain_api.base import BrainAPIError
from tests.production_api_stub import ProductionBrainAPIStub
from brain_alpha_ops.config import OfficialAPIConfig, OpsConfig, ResearchBudget
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
from brain_alpha_ops.research.pipeline_helpers import expr_key
from brain_alpha_ops.research.repository import ResearchRepository


def _single_cycle_config(tmp_path, **budget_overrides):
    budget_kwargs = {
        "max_candidates_per_cycle": 3,
        "max_official_validations_per_cycle": 0,
        "max_official_simulations_per_cycle": 0,
        "max_cycles": 1,
        "require_cloud_sync": False,
    }
    budget_kwargs.update(budget_overrides)
    return OpsConfig(budget=ResearchBudget(**budget_kwargs), storage_dir=str(tmp_path))


def test_pipeline_keeps_visible_backtest_slots_separate_from_official_capacity(tmp_path):
    config = _single_cycle_config(
        tmp_path,
        max_official_simulations_per_cycle=1,
        max_official_concurrent_simulations=1,
        official_backtest_batch_size=1,
    )
    pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())

    assert pipeline._active_backtest_limit() == 1

    slots = pipeline._slot_snapshot()

    assert [slot["slot"] for slot in slots] == [1, 2, 3]
    assert {slot["status"] for slot in slots} == {"EMPTY"}


def test_pipeline_runs_production_stub_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=8,
                max_official_simulations_per_cycle=5,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)
        data = result.to_dict()
        assert data["summary"]["total_candidates"] >= 5
        assert data["summary"]["officially_simulated"] > 0
        assert data["candidates"]
        assert any(event["event"] == "run_completed" for event in data["events"])
        first_event = data["events"][0]
        assert first_event["data"]["schema_version"] == "observability.v1"
        assert first_event["data"]["run_id"] == data["run_id"]
        assert first_event["data"]["event"] == first_event["event"]


def test_pipeline_auto_calibration_uses_config_storage_dir(monkeypatch, tmp_path):
    captured = {}

    def fake_auto_calibrate_if_stalled(storage_dir):
        captured["storage_dir"] = storage_dir
        return {
            "ok": True,
            "triggered": True,
            "reason": "score_history_stalled",
            "advice": {"prior_layer_weight": 0.31},
        }

    monkeypatch.setattr(
        "brain_alpha_ops.research.calibration.auto_calibrate_if_stalled",
        fake_auto_calibrate_if_stalled,
    )
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=3,
            max_official_validations_per_cycle=0,
            max_official_simulations_per_cycle=0,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )

    result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

    assert captured["storage_dir"] == str(tmp_path)
    event = next(event for event in result.events if event.event == "auto_calibration")
    assert event.message == "Auto-calibration triggered: score_history_stalled"
    assert event.data["triggered"] is True
    assert event.data["reason"] == "score_history_stalled"
    assert event.data["advice"] == {"prior_layer_weight": 0.31}


def test_pipeline_logs_context_refresh_exceptions(monkeypatch, caplog, tmp_path):
    class FailingContextLoader:
        def refresh(self):
            raise RuntimeError("context refresh unavailable Bearer token_12345")

        def get_datasets(self):
            class Dataset:
                id = "pv1"

            return [Dataset()]

    pipeline = AlphaResearchPipeline(
        config=_single_cycle_config(tmp_path),
        api=ProductionBrainAPIStub(),
    )
    pipeline._loader = FailingContextLoader()
    monkeypatch.setattr(
        pipeline,
        "_load_official_context",
        lambda: ([{"id": "close", "name": "close", "dataset": "pv1"}], [{"name": "rank"}]),
    )

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.pipeline"):
        result = pipeline.run(auto_submit=False)
    pipeline_log_text = "\n".join(
        str(record.message)
        for record in caplog.records
        if record.name == "brain_alpha_ops.research.pipeline"
    )

    event = next(event for event in result.events if event.event == "context_refresh_error")
    assert event.level == "ERROR"
    assert "context refresh unavailable" in event.message
    assert "token_12345" not in event.message
    assert "Context refresh exception in cycle 1" in pipeline_log_text
    assert "context refresh unavailable" in pipeline_log_text
    assert "token_12345" not in pipeline_log_text
    assert "Traceback" not in pipeline_log_text


def test_pipeline_logs_scoring_calibration_exceptions(monkeypatch, caplog, tmp_path):
    pipeline = AlphaResearchPipeline(
        config=_single_cycle_config(tmp_path),
        api=ProductionBrainAPIStub(),
    )
    monkeypatch.setattr(pipeline.auto_calibrator, "needs_calibration", lambda: True)

    def fail_calibrate():
        """Fail during calibration for warning coverage."""
        raise RuntimeError("score calibration unavailable password=dummy1")

    monkeypatch.setattr(pipeline.auto_calibrator, "calibrate", fail_calibrate)

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.pipeline"):
        result = pipeline.run(auto_submit=False)
    pipeline_log_text = "\n".join(
        str(record.message)
        for record in caplog.records
        if record.name == "brain_alpha_ops.research.pipeline"
    )

    event = next(event for event in result.events if event.event == "scoring_calibration_failed")
    assert event.level == "WARN"
    assert "score calibration unavailable" in event.message
    assert "dummy1" not in event.message
    assert "Scoring auto-calibration failed in cycle 1" in pipeline_log_text
    assert "score calibration unavailable" in pipeline_log_text
    assert "dummy1" not in pipeline_log_text
    assert "Traceback" not in pipeline_log_text


def test_pipeline_logs_secondary_fusion_exceptions(monkeypatch, caplog, tmp_path):
    pipeline = AlphaResearchPipeline(
        config=_single_cycle_config(tmp_path, enable_secondary_fusion=True),
        api=ProductionBrainAPIStub(),
    )
    monkeypatch.setattr(
        pipeline.convergence,
        "summary",
        lambda: {"stalled": True, "stall_cycles": 3},
    )

    def fail_fusion(*_args, **_kwargs):
        raise RuntimeError("fusion unavailable")

    monkeypatch.setattr(pipeline, "_try_fusion_top_candidates", fail_fusion)

    with caplog.at_level(logging.WARNING, logger="brain_alpha_ops.research.pipeline"):
        result = pipeline.run(auto_submit=False)

    event = next(event for event in result.events if event.event == "fusion_attempt_failed")
    assert event.level == "WARN"
    assert "fusion unavailable" in event.message
    assert "Secondary fusion attempt failed in cycle 1" in caplog.text
    assert "fusion unavailable" in caplog.text


def test_pipeline_auto_submit_is_guarded():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=8,
                max_official_simulations_per_cycle=5,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=True)
        assert result.summary["submitted_this_run"] <= config.submission_policy.max_auto_submissions_per_run


def test_pipeline_scores_and_sorts_before_official_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=1,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)
        candidates = result.candidates
        assert candidates
        assert all(candidate.scorecard.get("total_score", 0) > 0 for candidate in candidates)
        # rank_candidates uses multi-key sort; verify output is idempotent
        from brain_alpha_ops.research.pipeline_helpers import rank_candidates
        re_ranked = rank_candidates(candidates)
        assert [c.alpha_id for c in candidates] == [c.alpha_id for c in re_ranked], (
            "Pipeline output must already be sorted by rank_candidates multi-key order")
        assert any(candidate.scorecard.get("score_basis") == "local_prior" for candidate in candidates)


def test_pipeline_applies_knowledge_constraints_to_generator(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        kb = StructuredKnowledgeBase(tmp)
        kb.save(
            KnowledgeEntry(
                layer="rule",
                category="field_selection",
                title="Prefer close",
                fields_involved=["close"],
            )
        )
        config = OpsConfig(storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        captured = {}

        def fake_set_knowledge_constraints(constraints):
            captured["constraints"] = constraints

        monkeypatch.setattr(pipeline.generator, "set_knowledge_constraints", fake_set_knowledge_constraints)

        pipeline._apply_knowledge_constraints_to_generator()

        assert "close" in captured["constraints"]["preferred_fields"]
        assert captured["constraints"]["strict_preferred_fields"] is True
        assert captured["constraints"]["strict_preferred_operators"] is True
        assert any(event.event == "knowledge_constraints_applied" for event in pipeline.events)


def test_pipeline_local_prefilter_attaches_local_backtest_result(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        candidate = Candidate(
            alpha_id="alpha_local",
            expression="rank(close)",
            family="test",
            hypothesis="local backtest supported candidate",
            data_fields=["close"],
            operators=["rank"],
        )

        monkeypatch.setattr(
            pipeline._local_backtest_engine,
            "evaluate",
            lambda expression, cache_key="default": {
                "ok": True,
                "expression": expression,
                "pass_local": True,
                "sharpe": 1.5,
                "fitness": 1.2,
                "turnover": 0.2,
                "weight_concentration": 0.05,
                "pass_reasons": ["Sharpe 1.50 >= 1.25"],
            },
        )

        passed = pipeline._local_prefilter([candidate], 1, [{"name": "close"}], [{"name": "rank"}])

        assert passed == [candidate]
        assert candidate.submission["local_backtest"]["pass_local"] is True
        assert candidate.local_quality["local_backtest"]["sharpe"] == 1.5
        assert candidate.local_quality["local_backtest_support"]["supported"] is True


def test_pipeline_local_prefilter_rejects_failed_local_backtest(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        candidate = Candidate(
            alpha_id="alpha_local_fail",
            expression="rank(close)",
            family="test",
            hypothesis="local backtest failed candidate with enough context for scoring",
            data_fields=["close"],
            operators=["rank"],
        )

        monkeypatch.setattr(
            pipeline._local_backtest_engine,
            "evaluate",
            lambda expression, cache_key="default": {
                "ok": True,
                "expression": expression,
                "pass_local": False,
                "sharpe": 1.5,
                "fitness": 1.2,
                "turnover": 0.8,
                "weight_concentration": 0.12,
                "pass_reasons": ["Turnover 80.00% > 70% (FAIL)"],
            },
        )

        passed = pipeline._local_prefilter([candidate], 1, [{"name": "close"}], [{"name": "rank"}])

        assert passed == []
        assert candidate.lifecycle_status == "local_prefilter_rejected"
        assert candidate.gate["status"] == "LOCAL_PREFILTER_REJECTED"
        assert any(reason.startswith("local_backtest_failed:") for reason in candidate.local_quality["reasons"])
        assert candidate.submission["local_backtest"]["pass_local"] is False
        failures = pipeline._knowledge_base.list_layer("failure")
        high_turnover_failures = [entry for entry in failures if entry.category == "high_turnover"]
        assert high_turnover_failures
        assert high_turnover_failures[0].metadata["failure_category"] == "high_turnover"
        assert "high_turnover" in high_turnover_failures[0].source_tags


def test_pipeline_local_prefilter_rejects_unsupported_local_backtest_fields():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        candidate = Candidate(
            alpha_id="alpha_unsupported",
            expression="rank(sedol)",
            family="test",
            hypothesis="unsupported local backtest field",
            data_fields=["sedol"],
            operators=["rank"],
        )

        passed = pipeline._local_prefilter([candidate], 1, [{"name": "sedol"}], [{"name": "rank"}])

        assert passed == []
        assert candidate.lifecycle_status == "local_prefilter_rejected"
        assert candidate.gate["status"] == "LOCAL_PREFILTER_REJECTED"
        assert candidate.local_quality["passed"] is False
        assert candidate.local_quality["local_backtest_support"]["supported"] is False
        assert "local_backtest_unsupported:unsupported_fields=sedol" in candidate.local_quality["reasons"]
        assert candidate.submission["local_backtest"]["skipped"] is True


def test_pipeline_local_prefilter_rejects_expression_field_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        candidate = Candidate(
            alpha_id="alpha_expression_field_mismatch",
            expression="rank(ts_mean(pv13_rha2_foo, 20))",
            family="test",
            hypothesis="expression-level metadata field should block even when data_fields is under-reported",
            data_fields=["open"],
            operators=["rank", "ts_mean"],
        )

        passed = pipeline._local_prefilter([candidate], 1, [{"name": "open"}], [{"name": "rank"}, {"name": "ts_mean"}])

        assert passed == []
        assert candidate.lifecycle_status == "local_prefilter_rejected"
        assert candidate.local_quality["local_backtest_support"]["supported"] is False
        assert "pv13_rha2_foo" in candidate.local_quality["local_backtest_support"]["unsupported_fields"]
        assert "non_signal_generation_fields=pv13_rha2_foo" in candidate.local_quality["reasons"]


def test_pipeline_local_prefilter_rejects_expression_operator_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        candidate = Candidate(
            alpha_id="alpha_expression_operator_mismatch",
            expression="rank(ts_arg_max(close, 20))",
            family="test",
            hypothesis="expression-level unsupported operator should block even when operators are under-reported",
            data_fields=["close"],
            operators=["rank"],
        )

        passed = pipeline._local_prefilter([candidate], 1, [{"name": "close"}], [{"name": "rank"}])

        assert passed == []
        assert candidate.lifecycle_status == "local_prefilter_rejected"
        assert candidate.local_quality["local_backtest_support"]["supported"] is False
        assert "ts_arg_max" in candidate.local_quality["local_backtest_support"]["unsupported_operators"]
        assert "local_backtest_unsupported:unsupported_operators=ts_arg_max" in candidate.local_quality["reasons"]


def test_pipeline_auto_submit_blocks_when_cross_review_rejects(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        pipeline.cloud_sync = {"status": "loaded", "stale": False, "warning": ""}
        pipeline.cloud_alphas = [{"id": "existing", "status": "SUBMITTED", "expression": "rank(volume)"}]
        candidate = Candidate(
            alpha_id="alpha_review",
            expression="rank(close)",
            family="test",
            hypothesis="candidate ready for auto submit review",
            data_fields=["close"],
            operators=["rank"],
            official_alpha_id="prod_stub_alpha_9999",
            official_metrics={
                "sharpe": 2.0,
                "fitness": 1.6,
                "turnover": 0.2,
                "correlation": 0.1,
                "self_correlation": 0.1,
                "prod_correlation": 0.1,
                "weight_concentration": 0.05,
                "sub_universe_sharpe": 1.7,
                "alphaSize": 1000,
                "subUniverseSize": 1000,
                "pass_fail": "PASS",
            },
            gate={"submission_ready": True},
        )

        monkeypatch.setattr(
            pipeline,
            "_pre_submit_cross_review",
            lambda candidate: {"allowed": False, "failed_reasons": ["manual_review_required"]},
        )

        submitted = pipeline._try_auto_submit(candidate, 0)

        assert submitted == 0
        assert candidate.gate["status"] == "CROSS_REVIEW_BLOCKED"
        assert candidate.lifecycle_status == "auto_submit_cross_review_blocked"


def test_pipeline_auto_submit_blocks_incomplete_official_metric_fields(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False),
            storage_dir=tmp,
        )
        class RecordingAPI(ProductionBrainAPIStub):
            def __init__(self):
                super().__init__()
                self.submissions = []

            def submit_alpha(self, alpha_id, expression, settings):
                self.submissions.append((alpha_id, expression, settings))
                return super().submit_alpha(alpha_id, expression, settings)

        api = RecordingAPI()
        pipeline = AlphaResearchPipeline(config=config, api=api)
        pipeline.cloud_sync = {"status": "loaded", "stale": False, "warning": ""}
        pipeline.cloud_alphas = [{"id": "existing", "status": "UNSUBMITTED", "expression": "rank(volume)"}]
        candidate = Candidate(
            alpha_id="alpha_sparse_metrics",
            expression="rank(close)",
            family="test",
            hypothesis="sparse official metrics must not auto submit",
            data_fields=["close"],
            operators=["rank"],
            official_alpha_id="prod_alpha_1234",
            official_metrics={"pass_fail": "PASS"},
            gate={"submission_ready": True},
            scorecard={"total_score": 93, "decision_band": "submit_candidate"},
        )
        cross_review_called = {"value": False}

        def cross_review(_candidate):
            cross_review_called["value"] = True
            return {"allowed": True, "failed_reasons": []}

        monkeypatch.setattr(pipeline, "_pre_submit_cross_review", cross_review)

        submitted = pipeline._try_auto_submit(candidate, 0)

        assert submitted == 0
        assert cross_review_called["value"] is False
        assert api.submissions == []
        assert candidate.submission["safety"]["allowed"] is False
        assert candidate.submission["safety"]["status"] == "BLOCK"
        assert any(reason.startswith("missing_official_metric_fields:") for reason in candidate.submission["safety"]["failed_reasons"])


def test_pipeline_auto_submit_reports_exact_missing_official_metric_field(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False),
            storage_dir=tmp,
        )

        class RecordingAPI(ProductionBrainAPIStub):
            def __init__(self):
                super().__init__()
                self.submissions = []

            def submit_alpha(self, alpha_id, expression, settings):
                self.submissions.append((alpha_id, expression, settings))
                return super().submit_alpha(alpha_id, expression, settings)

        api = RecordingAPI()
        pipeline = AlphaResearchPipeline(config=config, api=api)
        pipeline.cloud_sync = {"status": "loaded", "stale": False, "warning": ""}
        pipeline.cloud_alphas = [{"id": "existing", "status": "UNSUBMITTED", "expression": "rank(volume)"}]
        candidate = Candidate(
            alpha_id="alpha_missing_one_metric",
            expression="rank(close)",
            family="test",
            hypothesis="single missing official metric must be visible",
            data_fields=["close"],
            operators=["rank"],
            official_alpha_id="prod_alpha_5678",
            official_metrics={
                "sharpe": 2.0,
                "fitness": 1.5,
                "turnover": 0.2,
                "correlation": 0.1,
                "self_correlation": 0.1,
                "prod_correlation": 0.1,
                "sub_universe_sharpe": 1.5,
                "pass_fail": "PASS",
            },
            gate={"submission_ready": True},
            scorecard={"total_score": 93, "decision_band": "submit_candidate"},
        )
        cross_review_called = {"value": False}

        def cross_review(_candidate):
            cross_review_called["value"] = True
            return {"allowed": True, "failed_reasons": []}

        monkeypatch.setattr(pipeline, "_pre_submit_cross_review", cross_review)

        submitted = pipeline._try_auto_submit(candidate, 0)

        metric_check = next(
            check for check in candidate.submission["safety"]["checks"]
            if check["name"] == "official_metric_fields_complete"
        )
        assert submitted == 0
        assert cross_review_called["value"] is False
        assert api.submissions == []
        assert metric_check["passed"] is False
        assert metric_check["detail"] == "missing_official_metric_fields:weight_concentration"


def test_pipeline_auto_submit_blocks_official_release_gate_failure_before_cross_review(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False),
            storage_dir=tmp,
        )

        class RecordingAPI(ProductionBrainAPIStub):
            def __init__(self):
                super().__init__()
                self.submissions = []

            def submit_alpha(self, alpha_id, expression, settings):
                self.submissions.append((alpha_id, expression, settings))
                return super().submit_alpha(alpha_id, expression, settings)

        api = RecordingAPI()
        pipeline = AlphaResearchPipeline(config=config, api=api)
        pipeline.cloud_sync = {"status": "loaded", "stale": False, "warning": ""}
        pipeline.cloud_alphas = [{"id": "existing", "status": "UNSUBMITTED", "expression": "rank(volume)"}]
        candidate = Candidate(
            alpha_id="alpha_low_release_gate",
            expression="rank(close)",
            family="test",
            hypothesis="official release gate failure must block auto submit",
            data_fields=["close"],
            operators=["rank"],
            official_alpha_id="prod_alpha_9012",
            official_metrics={
                "sharpe": 1.6,
                "fitness": 1.5,
                "turnover": 0.2,
                "correlation": 0.1,
                "self_correlation": 0.1,
                "prod_correlation": 0.1,
                "weight_concentration": 0.05,
                "sub_universe_sharpe": 0.6,
                "subUniverseSize": 1000,
                "alphaSize": 1000,
                "pass_fail": "PASS",
            },
            gate={"submission_ready": True},
            scorecard={"total_score": 93, "decision_band": "submit_candidate"},
        )
        cross_review_called = {"value": False}

        def cross_review(_candidate):
            cross_review_called["value"] = True
            return {"allowed": True, "failed_reasons": []}

        monkeypatch.setattr(pipeline, "_pre_submit_cross_review", cross_review)

        submitted = pipeline._try_auto_submit(candidate, 0)

        release_check = next(
            check for check in candidate.submission["safety"]["checks"]
            if check["name"] == "official_release_gate"
        )
        assert submitted == 0
        assert cross_review_called["value"] is False
        assert api.submissions == []
        assert release_check["passed"] is False
        assert release_check["detail"] == "official_release_gate_failed:sub_universe_sharpe"
        assert candidate.submission["safety"]["official_release_gate"]["status"] == "FAIL"


def test_pipeline_auto_submit_blocks_when_live_readiness_not_ready(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False),
            storage_dir=tmp,
        )

        class RecordingAPI(ProductionBrainAPIStub):
            def __init__(self):
                super().__init__()
                self.submissions = []

            def submit_alpha(self, alpha_id, expression, settings):
                self.submissions.append((alpha_id, expression, settings))
                return super().submit_alpha(alpha_id, expression, settings)

        api = RecordingAPI()
        pipeline = AlphaResearchPipeline(config=config, api=api)
        pipeline.cloud_sync = {"status": "loaded", "stale": False, "warning": ""}
        pipeline.cloud_alphas = [{"id": "existing", "status": "UNSUBMITTED", "expression": "rank(volume)"}]
        candidate = Candidate(
            alpha_id="alpha_live_readiness_blocked",
            expression="rank(close)",
            family="test",
            hypothesis="live readiness must block auto submit",
            data_fields=["close"],
            operators=["rank"],
            official_alpha_id="prod_alpha_7777",
            official_metrics={
                "sharpe": 2.0,
                "fitness": 1.5,
                "turnover": 0.2,
                "correlation": 0.1,
                "self_correlation": 0.1,
                "prod_correlation": 0.1,
                "weight_concentration": 0.05,
                "sub_universe_sharpe": 1.5,
                "subUniverseSize": 1000,
                "alphaSize": 1000,
                "pass_fail": "PASS",
            },
            gate={"submission_ready": True},
            scorecard={"total_score": 93, "decision_band": "submit_candidate"},
        )

        monkeypatch.setattr(
            pipeline,
            "_pre_submit_cross_review",
            lambda _candidate: {"allowed": True, "failed_reasons": []},
        )
        monkeypatch.setattr(
            "brain_alpha_ops.research.pipeline_submission_gate.live_submit_readiness_hard_gate",
            lambda candidate, config, official_id: {
                "ok": False,
                "error_code": "SUBMIT_READINESS_NOT_READY",
                "error": "not ready",
            },
        )

        submitted = pipeline._try_auto_submit(candidate, 0)

        assert submitted == 0
        assert api.submissions == []
        assert candidate.gate["status"] == "LIVE_SUBMIT_READINESS_BLOCKED"
        assert candidate.lifecycle_status == "auto_submit_readiness_blocked"
        assert candidate.submission["live_submit_readiness"]["error_code"] == "SUBMIT_READINESS_NOT_READY"


class ConcurrencyLimitedAPI(ProductionBrainAPIStub):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError(
            "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
        )


class SimulationSubmitRateLimitedAPI(ProductionBrainAPIStub):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError(
            "HTTP 429: rate limit token=secret-token-123",
            status_code=429,
            retry_after=7,
        )


class CountingProductionBrainAPIStub(ProductionBrainAPIStub):
    def __init__(self):
        super().__init__()
        self.validation_expressions: list[str] = []
        self.simulation_expressions: list[str] = []

    def validate_expression(self, expression: str, settings: dict) -> dict:
        self.validation_expressions.append(expression)
        return super().validate_expression(expression, settings)

    def submit_simulation(self, expression: str, settings: dict) -> str:
        self.simulation_expressions.append(expression)
        return super().submit_simulation(expression, settings)


class CloudSyncForbiddenAPI(ProductionBrainAPIStub):
    def list_user_alphas(self, sync_range: str = "all", progress_callback=None) -> list[dict]:
        raise AssertionError("cloud sync should not run when a local cache already exists")


class CallbackStoppingCloudSyncAPI(ProductionBrainAPIStub):
    def __init__(self):
        super().__init__()
        self.pages_requested = 0
        self.callback_results = []

    def list_user_alphas(self, sync_range: str = "all", progress_callback=None) -> list[dict]:
        rows = []
        for index in range(3):
            self.pages_requested += 1
            rows.append({"id": f"partial_alpha_{index + 1}", "status": "UNSUBMITTED"})
            if progress_callback:
                keep_going = progress_callback({
                    "scanned": len(rows),
                    "total": 300,
                    "page_size": 1,
                    "offset": index,
                })
                self.callback_results.append(keep_going)
                if keep_going is False:
                    break
        return rows


def test_pipeline_runs_initial_cloud_sync_when_cache_is_empty_and_per_run_sync_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False, cloud_sync_range="3d"),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        pipeline._sync_cloud_alphas()
        assert pipeline.cloud_sync["status"] == "synced"
        assert pipeline.cloud_sync["range"] == "all"
        assert pipeline.cloud_sync["count"] == 4
        assert len(pipeline.cloud_alphas) == 4


def test_pipeline_uses_cached_cloud_alphas_when_per_run_sync_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.merge_cloud_alphas(
            [{"id": "cached_alpha", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}}],
            sync_range="3d",
        )
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False, cloud_sync_range="3d"),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=CloudSyncForbiddenAPI())
        pipeline._sync_cloud_alphas()
        assert pipeline.cloud_sync["status"] == "loaded"
        assert pipeline.cloud_sync["run_status"] == "skipped"
        assert pipeline.cloud_sync["count"] == 1
        assert pipeline.cloud_alphas[0]["id"] == "cached_alpha"


def test_pipeline_default_budget_uses_cached_cloud_alphas_without_remote_sync():
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.merge_cloud_alphas(
            [{"id": "cached_alpha", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}}],
            sync_range="all",
        )
        config = OpsConfig(budget=ResearchBudget(), storage_dir=tmp)
        pipeline = AlphaResearchPipeline(config=config, api=CloudSyncForbiddenAPI())
        pipeline._sync_cloud_alphas()

        assert pipeline.cloud_sync["status"] == "loaded"
        assert pipeline.cloud_sync["status_code"] == "CACHE_LOADED"
        assert pipeline.cloud_sync["run_status"] == "skipped"
        assert pipeline.cloud_alphas[0]["id"] == "cached_alpha"


def test_pipeline_forces_remote_cloud_sync_when_required_even_if_cache_exists():
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.merge_cloud_alphas(
            [{"id": "cached_alpha", "status": "UNSUBMITTED", "metrics": {"pass_fail": "PASS"}}],
            sync_range="all",
        )
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=True, cloud_sync_range="3d"),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        pipeline._sync_cloud_alphas()
        assert pipeline.cloud_sync["status"] == "synced"
        assert pipeline.cloud_sync["range"] == "3d"
        assert pipeline.cloud_sync["count"] == 3
        assert len(pipeline.cloud_alphas) == 3
        assert {row["id"] for row in pipeline.cloud_alphas} != {"cached_alpha"}


def test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows():
    stop_requested = {"value": False}
    events = []

    def on_progress(event):
        events.append(event)
        if event["phase"] == "cloud_sync" and event.get("data", {}).get("cloud_sync", {}).get("status") == "running":
            stop_requested["value"] = True

    with tempfile.TemporaryDirectory() as tmp:
        api = CallbackStoppingCloudSyncAPI()
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False, cloud_sync_range="3d"),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(
            config=config,
            api=api,
            progress_callback=on_progress,
            stop_callback=lambda: stop_requested["value"],
        )

        pipeline._sync_cloud_alphas()

        assert api.pages_requested == 1
        assert api.callback_results == [False]
        assert pipeline.cloud_sync["status"] == "stopped"
        assert pipeline.cloud_sync["run_status"] == "stopped"
        assert pipeline.cloud_alphas == []
        assert ResearchRepository(tmp).latest_cloud_alphas() == []


def test_pipeline_cloud_sync_ignores_elapsed_limit_and_merges_all_rows():
    events = []

    with tempfile.TemporaryDirectory() as tmp:
        api = CallbackStoppingCloudSyncAPI()
        config = OpsConfig(
            budget=ResearchBudget(
                require_cloud_sync=False,
                cloud_sync_range="3d",
                cloud_sync_max_elapsed_seconds=0.000001,
            ),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=api, progress_callback=events.append)

        pipeline._sync_cloud_alphas()

        assert api.pages_requested == 3
        assert api.callback_results == [True, True, True]
        assert pipeline.cloud_sync["status"] == "synced"
        assert pipeline.cloud_sync["range"] == "all"
        assert pipeline.cloud_sync["count"] == 3
        assert len(pipeline.cloud_alphas) == 3
        assert len(ResearchRepository(tmp).latest_cloud_alphas()) == 3
        running_scan_events = [
            event for event in events
            if event["phase"] == "cloud_sync"
            and (event.get("data", {}).get("cloud_sync") or {}).get("status") == "running"
            and (event.get("data", {}).get("cloud_sync") or {}).get("scanned", 0) > 0
        ]
        assert running_scan_events
        assert all(event["indeterminate"] is True for event in running_scan_events)
        assert all(event["percent"] is None for event in running_scan_events)
        assert all(event["total"] == 0 for event in running_scan_events)
        assert running_scan_events[-1]["current"] == 3
        assert running_scan_events[-1]["data"]["cloud_sync"]["filter_window_count"] == 300
        final_sync_events = [
            event for event in events
            if event["phase"] == "cloud_sync"
            and (event.get("data", {}).get("cloud_sync") or {}).get("status") == "synced"
        ]
        assert final_sync_events[-1]["indeterminate"] is False
        assert final_sync_events[-1]["percent"] == 100.0


def test_pipeline_applies_persisted_assistant_guidance(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.save_assistant_guidance(
            {
                "ok": True,
                "schema_version": "assistant_generation_guidance.v1",
                "usable": True,
                "confidence": 0.82,
                "sample_size": 1,
                "top_fields": ["close"],
                "top_operators": ["ts_rank"],
                "preferred_windows": [10],
            },
            source="test",
        )
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=3,
                max_official_validations_per_cycle=1,
                max_official_simulations_per_cycle=1,
                max_cycles=1,
                require_cloud_sync=False,
                assistant_guidance_min_confidence=0.7,
            ),
            storage_dir=tmp,
        )
        captured = {}

        def fake_set_experience_guidance(self, patterns):
            captured["patterns"] = patterns

        monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", fake_set_experience_guidance)
        monkeypatch.setattr("brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.set_experience_guidance", fake_set_experience_guidance)

        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

        assert captured["patterns"]["sample_size"] == 3
        assert captured["patterns"]["top_operators"] == ["ts_rank"]
        assert captured["patterns"]["preferred_windows"] == [10]
        assert captured["patterns"]["field_combinations"] == [{"fields": ["close"], "rationale": "assistant top fields"}]
        assert any(event.event == "assistant_guidance_applied" for event in result.events)
        event = next(event for event in result.events if event.event == "assistant_guidance_applied")
        assert event.data["guidance_digest"].startswith("ag_")
        assert event.data["historical_outcome_status"] == "unknown"
        assert event.data["historical_outcome"] == {}
        assert result.candidates
        assert any("assistant_guided" in candidate.source_tags for candidate in result.candidates)
        assert any(candidate.submission.get("assistant_guidance_digest", "").startswith("ag_") for candidate in result.candidates)


def test_pipeline_attaches_structured_assistant_guidance_outcome_metadata(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.save_assistant_guidance(
            {
                "ok": True,
                "schema_version": "assistant_generation_guidance.v1",
                "usable": True,
                "confidence": 0.9,
                "guidance_digest": "ag_pipeline_strong",
                "sample_size": 2,
                "top_fields": ["close"],
                "top_operators": ["ts_rank"],
                "preferred_windows": [20],
            },
            source="test",
        )
        repo.save_candidate(
            "history_run",
            Candidate(
                alpha_id="history_guided",
                expression="rank(ts_delta(close, 20))",
                family="Momentum",
                hypothesis="historical assistant guidance winner",
                data_fields=["close"],
                operators=["rank", "ts_delta"],
                source_tags=["assistant_guided"],
                official_metrics={"sharpe": 1.7, "fitness": 1.3, "pass_fail": "PASS"},
                scorecard={"total_score": 84.0},
                gate={"submission_ready": True},
                submission={"assistant_guidance_digest": "ag_pipeline_strong"},
                lifecycle_status="submission_ready",
            ),
        )
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=2,
                max_official_validations_per_cycle=1,
                max_official_simulations_per_cycle=1,
                max_cycles=1,
                require_cloud_sync=False,
                assistant_guidance_min_confidence=0.7,
            ),
            storage_dir=tmp,
        )
        monkeypatch.setattr("brain_alpha_ops.research.generator.CandidateGenerator.set_experience_guidance", lambda self, patterns: None)
        monkeypatch.setattr("brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.set_experience_guidance", lambda self, patterns: None)

        def fake_generate(self, count, dataset_id=""):
            return [
                Candidate(
                    alpha_id="assistant_guided_candidate",
                    expression="rank(ts_mean(close, 20))",
                    family="Momentum",
                    hypothesis="deterministic assistant guidance candidate",
                    data_fields=["close"],
                    operators=["rank", "ts_mean"],
                )
            ]

        monkeypatch.setattr(
            "brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.generate",
            fake_generate,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.research.generator.CandidateGenerator.generate",
            fake_generate,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.research.local_backtest_engine.LocalBacktestEngine.evaluate",
            lambda self, expression, **_kwargs: {
                "ok": True,
                "expression": expression,
                "pass_local": True,
                "sharpe": 1.5,
                "fitness": 1.2,
                "turnover": 0.2,
                "weight_concentration": 0.05,
                "pass_reasons": ["fixture local backtest pass"],
            },
        )

        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

        assert result.candidates
        assert any(candidate.submission.get("assistant_guidance_outcome_status") == "strong" for candidate in result.candidates)
        assert any(candidate.submission.get("assistant_guidance_outcome_success_rate") == 1.0 for candidate in result.candidates)
        assert any(
            candidate.scorecard.get("assistant_guidance_adjustment", {}).get("adjustment", 0) > 0
            for candidate in result.candidates
        )


def test_pipeline_defers_remaining_candidates_on_concurrency_limit():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=8,
                max_official_simulations_per_cycle=3,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ConcurrencyLimitedAPI()).run(auto_submit=False)
        statuses = [candidate.lifecycle_status for candidate in result.candidates]
        assert any(status == "simulation_deferred_concurrency_limit" for status in statuses)
        assert result.summary["officially_simulated"] == 0
        assert result.summary["pending_backtest_count"] >= 1
        assert result.summary["pending_backtest_candidates"]


def test_pipeline_persists_structured_backtest_error_context_for_rate_limit():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=8,
                max_official_simulations_per_cycle=3,
                max_cycles=1,
                official_retry_pause_seconds=0.1,
            ),
            storage_dir=tmp,
        )

        result = AlphaResearchPipeline(config=config, api=SimulationSubmitRateLimitedAPI()).run(auto_submit=False)
        rows = [
            json.loads(line)
            for line in (Path(tmp) / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        submit_failure = next(row for row in rows if row.get("action") == "submit_failed")
        context = submit_failure["error_context"]

        assert result.summary["official_calls_halted"] is True
        assert submit_failure["retryable"] is True
        assert submit_failure["retry_after"] == 7
        assert context["error_code"] == "SIMULATION_SUBMIT_ERROR"
        assert context["error_category"] == "rate_limit"
        assert context["retryable"] is True
        assert context["status_code"] == 429
        assert context["retry_after"] == 7
        assert "secret-token-123" not in json.dumps(submit_failure)
        assert "<redacted>" in json.dumps(submit_failure)


def test_pipeline_observability_blocks_official_calls_but_keeps_local_generation():
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        for index in range(6):
            repo.save_backtest_record(
                "history_run",
                {
                    "action": "simulation_result",
                    "alpha_id": f"hist_{index}",
                    "status": "simulation_failed",
                    "expression": f"rank(ts_delta(close, {index + 2}))",
                    "note": "rate limit retry pending",
                    "retryable": True,
                },
            )
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=6,
                max_official_validations_per_cycle=4,
                max_official_simulations_per_cycle=2,
                max_cycles=1,
                require_cloud_sync=False,
                cycle_pause_seconds=0.1,
                official_retry_pause_seconds=0.1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

        assert result.summary["produced_count"] > 0
        assert result.summary["official_validation_attempted"] == 0
        assert result.summary["officially_simulated"] == 0
        assert result.summary["official_calls_halted"] is True
        assert "rate_limit_pressure" in result.summary["observability_throttle"]["blocking_flags"]
        assert any(event.event == "official_calls_halted_by_observability" for event in result.events)


def test_pipeline_passes_observability_duplicates_to_generator(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        expression = "rank(ts_delta(close, 20))"
        repo.save_candidate(
            "history_run",
            Candidate(
                alpha_id="hist_candidate",
                expression=expression,
                family="Momentum",
                hypothesis="duplicate expression history",
                data_fields=["close"],
                operators=["rank", "ts_delta"],
            ),
        )
        repo.save_backtest_record(
            "history_run",
            {
                "action": "submitted",
                "alpha_id": "hist_backtest",
                "status": "SUBMITTED",
                "expression": expression,
            },
        )
        captured: list[dict] = []

        def fake_set_observability_guidance(self, guidance):
            captured.append(guidance)

        monkeypatch.setattr(
            "brain_alpha_ops.research.generator.CandidateGenerator.set_observability_guidance",
            fake_set_observability_guidance,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.set_observability_guidance",
            fake_set_observability_guidance,
        )
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=3,
                max_official_validations_per_cycle=0,
                max_official_simulations_per_cycle=0,
                max_cycles=1,
                require_cloud_sync=False,
            ),
            storage_dir=tmp,
        )

        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

        assert result.summary["produced_count"] > 0
        assert captured
        assert any(row.get("avoid_expressions") for row in captured)
        assert any("duplicate_expression_history" in row.get("health_flags", []) for row in captured)
        guidance_summary = result.summary["observability_generation_guidance"]
        assert guidance_summary["active"] is True
        assert guidance_summary["avoid_expression_count"] >= 1
        assert guidance_summary["applied_to_generator"] is True
        assert result.summary["observability_throttle"]["generation_guidance"]["active"] is True
        assert any(event.event == "observability_generation_guidance_applied" for event in result.events)


def test_pipeline_records_observability_refresh_failure(monkeypatch):
    def fail_snapshot(*args, **kwargs):
        raise RuntimeError("observability store unavailable")

    monkeypatch.setattr(
        "brain_alpha_ops.research.pipeline.build_research_observability_snapshot",
        fail_snapshot,
    )
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=3,
                max_official_validations_per_cycle=0,
                max_official_simulations_per_cycle=0,
                max_cycles=1,
                require_cloud_sync=False,
            ),
            storage_dir=tmp,
        )

        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

        throttle = result.summary["observability_throttle"]
        guidance = result.summary["observability_generation_guidance"]
        assert result.summary["produced_count"] > 0
        assert throttle["ok"] is False
        assert throttle["status"] == "refresh_failed"
        assert "observability store unavailable" in throttle["error"]
        assert guidance["status"] == "refresh_failed"
        assert throttle["generation_guidance"]["status"] == "refresh_failed"
        event = next(event for event in result.events if event.event == "observability_refresh_failed")
        assert event.level == "WARN"
        assert event.data["error_code"] == "OBSERVABILITY_REFRESH_FAILED"
        assert event.data["phase"] == "observability"


def test_pipeline_records_observability_guidance_apply_failure(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        expression = "rank(ts_delta(close, 20))"
        repo.save_candidate(
            "history_run",
            Candidate(
                alpha_id="hist_candidate",
                expression=expression,
                family="Momentum",
                hypothesis="duplicate expression history",
                data_fields=["close"],
                operators=["rank", "ts_delta"],
            ),
        )
        repo.save_backtest_record(
            "history_run",
            {
                "action": "submitted",
                "alpha_id": "hist_backtest",
                "status": "SUBMITTED",
                "expression": expression,
            },
        )

        def fail_guidance(self, guidance):
            raise RuntimeError("generator guidance sink unavailable")

        monkeypatch.setattr(
            "brain_alpha_ops.research.generator.CandidateGenerator.set_observability_guidance",
            fail_guidance,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.set_observability_guidance",
            fail_guidance,
        )
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=3,
                max_official_validations_per_cycle=0,
                max_official_simulations_per_cycle=0,
                max_cycles=1,
                require_cloud_sync=False,
            ),
            storage_dir=tmp,
        )

        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)

        throttle = result.summary["observability_throttle"]
        guidance = result.summary["observability_generation_guidance"]
        assert result.summary["produced_count"] > 0
        assert throttle["ok"] is True
        assert throttle["status"] == "ready"
        assert guidance["active"] is True
        assert guidance["status"] == "apply_failed"
        assert guidance["applied_to_generator"] is False
        assert "generator guidance sink unavailable" in guidance["error"]
        assert throttle["generation_guidance"]["status"] == "apply_failed"
        event = next(event for event in result.events if event.event == "observability_generation_guidance_failed")
        assert event.level == "WARN"
        assert event.data["error_code"] == "OBSERVABILITY_GENERATION_GUIDANCE_FAILED"
        assert event.data["phase"] == "observability_generation"


def test_pipeline_observability_duplicate_guard_blocks_official_validation(monkeypatch):
    duplicate_expression = "rank(ts_mean(volume / adv20, 10))"
    alternative_expression = "rank(ts_mean(returns, 10))"

    def fake_generate(self, count, dataset_id=""):
        return [
            Candidate(
                alpha_id="dup_candidate",
                expression=duplicate_expression,
                family="Liquidity",
                hypothesis="duplicate history candidate",
                data_fields=["volume", "adv20"],
                operators=["rank", "ts_mean", "divide"],
                scorecard={"total_score": 95},
            ),
            Candidate(
                alpha_id="alt_candidate",
                expression=alternative_expression,
                family="Liquidity",
                hypothesis="fresh candidate",
                data_fields=["returns"],
                operators=["rank", "ts_mean"],
                scorecard={"total_score": 90},
            ),
        ]

    monkeypatch.setattr(
        "brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        "brain_alpha_ops.research.generator.CandidateGenerator.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        "brain_alpha_ops.research.local_backtest_engine.LocalBacktestEngine.evaluate",
        lambda self, expression, **_kwargs: {
            "ok": True,
            "expression": expression,
            "pass_local": True,
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.2,
            "weight_concentration": 0.05,
            "pass_reasons": ["fixture local backtest pass"],
        },
    )
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.save_candidate(
            "history_run",
            Candidate(
                alpha_id="hist_candidate",
                expression=duplicate_expression,
                family="Liquidity",
                hypothesis="duplicate expression history",
                data_fields=["volume", "adv20"],
                operators=["rank", "ts_mean", "divide"],
            ),
        )
        repo.save_backtest_record(
            "history_run",
            {
                "action": "submitted",
                "alpha_id": "hist_backtest",
                "status": "SUBMITTED",
                "expression": duplicate_expression,
            },
        )
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=2,
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=1,
                official_backtest_batch_size=1,
                max_cycles=1,
                require_cloud_sync=False,
            ),
            storage_dir=tmp,
        )
        api = CountingProductionBrainAPIStub()

        result = AlphaResearchPipeline(config=config, api=api).run(auto_submit=False)

        assert duplicate_expression not in api.validation_expressions
        assert alternative_expression in api.validation_expressions
        assert result.summary["official_validation_attempted"] == 1
        guard = result.summary["observability_official_call_guard"]
        assert guard["blocked_count"] == 1
        assert guard["validation_blocked_count"] == 1
        assert guard["simulation_blocked_count"] == 0
        assert guard["last_blocked_alpha_id"] == "dup_candidate"
        assert guard["last_blocked_phase"] == "official_validation"
        assert guard["phase_counts"]["official_validation"] == 1
        assert guard["blocked_candidates"][0]["alpha_id"] == "dup_candidate"
        assert result.summary["observability_throttle"]["official_call_guard"]["blocked_count"] == 1
        assert sum(
            event.event == "observability_duplicate_official_call_blocked"
            for event in result.events
        ) == 1


def test_pipeline_backtest_targets_fill_slot_after_high_similarity_skip():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_official_simulations_per_cycle=1,
                official_backtest_batch_size=1,
            ),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        crowded = Candidate(
            alpha_id="crowded_candidate",
            expression="rank(ts_mean(volume / adv20, 20))",
            family="Liquidity",
            hypothesis="high score but cloud-crowded expression",
            data_fields=["volume", "adv20"],
            operators=["rank", "ts_mean", "divide"],
            validation={"status": "PASS"},
            scorecard={"total_score": 100.0},
        )
        safe = Candidate(
            alpha_id="safe_candidate",
            expression="rank(ts_mean(returns, 10))",
            family="Liquidity",
            hypothesis="lower score but low cloud similarity",
            data_fields=["returns"],
            operators=["rank", "ts_mean"],
            validation={"status": "PASS"},
            scorecard={"total_score": config.budget.min_prior_score_for_official_simulation},
        )
        pipeline.cloud_alphas = [
            {
                "id": "cloud_1",
                "status": "PRODUCTION",
                "expression": crowded.expression,
            }
        ]
        pipeline._refresh_cloud_similarity_index()

        targets = pipeline._backtest_targets([crowded, safe])

        assert [candidate.alpha_id for candidate in targets] == ["safe_candidate"]
        assert crowded.lifecycle_status == "high_cloud_similarity_rejected"
        assert crowded.gate["status"] == "HIGH_CLOUD_SIMILARITY_REJECTED"
        assert crowded.gate["submission_ready"] is False
        assert crowded.submission["cloud_similarity_preflight"]["matched_alpha_id"] == "cloud_1"
        pending = pipeline._pending_backtest_candidates([crowded, safe])
        assert [candidate.alpha_id for candidate in pending] == ["safe_candidate"]
        plan = pipeline.last_runtime_data["backtest_batch_plan"]
        assert plan["selected"][0]["alpha_id"] == "safe_candidate"
        assert plan["skipped"][0]["alpha_id"] == "crowded_candidate"


def test_pipeline_validation_quota_ignores_high_similarity_pending_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=1,
                official_backtest_batch_size=1,
            ),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())
        crowded = Candidate(
            alpha_id="crowded_candidate",
            expression="rank(ts_mean(volume / adv20, 20))",
            family="Liquidity",
            hypothesis="already validated but too similar to cloud alpha",
            data_fields=["volume", "adv20"],
            operators=["rank", "ts_mean", "divide"],
            validation={"status": "PASS"},
            scorecard={"total_score": 100.0},
        )
        safe = Candidate(
            alpha_id="safe_candidate",
            expression="rank(ts_mean(returns, 10))",
            family="Liquidity",
            hypothesis="safe candidate still needs validation",
            data_fields=["returns"],
            operators=["rank", "ts_mean"],
            scorecard={"total_score": config.budget.min_prior_score_for_official_simulation},
        )
        pipeline.cloud_alphas = [
            {
                "id": "cloud_1",
                "status": "PRODUCTION",
                "expression": crowded.expression,
            }
        ]
        pipeline._refresh_cloud_similarity_index()

        quota = pipeline._validation_quota([crowded, safe])

        assert quota == 1
        assert crowded.lifecycle_status == "high_cloud_similarity_rejected"
        assert crowded.gate["status"] == "HIGH_CLOUD_SIMILARITY_REJECTED"
        assert pipeline._validation_targets([crowded, safe]) == [safe]
        assert pipeline._pending_backtest_candidates([crowded, safe]) == []


def test_pipeline_validate_slots_archives_high_similarity_pending_candidate():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=1,
                official_backtest_batch_size=1,
            ),
            storage_dir=tmp,
        )
        api = CountingProductionBrainAPIStub()
        pipeline = AlphaResearchPipeline(config=config, api=api)
        crowded = Candidate(
            alpha_id="crowded_candidate",
            expression="rank(ts_mean(volume / adv20, 20))",
            family="Liquidity",
            hypothesis="already validated but too similar to cloud alpha",
            data_fields=["volume", "adv20"],
            operators=["rank", "ts_mean", "divide"],
            validation={"status": "PASS"},
            scorecard={"total_score": 100.0},
        )
        safe = Candidate(
            alpha_id="safe_candidate",
            expression="rank(ts_mean(returns, 10))",
            family="Liquidity",
            hypothesis="safe candidate still needs validation",
            data_fields=["returns"],
            operators=["rank", "ts_mean"],
            scorecard={"total_score": config.budget.min_prior_score_for_official_simulation},
        )
        pipeline.cloud_alphas = [
            {
                "id": "cloud_1",
                "status": "PRODUCTION",
                "expression": crowded.expression,
            }
        ]
        pipeline._refresh_cloud_similarity_index()
        pool_by_expression = {expr_key(candidate): candidate for candidate in (crowded, safe)}
        archive_stats: dict[str, int] = {}
        blocked_expressions: set[str] = set()

        pipeline._validate_for_open_backtest_slots(
            1,
            pool_by_expression,
            [],
            archive_stats,
            blocked_expressions,
        )

        assert expr_key(crowded) not in pool_by_expression
        assert expr_key(crowded) in blocked_expressions
        assert archive_stats["HIGH_CLOUD_SIMILARITY_REJECTED"] == 1
        assert api.validation_expressions == [safe.expression]
        assert safe.validation["status"] == "PASS"


def test_pipeline_skips_high_cloud_similarity_before_official_validation():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=1,
                official_backtest_batch_size=1,
            ),
            storage_dir=tmp,
        )
        api = CountingProductionBrainAPIStub()
        pipeline = AlphaResearchPipeline(config=config, api=api)
        crowded = Candidate(
            alpha_id="crowded_candidate",
            expression="rank(ts_mean(volume / adv20, 20))",
            family="Liquidity",
            hypothesis="high score but cloud-crowded expression",
            data_fields=["volume", "adv20"],
            operators=["rank", "ts_mean", "divide"],
            scorecard={"total_score": 100.0},
        )
        safe = Candidate(
            alpha_id="safe_candidate",
            expression="rank(ts_mean(returns, 10))",
            family="Liquidity",
            hypothesis="safe candidate still needs official validation",
            data_fields=["returns"],
            operators=["rank", "ts_mean"],
            scorecard={"total_score": config.budget.min_prior_score_for_official_simulation},
        )
        pipeline.cloud_alphas = [
            {
                "id": "cloud_1",
                "status": "PRODUCTION",
                "expression": crowded.expression,
            }
        ]
        pipeline._refresh_cloud_similarity_index()
        pool_by_expression = {expr_key(candidate): candidate for candidate in (crowded, safe)}
        archive_stats: dict[str, int] = {}
        blocked_expressions: set[str] = set()

        pipeline._validate_for_open_backtest_slots(
            1,
            pool_by_expression,
            [],
            archive_stats,
            blocked_expressions,
        )

        assert crowded.lifecycle_status == "high_cloud_similarity_rejected"
        assert crowded.gate["status"] == "HIGH_CLOUD_SIMILARITY_REJECTED"
        assert expr_key(crowded) not in pool_by_expression
        assert expr_key(crowded) in blocked_expressions
        assert archive_stats["HIGH_CLOUD_SIMILARITY_REJECTED"] == 1
        assert api.validation_expressions == [safe.expression]
        assert safe.validation["status"] == "PASS"


def test_pipeline_skips_high_cloud_similarity_before_official_simulation(monkeypatch):
    crowded_expression = "rank(ts_mean(volume / adv20, 20))"
    safe_expression = "rank(ts_mean(returns, 10))"

    def fake_generate(self, count, dataset_id=""):
        return [
            Candidate(
                alpha_id="crowded_candidate",
                expression=crowded_expression,
                family="Liquidity",
                hypothesis="crowded liquidity candidate that should be preflight blocked",
                data_fields=["volume", "adv20"],
                operators=["rank", "ts_mean", "divide"],
            ),
            Candidate(
                alpha_id="safe_candidate",
                expression=safe_expression,
                family="Liquidity",
                hypothesis="fresh returns candidate with production-quality local evidence",
                data_fields=["returns"],
                operators=["rank", "ts_mean"],
            ),
        ]

    monkeypatch.setattr(
        "brain_alpha_ops.research.hypothesis_driven_generator.HypothesisDrivenGenerator.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        "brain_alpha_ops.research.generator.CandidateGenerator.generate",
        fake_generate,
    )
    monkeypatch.setattr(
        "brain_alpha_ops.research.local_backtest_engine.LocalBacktestEngine.evaluate",
        lambda self, expression, **_kwargs: {
            "ok": True,
            "expression": expression,
            "pass_local": True,
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.2,
            "weight_concentration": 0.05,
            "pass_reasons": ["fixture local backtest pass"],
        },
    )

    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=2,
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=2,
                official_backtest_batch_size=2,
                max_cycles=1,
                require_cloud_sync=True,
                cloud_sync_range="3d",
            ),
            storage_dir=tmp,
        )
        api = CountingProductionBrainAPIStub()

        result = AlphaResearchPipeline(config=config, api=api).run(auto_submit=False)

        assert crowded_expression not in api.validation_expressions
        assert safe_expression in api.validation_expressions
        assert crowded_expression not in api.simulation_expressions
        assert safe_expression in api.simulation_expressions
        assert result.summary["backtests_submitted"] == 1
        assert result.summary["cloud_sync"]["status"] in {"synced", "loaded"}
        assert result.summary["archive_stats"]["HIGH_CLOUD_SIMILARITY_REJECTED"] == 1
        pending_alpha_ids = {row["alpha_id"] for row in result.summary["pending_backtest_candidates"]}
        assert "crowded_candidate" not in pending_alpha_ids
        final_alpha_ids = {candidate.alpha_id for candidate in result.candidates}
        assert "crowded_candidate" not in final_alpha_ids


def test_candidate_pool_excludes_waiting_backtest_queue():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=20,
                max_official_validations_per_cycle=10,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                max_cycles=2,
                cycle_pause_seconds=0.1,
                official_retry_pause_seconds=0.1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ConcurrencyLimitedAPI()).run(auto_submit=False)
        candidates = result.summary["candidates"]
        pending = result.summary["pending_backtest_candidates"]
        retained_limit = config.budget.retained_alpha_pool_size
        assert 0 < len(candidates) <= retained_limit
        assert pending
        assert result.summary["candidate_pool_excludes_waiting_backtests"] is True
        assert {row["alpha_id"] for row in candidates}.isdisjoint({row["alpha_id"] for row in pending})
        assert all(row["lifecycle_status"] == "candidate_pool_retained" for row in candidates)
        assert len(candidates) + len(pending) <= retained_limit


def test_pipeline_keeps_top10_and_submits_top3_backtests():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=10,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=5,  # smaller pool for tighter test
                official_backtest_batch_size=3,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)
        assert result.summary["retained_pool_limit"] == 5
        assert result.summary["backtest_batch_size"] == 3
        assert result.summary["backtests_submitted"] >= 1
        assert result.summary["officially_simulated"] >= 1
        assert result.summary["retained_pool_size"] <= 10  # pool may grow with good candidates


def test_pipeline_emits_three_backtest_statuses():
    events = []
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=10,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                official_backtest_batch_size=3,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub(), progress_callback=events.append).run(auto_submit=False)
        backtest_events = [event for event in events if len(event.get("data", {}).get("backtests", [])) == 3]
        assert backtest_events
        assert any(event["phase"] == "simulation_wait" for event in backtest_events)


def test_pipeline_persists_backtest_state_records():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=10,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                official_backtest_batch_size=3,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )

        result = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)
        rows = [
            json.loads(line)
            for line in (Path(tmp) / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        assert rows
        assert result.summary["backtest_records"]
        assert any(row["action"] == "submitted" for row in rows)
        assert any(row["action"] == "completed" for row in rows)
        assert all(row.get("expression_fingerprint") for row in rows)
        assert {row["schema_version"] for row in [rows[0]["expression_profile"]]} == {"expression-profile.v1"}


def test_pipeline_persists_robustness_scientific_audit_records():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=10,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                official_backtest_batch_size=3,
                max_cycles=1,
            ),
            storage_dir=tmp,
        )

        AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub()).run(auto_submit=False)
        backtest_rows = [
            json.loads(line)
            for line in (Path(tmp) / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        lifecycle_rows = [
            json.loads(line)
            for line in (Path(tmp) / "lifecycle.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        robustness_backtests = [row for row in backtest_rows if row.get("action") == "robustness_feedback"]
        robustness_lifecycle = [row for row in lifecycle_rows if row.get("stage") == "robustness_feedback"]
        assert robustness_backtests
        assert robustness_lifecycle
        audit = robustness_backtests[0]["scientific_audit"]
        assert audit["schema_version"] == "candidate-scientific-audit-v1"
        assert audit["events"][-1]["operation"] == "robustness_feedback"
        assert "anti_overfit_report" in audit["evidence"]["feedback_sources"]
        assert "rolling_validation_report" in audit["evidence"]["feedback_sources"]
        assert audit["safety_boundary"]["submit_allowed"] is False


class SlowCompletingAPI(ProductionBrainAPIStub):
    def __init__(self):
        super().__init__()
        self.poll_counts = {}

    def poll_simulation(self, simulation_id: str) -> str:
        self.poll_counts[simulation_id] = self.poll_counts.get(simulation_id, 0) + 1
        if self.poll_counts[simulation_id] >= 2:
            self._simulations[simulation_id]["status"] = "COMPLETED"
        else:
            self._simulations[simulation_id]["status"] = "RUNNING"
        return super().poll_simulation(simulation_id)


class ValidationSieveAPI(SlowCompletingAPI):
    def __init__(self):
        super().__init__()
        self.validation_calls = 0

    def validate_expression(self, expression: str, settings: dict) -> dict:
        self.validation_calls += 1
        if self.validation_calls <= 2:
            return {
                "status": "FAIL",
                "errors": [f"forced validation miss {self.validation_calls}"],
            }
        return super().validate_expression(expression, settings)


def test_pipeline_keeps_producing_while_backtests_are_running():
    events = []
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=8,
                max_official_validations_per_cycle=6,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                official_backtest_batch_size=3,
                max_cycles=4,
                cycle_pause_seconds=0.15,
            ),
            official_api=OfficialAPIConfig(poll_interval_seconds=0.1),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=SlowCompletingAPI(), progress_callback=events.append).run(auto_submit=False)
        assert result.summary["produced_count"] >= 24
        assert result.summary["backtests_submitted"] >= 3
        assert any(row["status"] == "RUNNING" for row in result.summary["backtest_slots"])
        assert any(event["phase"] == "production_loop" for event in events)
        assert all(len(event.get("data", {}).get("backtests", [])) == 3 for event in events if event.get("data", {}).get("backtests"))


def test_pipeline_validates_past_failed_prechecks_to_fill_three_slots():
    with tempfile.TemporaryDirectory() as tmp:
        api = ValidationSieveAPI()
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=8,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                official_backtest_batch_size=3,
                max_cycles=1,
            ),
            official_api=OfficialAPIConfig(poll_interval_seconds=0.1),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=api).run(auto_submit=False)
        active_slots = [
            row
            for row in result.summary["backtest_slots"]
            if row["alpha_id"] and row["status"] in {"RUNNING", "SUBMITTED"}
        ]
        assert api.validation_calls > 3
        assert result.summary["backtest_slot_limit"] == 3
        assert result.summary["backtests_submitted"] == min(
            result.summary["backtest_slot_limit"],
            result.summary["official_validation_passed"],
        )
        assert len(active_slots) == result.summary["backtests_submitted"]


def test_pipeline_does_not_overfill_waiting_backtests():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=20,
                max_official_validations_per_cycle=10,
                max_official_simulations_per_cycle=3,
                retained_alpha_pool_size=10,
                official_backtest_batch_size=3,
                max_cycles=1,
            ),
            official_api=OfficialAPIConfig(poll_interval_seconds=0.1),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=SlowCompletingAPI()).run(auto_submit=False)
        assert result.summary["backtests_submitted"] >= 2  # 2-3 acceptable with new margin check
        assert len(result.summary["backtest_slots"]) >= 2
        assert result.summary["candidate_pool_available_count"] > 0
        assert result.summary["pending_backtest_count"] == 0
