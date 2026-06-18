"""Tests for per-candidate BRAIN simulation service."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import QualityThresholds, ScoringConfig
from brain_alpha_ops.web_candidates.simulation_state import candidate_update_row
from brain_alpha_ops.web_candidates.simulation import (
    _active_account_simulation_cooldown,
    _candidate_score,
    _eligible_for_simulation,
    _load_candidates,
    _score_simulated_candidate,
    _save_candidates,
    _simulation_poll_interval,
    _simulation_poll_timeout,
    simulate_candidates_job,
    simulation_candidates_payload,
)


# ── Helpers ───────────────────────────────────────────────────────
def _make_candidate(**overrides):
    base = {
        "alpha_id": "alpha_test123",
        "expression": "rank(ts_mean(close, 20))",
        "dataset_id": "pv1",
        "scorecard": {"total_score": 75.0},
        "local_quality": {"passed": True},
        "official_metrics": {},
        "simulation_id": "",
        "lifecycle_status": "generated",
        "source_tags": ["local_only"],
    }
    base.update(overrides)
    return base


def _make_config(storage_dir, **ops_overrides):
    """Build a SimpleNamespace config mock matching RunConfig structure."""
    ops_kw = {
        "storage_dir": storage_dir,
        "budget": SimpleNamespace(
            min_prior_score_for_official_simulation=60.0,
            max_official_simulations_per_cycle=3,
            official_retry_pause_seconds=60.0,
        ),
        "thresholds": QualityThresholds(),
        "scoring": ScoringConfig(),
        "settings": SimpleNamespace(
            to_platform_dict=lambda: {
                "settings": {
                    "region": "USA",
                    "universe": "TOP3000",
                    "delay": 1,
                    "instrumentType": "EQUITY",
                    "dataset": "pv1",
                }
            }
        ),
        "official_api": SimpleNamespace(),
    }
    ops_kw.update(ops_overrides)
    return SimpleNamespace(
        ops=SimpleNamespace(**ops_kw),
        credentials=SimpleNamespace(
            username="test_user", password="test_pass", token="",
            username_env="BRAIN_USERNAME", password_env="BRAIN_PASSWORD", token_env="BRAIN_TOKEN",
        ),
    )


def _complete_pass_metrics():
    return {
        "official_alpha_id": "official_alpha_1",
        "pass_fail": "PASS",
        "sharpe": 2.0,
        "fitness": 1.3,
        "turnover": 0.2,
        "returns": 0.08,
        "drawdown": 0.02,
        "margin": 5.0,
        "correlation": 0.1,
        "self_correlation": 0.1,
        "prod_correlation": 0.1,
        "weight_concentration": 0.02,
        "sub_universe_sharpe": 2.0,
        "subUniverseSize": 1000,
        "alphaSize": 1000,
    }


def _last_audit_event(row):
    audit = row["scientific_audit"]
    assert audit["schema_version"] == "candidate-scientific-audit-v1"
    assert audit["safety_boundary"]["submit_allowed"] is False
    assert audit["safety_boundary"]["real_submit_performed"] is False
    return audit["events"][-1]


# ── _candidate_score ─────────────────────────────────────────────
class TestCandidateScore:
    def test_extracts_from_scorecard(self):
        assert _candidate_score({"scorecard": {"total_score": 82.5}}) == 82.5

    def test_falls_back_to_score_key(self):
        assert _candidate_score({"score": 60.0}) == 60.0

    def test_returns_zero_for_missing(self):
        assert _candidate_score({}) == 0.0

    def test_returns_zero_for_nan(self):
        assert _candidate_score({"score": float("nan")}) == 0.0

    def test_returns_zero_for_non_numeric(self):
        assert _candidate_score({"score": "bad"}) == 0.0


# ── _eligible_for_simulation ─────────────────────────────────────
class TestEligibleForSimulation:
    def test_basic_eligible(self):
        c = _make_candidate()
        assert _eligible_for_simulation(c, min_score=60.0) is True

    def test_allows_partial_official_metrics_to_be_refreshed(self):
        c = _make_candidate(official_metrics={"sharpe": 1.5, "fitness": 1.1, "turnover": 0.4})
        assert _eligible_for_simulation(c, min_score=60.0) is True

    def test_rejects_complete_official_pass_result(self):
        c = _make_candidate(official_metrics={
            "sharpe": 1.5,
            "fitness": 1.1,
            "turnover": 0.4,
            "self_correlation": 0.2,
            "prod_correlation": 0.3,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.4,
            "pass_fail": "PASS",
        })
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_below_score_threshold(self):
        c = _make_candidate(scorecard={"total_score": 50.0})
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_running_simulation(self):
        c = _make_candidate(simulation_id="/simulations/abc", lifecycle_status="simulation_running")
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_deferred_simulation_without_cooldown_until(self):
        c = _make_candidate(lifecycle_status="simulation_deferred_concurrency_limit")
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_deferred_simulation_until_cooldown_expires(self):
        c = _make_candidate(
            lifecycle_status="simulation_deferred_rate_limit",
            simulation_deferred_until=1060.0,
        )

        assert _eligible_for_simulation(c, min_score=60.0, now=1000.0) is False
        assert _eligible_for_simulation(c, min_score=60.0, now=1061.0) is True
        assert c["simulation_cooldown_active"] is False

    def test_rejects_local_quality_failed(self):
        c = _make_candidate(local_quality={"passed": False})
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_unsafe_scientific_audit_feedback_before_official_simulation(self):
        c = _make_candidate(
            scientific_audit={
                "schema_version": "candidate-scientific-audit-v1",
                "anti_overfit": {"test_script_outcomes_used": False},
                "evidence": {"feedback_sources": ["scorecard"]},
                "safety_boundary": {"submit_allowed": False, "real_submit_performed": False},
            },
            extra_fields={
                "scientific_audit": {
                    "schema_version": "candidate-scientific-audit-v1",
                    "anti_overfit": {"test_script_outcomes_used": False},
                    "evidence": {"feedback_sources": ["pytest_result"]},
                    "safety_boundary": {"submit_allowed": False, "real_submit_performed": False},
                }
            },
        )

        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_unsupported_local_backtest_support(self):
        c = _make_candidate(
            local_quality={
                "passed": True,
                "local_backtest_support": {
                    "supported": False,
                    "unsupported_fields": ["sedol", "pv13_revere_parent"],
                },
            }
        )
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_string_false_local_backtest_support(self):
        c = _make_candidate(
            local_quality={"passed": True, "local_backtest_support": {"supported": "false"}}
        )
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_legacy_candidate_with_non_signal_data_fields(self):
        c = _make_candidate(
            data_fields=[
                "open",
                "pv13_top",
                "topsp200",
                "pv13_top200",
                "pv13_topsp",
                "pv13_hierarchy_level",
                "pv13_revere_parent",
                "pv13_rha2_min20_3000_513",
                "pv13_rha2_foo",
                "pv13_isin",
            ]
        )
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_expression_only_legacy_candidate_with_non_signal_fields(self):
        c = _make_candidate(expression="rank(sedol)", data_fields=[])
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_expression_only_legacy_candidate_with_rha_field(self):
        c = _make_candidate(expression="rank(ts_mean(pv13_rha2_foo, 20))", data_fields=[])
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_stale_data_fields_when_expression_has_non_signal_field(self):
        c = _make_candidate(expression="rank(ts_mean(pv13_rha2_foo, 20))", data_fields=["open"])
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_allows_group_key_when_expression_uses_group_operator(self):
        c = _make_candidate(expression="group_neutralize(rank(open), sector)", data_fields=["open"])
        assert _eligible_for_simulation(c, min_score=60.0) is True

    def test_allows_zero_score_when_threshold_is_zero(self):
        c = _make_candidate(scorecard={"total_score": 0.0})
        assert _eligible_for_simulation(c, min_score=0.0) is True


    def test_round_trip(self, tmp_path):
        storage = str(tmp_path)
        candidates = [_make_candidate(), _make_candidate(alpha_id="alpha_2")]
        _save_candidates(storage, candidates)
        loaded = _load_candidates(storage)
        assert len(loaded) == 2
        assert loaded[0]["alpha_id"] == "alpha_test123"
        assert loaded[1]["alpha_id"] == "alpha_2"

    def test_empty_file(self, tmp_path):
        assert _load_candidates(str(tmp_path)) == []

    def test_handles_malformed_lines(self, tmp_path):
        path = tmp_path / "candidates.jsonl"
        path.write_text("not json\n{}\n", encoding="utf-8")
        loaded = _load_candidates(str(tmp_path))
        assert len(loaded) == 1

    def test_handles_missing_file(self):
        assert _load_candidates("/nonexistent/path") == []

    def test_save_candidates_merges_with_concurrent_appends(self, tmp_path):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_existing")])

        concurrent = _make_candidate(alpha_id="alpha_concurrent", expression="rank(volume)")
        with (tmp_path / "candidates.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(concurrent, ensure_ascii=False) + "\n")

        _save_candidates(storage, [_make_candidate(alpha_id="alpha_existing", official_metrics={"sharpe": 1.4})])
        loaded = {row["alpha_id"]: row for row in _load_candidates(storage)}

        assert loaded["alpha_existing"]["official_metrics"]["sharpe"] == 1.4
        assert loaded["alpha_concurrent"]["expression"] == "rank(volume)"

    def test_candidate_update_row_preserves_top_level_scientific_audit_when_requested(self):
        audit = {
            "schema_version": "candidate-scientific-audit-v1",
            "safety_boundary": {"submit_allowed": False, "real_submit_performed": False},
        }

        update = candidate_update_row(
            _make_candidate(alpha_id="alpha_audited", scientific_audit=audit),
            ["scientific_audit", "extra_fields"],
        )

        assert update["alpha_id"] == "alpha_audited"
        assert update["scientific_audit"] == audit

    def test_score_simulated_candidate_uses_candidate_model_with_legacy_defaults(self):
        config = _make_config("/tmp/data")

        scored = _score_simulated_candidate(
            _make_candidate(
                family="",
                hypothesis="",
                official_metrics={"sharpe": 1.6, "fitness": 1.2, "turnover": 0.2},
            ),
            config,
        )

        assert scored["scorecard"]["score_basis"] == "official_verified"
        assert scored["scorecard"]["empirical"]["score"] >= 0

    def test_score_simulated_candidate_preserves_top_level_readiness_evidence(self):
        config = _make_config("/tmp/data")

        scored = _score_simulated_candidate(
            _make_candidate(
                official_alpha_id="official_alpha_1",
                family="Reversion",
                hypothesis="Mean reversion alpha with liquid equity universe risk control.",
                official_metrics=_complete_pass_metrics(),
                cloud_correlation_risk={"max_similarity": 0.2, "level": "low"},
                gate={"submission_ready": True},
            ),
            config,
        )

        assert scored["cloud_correlation_risk"]["max_similarity"] == 0.2
        assert scored["gate"]["submission_ready"] is True
        assert scored["gate"]["official_release_gate"]["status"] == "PASS"
        assert "cloud_correlation_risk" not in scored.get("extra_fields", {})

    def test_score_simulated_candidate_overwrites_stale_green_gate_when_metrics_incomplete(self):
        config = _make_config("/tmp/data")

        scored = _score_simulated_candidate(
            _make_candidate(
                official_alpha_id="official_alpha_1",
                official_metrics={"sharpe": 1.6, "fitness": 1.2, "turnover": 0.2, "pass_fail": "PASS"},
                gate={"submission_ready": True},
            ),
            config,
        )

        assert scored["gate"]["submission_ready"] is False
        assert scored["gate"]["status"] == "NEEDS_ITERATION"
        assert "official_metric_fields_complete" in " ".join(scored["gate"]["failed_reasons"])


# ── simulation_candidates_payload ────────────────────────────────
class TestSimulationCandidatesPayload:
    def test_returns_eligible_count(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        candidates = [
            _make_candidate(),
            _make_candidate(alpha_id="alpha_low", scorecard={"total_score": 30.0}),
        ]
        _save_candidates(storage, candidates)
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        result = simulation_candidates_payload({})
        assert result["ok"] is True
        assert result["eligible_count"] == 1
        assert result["total_candidates"] == 2

    def test_preview_without_specific_ids_ranks_eligible_targets_by_score(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_low_file_first", expression="rank(low)", scorecard={"total_score": 61.0}),
                _make_candidate(alpha_id="alpha_top", expression="rank(close)", scorecard={"total_score": 95.0}),
                _make_candidate(alpha_id="alpha_mid", expression="rank(open)", scorecard={"total_score": 88.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        result = simulation_candidates_payload({})

        assert [row["alpha_id"] for row in result["eligible_alphas"]] == [
            "alpha_top",
            "alpha_mid",
            "alpha_low_file_first",
        ]

    def test_preview_with_specific_ids(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        candidates = [_make_candidate(), _make_candidate(alpha_id="alpha_2")]
        _save_candidates(storage, candidates)
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        result = simulation_candidates_payload({"candidate_ids": ["alpha_2"]})
        assert result["eligible_count"] == 1

    def test_preview_with_specific_ids_still_ranks_requested_targets_by_score(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_requested_low", expression="rank(low)", scorecard={"total_score": 70.0}),
                _make_candidate(alpha_id="alpha_requested_top", expression="rank(close)", scorecard={"total_score": 94.0}),
                _make_candidate(alpha_id="alpha_unrequested_high", expression="rank(vwap)", scorecard={"total_score": 99.0}),
                _make_candidate(alpha_id="alpha_requested_mid", expression="rank(open)", scorecard={"total_score": 88.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        result = simulation_candidates_payload({
            "candidate_ids": ["alpha_requested_mid", "alpha_requested_low", "alpha_requested_top"]
        })

        assert [row["alpha_id"] for row in result["eligible_alphas"]] == [
            "alpha_requested_top",
            "alpha_requested_mid",
            "alpha_requested_low",
        ]

    def test_preview_uses_workflow_validator_queue_without_api_client(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_unqueued_high", expression="rank(vwap)", scorecard={"total_score": 99.0}),
                _make_candidate(alpha_id="alpha_queued_mid", expression="rank(close)", scorecard={"total_score": 82.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preview must not create API client")),
        )

        result = simulation_candidates_payload({
            "workflow_plan": {
                "validator": {
                    "next_candidate_ids": ["alpha_queued_mid"],
                },
            },
        })

        assert result["eligible_count"] == 1
        assert [row["alpha_id"] for row in result["eligible_alphas"]] == ["alpha_queued_mid"]

    def test_preview_with_specific_ids_matches_official_or_simulation_ids(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        candidates = [
            _make_candidate(
                alpha_id="local_alpha",
                official_alpha_id="official_alpha",
                simulation_id="/simulations/official_sim",
            ),
        ]
        _save_candidates(storage, candidates)
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        by_official_id = simulation_candidates_payload({"candidate_ids": ["official_alpha"]})
        by_simulation_id = simulation_candidates_payload({"candidate_ids": ["/simulations/official_sim"]})

        assert by_official_id["eligible_count"] == 1
        assert by_official_id["eligible_alphas"][0]["alpha_id"] == "local_alpha"
        assert by_simulation_id["eligible_count"] == 1
        assert by_simulation_id["eligible_alphas"][0]["alpha_id"] == "local_alpha"

    def test_preview_with_specific_ids_skips_cooling_deferred_candidate(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(
                    alpha_id="alpha_2",
                    lifecycle_status="simulation_deferred_concurrency_limit",
                    simulation_deferred_until=1060.0,
                )
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 1000.0)
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        result = simulation_candidates_payload({"candidate_ids": ["alpha_2"]})

        assert result["eligible_count"] == 0
        assert result["eligible_alphas"] == []

    def test_preview_dedupes_targets_by_expression(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_1", expression="rank(volume)"),
                _make_candidate(alpha_id="alpha_2", expression=" rank(  volume ) "),
                _make_candidate(alpha_id="alpha_3", expression="rank(close)"),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        result = simulation_candidates_payload({})

        assert result["eligible_count"] == 2
        assert [row["alpha_id"] for row in result["eligible_alphas"]] == ["alpha_1", "alpha_3"]

    def test_preview_keeps_same_expression_when_dataset_differs(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_1", expression="rank(volume)", dataset_id="pv1"),
                _make_candidate(alpha_id="alpha_2", expression=" rank( volume ) ", dataset_id="model77"),
                _make_candidate(alpha_id="alpha_3", expression="rank(volume)", dataset_id="pv1"),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        result = simulation_candidates_payload({})

        assert result["eligible_count"] == 2
        assert [row["alpha_id"] for row in result["eligible_alphas"]] == ["alpha_1", "alpha_2"]

    def test_preview_reports_account_cooldown_as_no_eligible(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_ready")])
        (tmp_path / "simulation_cooldown.json").write_text(
            json.dumps(
                {
                    "official_simulation": {
                        "active": True,
                        "deferred_until": 1060.0,
                        "retry_after_seconds": 60.0,
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 1000.0)

        result = simulation_candidates_payload({})

        assert result["eligible_count"] == 0
        assert result["eligible_alphas"] == []
        assert result["account_cooldown"]["remaining_seconds"] == 60.0


class RecordingJobStore:
    def __init__(self):
        self.updates: list[dict] = []
        self.cancelled = False

    def update(self, job_id, **kwargs):
        self.updates.append({"job_id": job_id, **kwargs})

    def is_cancelled(self, _job_id):
        return self.cancelled


class CancelAfterCapacityWaitStore(RecordingJobStore):
    def __init__(self, *, after: int):
        super().__init__()
        self.after = after
        self.capacity_wait_updates = 0

    def update(self, job_id, **kwargs):
        super().update(job_id, **kwargs)
        progress = kwargs.get("progress") if isinstance(kwargs.get("progress"), dict) else {}
        if progress.get("phase") == "simulation_capacity_wait":
            self.capacity_wait_updates += 1
            if self.capacity_wait_updates >= self.after:
                self.cancelled = True


# ── simulate_candidates_job ──────────────────────────────────────
class TestSimulateCandidatesJob:
    def test_web_backtest_poll_interval_stays_fixed_five_seconds(self, tmp_path):
        config = _make_config(
            str(tmp_path),
            official_api=SimpleNamespace(poll_attempts=30, poll_interval_seconds=6.0),
        )

        assert _simulation_poll_timeout(config, {}) == 180.0
        assert _simulation_poll_interval(config, {}) == 5.0
        assert _simulation_poll_timeout(config, {"poll_timeout": 9}) == 9.0
        assert _simulation_poll_interval(config, {"poll_interval": 0.25}) == 5.0

    def test_job_without_specific_ids_submits_top_three_by_score(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_70", expression="rank(close_70)", scorecard={"total_score": 70.0}),
                _make_candidate(alpha_id="alpha_95", expression="rank(close_95)", scorecard={"total_score": 95.0}),
                _make_candidate(alpha_id="alpha_80", expression="rank(close_80)", scorecard={"total_score": 80.0}),
                _make_candidate(alpha_id="alpha_91", expression="rank(close_91)", scorecard={"total_score": 91.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.side_effect = ["/simulations/top", "/simulations/second", "/simulations/third"]
        mock_api.poll_simulation.return_value = "FAILED"
        mock_api.fetch_result.return_value = {"error": "mock failed"}
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_top3", {}, job_store=job_store)

        submitted_expressions = [call.args[0] for call in mock_api.submit_simulation.call_args_list]
        assert submitted_expressions == ["rank(close_95)", "rank(close_91)", "rank(close_80)"]

    def test_workflow_validator_queue_is_not_replaced_by_newer_high_score_candidates(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_selected", expression="rank(close_70)", scorecard={"total_score": 70.0}),
                _make_candidate(alpha_id="alpha_newer_high", expression="rank(close_99)", scorecard={"total_score": 99.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/selected"
        mock_api.poll_simulation.return_value = "FAILED"
        mock_api.fetch_result.return_value = {"error": "mock failed"}
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job(
            "job_workflow_queue",
            {
                "workflow_plan": {
                    "validator": {
                        "next_candidate_ids": ["alpha_selected"],
                    },
                },
                "poll_timeout": 10,
            },
            job_store=job_store,
        )

        submitted_expressions = [call.args[0] for call in mock_api.submit_simulation.call_args_list]
        assert submitted_expressions == ["rank(close_70)"]

    def test_top_three_are_submitted_before_first_poll(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_95", expression="rank(close_95)", scorecard={"total_score": 95.0}),
                _make_candidate(alpha_id="alpha_91", expression="rank(close_91)", scorecard={"total_score": 91.0}),
                _make_candidate(alpha_id="alpha_80", expression="rank(close_80)", scorecard={"total_score": 80.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        events: list[str] = []

        class FakeAPI:
            def authenticate(self):
                return {"auth": "ok"}

            def submit_simulation(self, expression, _settings):
                events.append(f"submit:{expression}")
                return f"/simulations/{expression.removeprefix('rank(').removesuffix(')')}"

            def poll_simulation(self, simulation_id):
                events.append(f"poll:{simulation_id}")
                return "FAILED"

            def fetch_result(self, simulation_id):
                events.append(f"fetch:{simulation_id}")
                return {"raw": {"status": "FAILED", "message": f"failed {simulation_id}"}}

        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": FakeAPI(),
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_slots", {"poll_timeout": 10}, job_store=job_store)

        assert events[:3] == [
            "submit:rank(close_95)",
            "submit:rank(close_91)",
            "submit:rank(close_80)",
        ]
        first_poll_index = next(i for i, event in enumerate(events) if event.startswith("poll:"))
        assert first_poll_index == 3

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        submitted_rows = [row for row in backtest_rows if row["action"] == "submitted"]
        assert [row["slot"] for row in submitted_rows] == [1, 2, 3]

    def test_capacity_hit_after_active_slots_does_not_starve_polling(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_95", expression="rank(close_95)", scorecard={"total_score": 95.0}),
                _make_candidate(alpha_id="alpha_91", expression="rank(close_91)", scorecard={"total_score": 91.0}),
                _make_candidate(alpha_id="alpha_80", expression="rank(close_80)", scorecard={"total_score": 80.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 9000.0)
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        events: list[str] = []

        class FakeAPI:
            def authenticate(self):
                return {"auth": "ok"}

            def submit_simulation(self, expression, _settings):
                events.append(f"submit:{expression}")
                if expression == "rank(close_80)":
                    raise BrainAPIError(
                        "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
                        status_code=400,
                        payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
                        retry_after=13,
                    )
                return f"/simulations/{expression.removeprefix('rank(').removesuffix(')')}"

            def poll_simulation(self, simulation_id):
                events.append(f"poll:{simulation_id}")
                return "FAILED"

            def fetch_result(self, simulation_id):
                return {"raw": {"status": "FAILED", "message": f"failed {simulation_id}"}}

        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": FakeAPI(),
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_capacity_active", {"poll_timeout": 10}, job_store=job_store)

        assert events == [
            "submit:rank(close_95)",
            "submit:rank(close_91)",
            "submit:rank(close_80)",
            "poll:/simulations/close_95",
            "poll:/simulations/close_91",
        ]
        loaded = {row["alpha_id"]: row for row in _load_candidates(storage)}
        assert loaded["alpha_80"]["lifecycle_status"] == "simulation_deferred_concurrency_limit"
        assert loaded["alpha_80"]["simulation_retry_after_seconds"] == 13.0
        event = _last_audit_event(loaded["alpha_80"])
        assert event["source"] == "web_official_simulation_capacity_deferred"
        assert event["official_api_called"] is True
        assert event["details"]["status"] == "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"
        final_results = job_store.updates[-1]["progress"]["data"]["results"]
        assert any(row["status"] == "deferred_concurrency_limit" for row in final_results)

    def test_poll_rate_limit_defers_one_slot_without_blocking_others(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(alpha_id="alpha_95", expression="rank(close_95)", scorecard={"total_score": 95.0}),
                _make_candidate(alpha_id="alpha_91", expression="rank(close_91)", scorecard={"total_score": 91.0}),
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )

        current_time = {"value": 0.0}
        events: list[str] = []

        def fake_monotonic():
            return current_time["value"]

        def fake_sleep(seconds):
            events.append(f"sleep:{seconds}")
            current_time["value"] += float(seconds or 0.0)

        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.monotonic", fake_monotonic)
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", fake_sleep)

        class FakeAPI:
            def __init__(self):
                self.rate_limited_once = False

            def authenticate(self):
                return {"auth": "ok"}

            def submit_simulation(self, expression, _settings):
                events.append(f"submit:{expression}")
                return f"/simulations/{expression.removeprefix('rank(').removesuffix(')')}"

            def poll_simulation(self, simulation_id):
                events.append(f"poll:{simulation_id}")
                if simulation_id == "/simulations/close_95" and not self.rate_limited_once:
                    self.rate_limited_once = True
                    raise BrainAPIError("HTTP 429: Too Many Requests", status_code=429, retry_after=30)
                return "FAILED"

            def fetch_result(self, simulation_id):
                return {"raw": {"status": "FAILED", "message": f"failed {simulation_id}"}}

        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": FakeAPI(),
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_poll_429", {"poll_timeout": 40}, job_store=job_store)

        first_poll_95 = events.index("poll:/simulations/close_95")
        first_poll_91 = events.index("poll:/simulations/close_91")
        assert first_poll_91 == first_poll_95 + 1
        assert "sleep:30.0" not in events[:first_poll_91]
        final_results = job_store.updates[-1]["progress"]["data"]["results"]
        assert {row["alpha_id"] for row in final_results} == {"alpha_95", "alpha_91"}

    def test_zero_requested_slots_do_not_authenticate(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_ready")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        create_api = MagicMock(side_effect=AssertionError("no official API session should be created for zero slots"))
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation._create_api", create_api)

        job_store = RecordingJobStore()
        simulate_candidates_job("job_zero_slots", {"max_simulations": 0}, job_store=job_store)

        create_api.assert_not_called()
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["phase"] == "no_simulation_slots"
        assert final_progress["data"]["eligible"] == 1
        assert final_progress["data"]["slot_limit"] == 0

    def test_poll_progress_updates_keep_simulation_job_observable(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate()])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/test"
        mock_api.poll_simulation.side_effect = ["RUNNING", "FAILED"]
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_poll", {"poll_interval": 0, "poll_timeout": 10}, job_store=job_store)

        progress_updates = [
            row["progress"]
            for row in job_store.updates
            if isinstance(row.get("progress"), dict)
        ]
        polling = [row for row in progress_updates if row.get("phase") == "simulation_polling"]

        assert polling, "official simulation polling did not publish observable progress"
        assert any(row.get("data", {}).get("last_status") == "RUNNING" for row in polling)
        assert all(row.get("status_message") for row in polling)
        assert any(row.get("percent_complete") is not None for row in polling)

    def test_concurrency_limit_retries_every_five_seconds_before_polling(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_retry")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        sleep_calls: list[float] = []
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda seconds: sleep_calls.append(seconds))

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.side_effect = [
            BrainAPIError(
                "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
                status_code=400,
                payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
                retry_after=60,
            ),
            "/simulations/retry-ok",
        ]
        mock_api.poll_simulation.return_value = "FAILED"
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_retry", {"candidate_ids": ["alpha_retry"], "poll_timeout": 10}, job_store=job_store)

        assert mock_api.submit_simulation.call_count == 2
        assert sleep_calls[0] == 5.0
        assert sleep_calls[1] == 5.0
        progress_updates = [row["progress"] for row in job_store.updates if isinstance(row.get("progress"), dict)]
        capacity_wait = [row for row in progress_updates if row.get("phase") == "simulation_capacity_wait"]
        polling = [row for row in progress_updates if row.get("phase") == "simulation_polling"]
        assert capacity_wait
        assert capacity_wait[-1]["data"]["submit_attempts"] == 1
        assert "已等待" in capacity_wait[-1]["message"]
        assert polling
        loaded = _load_candidates(storage)[0]
        assert loaded["simulation_cooldown_active"] is False

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert [row["action"] for row in backtest_rows] == ["capacity_wait", "submitted", "failed"]
        assert backtest_rows[0]["next_poll_seconds"] == 5.0
        assert backtest_rows[1]["next_poll_seconds"] == 5.0

    def test_concurrency_limit_capacity_wait_times_out_without_hanging(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_timeout")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 7000.0)
        sleep_calls: list[float] = []
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda seconds: sleep_calls.append(seconds))

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.side_effect = BrainAPIError(
            "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
            retry_after=17,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job(
            "job_capacity_timeout",
            {"candidate_ids": ["alpha_timeout"], "poll_timeout": 0},
            job_store=job_store,
        )

        assert mock_api.submit_simulation.call_count == 1
        assert sleep_calls == []
        loaded = _load_candidates(storage)[0]
        assert loaded["lifecycle_status"] == "simulation_deferred_concurrency_limit"
        assert loaded["simulation_retry_after_seconds"] == 17.0
        event = _last_audit_event(loaded)
        assert event["source"] == "web_official_simulation_capacity_timeout"
        assert event["official_api_called"] is True
        assert event["details"]["status"] == "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"
        progress_updates = [row["progress"] for row in job_store.updates if isinstance(row.get("progress"), dict)]
        assert any(row.get("phase") == "simulation_capacity_timeout" for row in progress_updates)
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["data"]["failed"] == 1
        assert final_progress["data"]["results"][0]["status"] == "deferred_concurrency_limit"

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert [row["action"] for row in backtest_rows] == ["capacity_timeout"]
        assert backtest_rows[0]["next_poll_seconds"] == 0.0

    def test_submit_failure_appends_scientific_audit_event(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_submit_failed")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.side_effect = BrainAPIError("HTTP 500: submit unavailable", status_code=500)
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_submit_failed", {"candidate_ids": ["alpha_submit_failed"]}, job_store=job_store)

        loaded = _load_candidates(storage)[0]
        assert loaded["lifecycle_status"] == "simulation_submit_failed"
        event = _last_audit_event(loaded)
        assert event["source"] == "web_official_simulation_submit_failed"
        assert event["official_api_called"] is True
        assert event["details"]["status"] == "SUBMIT_FAILED"
        assert "submit unavailable" in event["details"]["error"]
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["data"]["results"][0]["status"] == "submit_failed"

    def test_terminal_failure_clears_stale_candidate_cooldown_fields(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(
                    lifecycle_status="generated",
                    simulation_deferred_until=1000.0,
                    simulation_retry_after_seconds=60.0,
                    simulation_cooldown_active=True,
                    simulation_deferred_reason="old limit",
                )
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/test"
        mock_api.poll_simulation.return_value = "FAILED"
        mock_api.fetch_result.return_value = {
            "raw": {"status": "FAILED", "message": "BRAIN rejected expression syntax"}
        }
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_failed_clears", {"poll_interval": 0, "poll_timeout": 10}, job_store=job_store)

        loaded = _load_candidates(storage)[0]
        assert loaded["lifecycle_status"] == "simulation_failed"
        assert loaded["simulation_cooldown_active"] is False
        assert loaded["simulation_deferred_until"] is None
        assert loaded["simulation_retry_after_seconds"] is None
        assert loaded["simulation_deferred_reason"] is None
        assert loaded["simulation_error"] == "BRAIN rejected expression syntax"
        assert loaded["last_status"] == "FAILED"
        assert loaded["extra_fields"]["last_simulation_error"] == "BRAIN rejected expression syntax"
        assert loaded["extra_fields"]["simulation_failure_evidence"]["source"] == "fetch_result"
        audit = loaded["scientific_audit"]
        assert audit["schema_version"] == "candidate-scientific-audit-v1"
        assert audit["events"][-1]["operation"] == "official_simulation_writeback"
        assert audit["events"][-1]["official_api_called"] is True
        assert audit["events"][-1]["details"]["status"] == "FAILED"
        assert audit["safety_boundary"]["submit_allowed"] is False

        final_progress = job_store.updates[-1]["progress"]
        assert job_store.updates[-1]["status"] == "failed"
        assert job_store.updates[-1]["result"]["completed"] == 0
        assert job_store.updates[-1]["result"]["failed"] == 1
        result = final_progress["data"]["results"][0]
        assert result["error"] == "BRAIN rejected expression syntax"
        assert result["failure_evidence"]["simulation_id"] == "/simulations/test"

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert backtest_rows[-1]["error"] == "BRAIN rejected expression syntax"
        assert "BRAIN rejected expression syntax" in backtest_rows[-1]["message"]

    def test_completed_simulation_appends_scientific_audit_events(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_completed")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/completed"
        mock_api.poll_simulation.return_value = "COMPLETED"
        mock_api.fetch_result.return_value = {
            "alpha_id": "official_completed",
            "metrics": _complete_pass_metrics(),
        }
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job(
            "job_completed_audit",
            {"candidate_ids": ["alpha_completed"], "poll_timeout": 10},
            job_store=job_store,
        )

        loaded = _load_candidates(storage)[0]
        operations = [event["operation"] for event in loaded["scientific_audit"]["events"]]
        assert loaded["official_alpha_id"]
        assert loaded["official_metrics"]
        assert operations.count("official_simulation_writeback") >= 3
        assert loaded["scientific_audit"]["events"][-1]["details"]["status"] == "RESCORED"
        assert loaded["scientific_audit"]["safety_boundary"]["submit_allowed"] is False
        assert loaded["scientific_audit"]["safety_boundary"]["real_submit_performed"] is False

    def test_completed_simulation_fetch_result_failure_marks_candidate_failed_without_metrics(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_result_error", official_metrics={})])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/result-error"
        mock_api.poll_simulation.return_value = "COMPLETED"
        mock_api.fetch_result.side_effect = BrainAPIError("HTTP 500: result unavailable", status_code=500)
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job(
            "job_result_error",
            {"candidate_ids": ["alpha_result_error"], "poll_timeout": 10},
            job_store=job_store,
        )

        loaded = _load_candidates(storage)[0]
        assert loaded["lifecycle_status"] == "simulation_result_failed"
        assert loaded["official_metrics"] == {}
        final_update = job_store.updates[-1]
        assert final_update["status"] == "failed"
        result = final_update["progress"]["data"]["results"][0]
        assert result["status"] == "result_fetch_failed"
        assert result["simulation_id"] == "/simulations/result-error"

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert backtest_rows[-1]["action"] == "failed"
        assert backtest_rows[-1]["status"] == "RESULT_FETCH_FAILED"
        assert backtest_rows[-1]["simulation_id"] == "/simulations/result-error"

    def test_simulation_poll_timeout_marks_candidate_failed_and_writes_terminal_record(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_poll_timeout")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        current_time = {"value": 0.0}
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.monotonic", lambda: current_time["value"])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.time.sleep",
            lambda seconds: current_time.update({"value": current_time["value"] + float(seconds or 0.0)}),
        )

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/poll-timeout"
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job(
            "job_poll_timeout",
            {"candidate_ids": ["alpha_poll_timeout"], "poll_timeout": 1, "stall_timeout": 60},
            job_store=job_store,
        )

        mock_api.poll_simulation.assert_not_called()
        loaded = _load_candidates(storage)[0]
        assert loaded["lifecycle_status"] == "simulation_poll_timeout"
        event = _last_audit_event(loaded)
        assert event["source"] == "web_official_simulation_poll_timeout"
        assert event["official_api_called"] is True
        assert event["details"]["status"] == "POLL_TIMEOUT"
        assert event["details"]["simulation_id"] == "/simulations/poll-timeout"
        final_update = job_store.updates[-1]
        assert final_update["status"] == "failed"
        assert final_update["progress"]["data"]["results"][0]["status"] == "poll_timeout"

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert backtest_rows[-1]["action"] == "failed"
        assert backtest_rows[-1]["status"] == "POLL_TIMEOUT"
        assert backtest_rows[-1]["simulation_id"] == "/simulations/poll-timeout"

    def test_simulation_stall_timeout_marks_candidate_stalled_without_more_api_calls(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_stalled")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(
                storage,
                official_api=SimpleNamespace(poll_attempts=3, poll_interval_seconds=0.0),
            ),
        )
        current_time = {"value": 0.0}
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.monotonic", lambda: current_time["value"])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.time.sleep",
            lambda seconds: current_time.update({"value": current_time["value"] + float(seconds or 0.0)}),
        )

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.return_value = "/simulations/stalled"
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job(
            "job_stalled",
            {"candidate_ids": ["alpha_stalled"], "poll_timeout": 60, "stall_timeout": 1},
            job_store=job_store,
        )

        mock_api.poll_simulation.assert_not_called()
        loaded = _load_candidates(storage)[0]
        assert loaded["lifecycle_status"] == "simulation_stall_detected"
        event = _last_audit_event(loaded)
        assert event["source"] == "web_official_simulation_stall_detected"
        assert event["official_api_called"] is True
        assert event["details"]["status"] == "STALL_DETECTED"
        assert event["details"]["simulation_id"] == "/simulations/stalled"
        final_update = job_store.updates[-1]
        assert final_update["status"] == "failed"
        assert final_update["progress"]["data"]["results"][0]["status"] == "stall_detected"

        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert backtest_rows[-1]["action"] == "failed"
        assert backtest_rows[-1]["status"] == "STALL_DETECTED"
        assert backtest_rows[-1]["simulation_id"] == "/simulations/stalled"

    def test_submit_concurrency_wait_keeps_retrying_until_cancelled(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_limit")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 1000.0)
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.side_effect = BrainAPIError(
            "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
            retry_after=7,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = CancelAfterCapacityWaitStore(after=2)
        simulate_candidates_job(
            "job_limit",
            {"candidate_ids": ["alpha_limit"]},
            job_store=job_store,
        )

        assert mock_api.submit_simulation.call_count == 2
        loaded = _load_candidates(storage)
        assert loaded[0]["lifecycle_status"] == "simulation_deferred_concurrency_limit"
        assert loaded[0]["simulation_retry_after_seconds"] == 7.0
        assert loaded[0]["simulation_deferred_until"] == 1007.0
        assert loaded[0]["simulation_cooldown_active"] is True
        event = _last_audit_event(loaded[0])
        assert event["source"] == "web_official_simulation_capacity_wait"
        assert event["details"]["status"] == "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"
        assert job_store.updates[-1]["status"] == "stopped"
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["data"]["failed"] == 0
        assert final_progress["data"]["results"] == []
        cooldown = _active_account_simulation_cooldown(storage, now=1001.0)
        assert cooldown is not None
        assert cooldown["lifecycle_status"] == "simulation_deferred_concurrency_limit"
        backtest_rows = [
            json.loads(line)
            for line in (tmp_path / "backtests.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert [row["action"] for row in backtest_rows] == ["capacity_wait", "capacity_wait"]
        assert all(row["next_poll_seconds"] == 5.0 for row in backtest_rows)

    def test_plain_429_deferral_persists_account_and_candidate_cooldown(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_rate")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 2000.0)

        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        mock_api.submit_simulation.side_effect = BrainAPIError(
            "HTTP 429: Too Many Requests",
            status_code=429,
            retry_after=11,
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )

        job_store = RecordingJobStore()
        simulate_candidates_job("job_rate", {"candidate_ids": ["alpha_rate"]}, job_store=job_store)

        loaded = _load_candidates(storage)
        assert loaded[0]["lifecycle_status"] == "simulation_deferred_rate_limit"
        assert loaded[0]["simulation_deferred_until"] == 2011.0
        event = _last_audit_event(loaded[0])
        assert event["source"] == "web_official_simulation_rate_limit"
        assert event["official_api_called"] is True
        assert event["details"]["status"] == "RATE_LIMITED"
        assert _active_account_simulation_cooldown(storage, now=2001.0)["remaining_seconds"] == 10.0
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["data"]["results"][0]["status"] == "deferred_rate_limit"

    def test_repeated_run_during_account_cooldown_does_not_authenticate(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_next")])
        (tmp_path / "simulation_cooldown.json").write_text(
            json.dumps(
                {
                    "official_simulation": {
                        "active": True,
                        "deferred_until": 3060.0,
                        "retry_after_seconds": 60.0,
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 3000.0)
        create_api = MagicMock(side_effect=AssertionError("BRAIN API should not be created during cooldown"))
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation._create_api", create_api)

        job_store = RecordingJobStore()
        simulate_candidates_job("job_cooldown", {}, job_store=job_store)

        create_api.assert_not_called()
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["phase"] == "simulation_account_cooldown"
        assert final_progress["data"]["account_cooldown"]["remaining_seconds"] == 60.0

    def test_explicit_deferred_candidate_ids_do_not_authenticate(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(
            storage,
            [
                _make_candidate(
                    alpha_id="alpha_cooling",
                    lifecycle_status="simulation_deferred_rate_limit",
                    simulation_deferred_until=4060.0,
                )
            ],
        )
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 4000.0)
        create_api = MagicMock(side_effect=AssertionError("BRAIN API should not be created for cooling candidate"))
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation._create_api", create_api)

        job_store = RecordingJobStore()
        simulate_candidates_job("job_explicit_cooling", {"candidate_ids": ["alpha_cooling"]}, job_store=job_store)

        create_api.assert_not_called()
        final_progress = job_store.updates[-1]["progress"]
        assert final_progress["phase"] == "no_eligible"

    def test_simulation_save_preserves_concurrent_existing_row_updates(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_existing", expression="rank(close)")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.time", lambda: 5000.0)
        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation.time.sleep", lambda _seconds: None)

        def _create_api_with_concurrent_update(config, username="", password="", token=""):
            _save_candidates(
                storage,
                [
                    _make_candidate(
                        alpha_id="alpha_existing",
                        expression="rank(volume)",
                        official_metrics={"external": 1},
                        extra_fields={"peer_update": "kept"},
                    )
                ],
            )
            mock_api = MagicMock()
            mock_api.authenticate.return_value = {"auth": "ok"}
            mock_api.submit_simulation.side_effect = BrainAPIError(
                "HTTP 400: {'detail': 'CONCURRENT_SIMULATION_LIMIT_EXCEEDED'}",
                status_code=400,
                payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
                retry_after=9,
            )
            return mock_api

        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation._create_api", _create_api_with_concurrent_update)

        job_store = CancelAfterCapacityWaitStore(after=1)
        simulate_candidates_job(
            "job_merge",
            {"candidate_ids": ["alpha_existing"]},
            job_store=job_store,
        )

        loaded = _load_candidates(storage)[0]
        assert loaded["expression"] == "rank(volume)"
        assert loaded["official_metrics"] == {"external": 1}
        assert loaded["extra_fields"] == {"peer_update": "kept"}
        assert loaded["lifecycle_status"] == "simulation_deferred_concurrency_limit"
        assert loaded["simulation_retry_after_seconds"] == 9.0
        assert loaded["scientific_audit"]["events"][-1]["source"] == "web_official_simulation_capacity_wait"

    def test_no_candidates(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        # Mock authenticate to avoid real API calls
        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "session_cookie"}
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, **kw: mock_api,
        )
        job_store = MagicMock()
        job_store.is_cancelled.return_value = False
        simulate_candidates_job("job_test", {}, job_store=job_store)
        final_update = job_store.update.call_args_list[-1]
        assert final_update[1]["status"] == "completed"

    def test_cancellation_respected(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate()])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )
        # Mock BRAIN API creation to avoid needing real credentials
        mock_api = MagicMock()
        mock_api.authenticate.return_value = {"auth": "ok"}
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation._create_api",
            lambda config, username="", password="", token="": mock_api,
        )
        job_store = MagicMock()
        job_store.is_cancelled.return_value = True
        simulate_candidates_job("job_cancel", {}, job_store=job_store)
        # Cancellation should be respected — job should end quickly
        calls = [str(c) for c in job_store.update.call_args_list]
        assert any("status" in c for c in calls)

    def test_cancel_before_api_init_skips_create_api(self, tmp_path, monkeypatch):
        storage = str(tmp_path)
        _save_candidates(storage, [_make_candidate(alpha_id="alpha_cancel_pre_api", expression="rank(close)")])
        monkeypatch.setattr(
            "brain_alpha_ops.web_candidate_simulation.load_run_config",
            lambda: _make_config(storage),
        )

        def fail_create_api(*_args, **_kwargs):
            raise AssertionError("cancelled simulation must not initialize BRAIN API")

        monkeypatch.setattr("brain_alpha_ops.web_candidate_simulation._create_api", fail_create_api)

        job_store = RecordingJobStore()
        job_store.cancelled = True
        simulate_candidates_job("job_cancel_pre_api", {}, job_store=job_store)

        assert job_store.updates[-1]["status"] == "stopped"
        assert job_store.updates[-1]["progress"]["phase"] == "stopped"
        assert "远程 API 初始化前停止" in job_store.updates[-1]["progress"]["status_message"]
