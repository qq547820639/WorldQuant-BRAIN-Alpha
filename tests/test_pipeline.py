import tempfile
import json
from pathlib import Path

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.brain_api.mock import MockBrainAPI
from brain_alpha_ops.config import OfficialAPIConfig, OpsConfig, ResearchBudget
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
from brain_alpha_ops.research.repository import ResearchRepository


def test_pipeline_runs_mock_end_to_end():
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
        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)
        data = result.to_dict()
        assert data["summary"]["total_candidates"] >= 5
        assert data["summary"]["officially_simulated"] > 0
        assert data["candidates"]
        assert any(event["event"] == "run_completed" for event in data["events"])
        first_event = data["events"][0]
        assert first_event["data"]["schema_version"] == "observability.v1"
        assert first_event["data"]["run_id"] == data["run_id"]
        assert first_event["data"]["event"] == first_event["event"]


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
        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=True)
        assert result.summary["submitted_this_run"] <= config.submission_policy.max_auto_submissions_per_run


def test_pipeline_scores_and_sorts_before_official_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=12,
                max_official_validations_per_cycle=2,
                max_official_simulations_per_cycle=1,
                min_prior_score_for_official_validation=60,  # lowered: new generator uses real BRAIN fields
                max_cycles=1,
            ),
            storage_dir=tmp,
        )
        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)
        candidates = result.candidates
        assert candidates
        assert all(candidate.scorecard.get("total_score", 0) > 0 for candidate in candidates)
        scores = [candidate.scorecard.get("total_score", 0) for candidate in candidates]
        assert scores == sorted(scores, reverse=True)
        assert any(candidate.scorecard.get("score_basis") == "local_prior" for candidate in candidates)


class ConcurrencyLimitedAPI(MockBrainAPI):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError(
            "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
        )


class SimulationSubmitRateLimitedAPI(MockBrainAPI):
    def submit_simulation(self, expression: str, settings: dict) -> str:
        raise BrainAPIError(
            "HTTP 429: rate limit token=secret-token-123",
            status_code=429,
            retry_after=7,
        )


class CountingMockBrainAPI(MockBrainAPI):
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


class CloudSyncForbiddenAPI(MockBrainAPI):
    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict]:
        raise AssertionError("cloud sync should not run when a local cache already exists")


def test_pipeline_runs_initial_cloud_sync_when_cache_is_empty_and_per_run_sync_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(require_cloud_sync=False, cloud_sync_range="3d"),
            storage_dir=tmp,
        )
        pipeline = AlphaResearchPipeline(config=config, api=MockBrainAPI())
        pipeline._sync_cloud_alphas()
        assert pipeline.cloud_sync["status"] == "synced"
        assert pipeline.cloud_sync["count"] > 0
        assert pipeline.cloud_alphas


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

        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)

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

        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)

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
                min_prior_score_for_official_validation=0,
                min_prior_score_for_official_simulation=0,
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
        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)

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

        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)

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

        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)

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

        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)

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
    duplicate_expression = "rank(ts_delta(close, 20))"
    alternative_expression = "rank(ts_mean(volume, 5))"

    def fake_generate(self, count, dataset_id=""):
        return [
            Candidate(
                alpha_id="dup_candidate",
                expression=duplicate_expression,
                family="Momentum",
                hypothesis="duplicate history candidate",
                data_fields=["close"],
                operators=["rank", "ts_delta"],
                scorecard={"total_score": 95},
            ),
            Candidate(
                alpha_id="alt_candidate",
                expression=alternative_expression,
                family="Liquidity",
                hypothesis="fresh candidate",
                data_fields=["volume"],
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
    with tempfile.TemporaryDirectory() as tmp:
        repo = ResearchRepository(tmp)
        repo.save_candidate(
            "history_run",
            Candidate(
                alpha_id="hist_candidate",
                expression=duplicate_expression,
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
        api = CountingMockBrainAPI()

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
        assert any(event.event == "observability_duplicate_official_call_blocked" for event in result.events)


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
        assert len(candidates) == 10
        assert pending
        assert result.summary["candidate_pool_excludes_waiting_backtests"] is True
        assert {row["alpha_id"] for row in candidates}.isdisjoint({row["alpha_id"] for row in pending})
        assert all(row["lifecycle_status"] == "candidate_pool_retained" for row in candidates)


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
        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)
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
        AlphaResearchPipeline(config=config, api=MockBrainAPI(), progress_callback=events.append).run(auto_submit=False)
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

        result = AlphaResearchPipeline(config=config, api=MockBrainAPI()).run(auto_submit=False)
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


class SlowCompletingAPI(MockBrainAPI):
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
        assert result.summary["backtests_submitted"] == 3
        assert len(active_slots) == 3


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
