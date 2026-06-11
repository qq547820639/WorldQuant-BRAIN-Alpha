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
from brain_alpha_ops.web_candidate_simulation import (
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
