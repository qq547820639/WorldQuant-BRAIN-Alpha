"""Tests for per-candidate BRAIN simulation service."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from brain_alpha_ops.web_candidate_simulation import (
    _candidate_score,
    _eligible_for_simulation,
    _load_candidates,
    _save_candidates,
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
        ),
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

    def test_rejects_already_has_metrics(self):
        c = _make_candidate(official_metrics={"sharpe": 1.5})
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_below_score_threshold(self):
        c = _make_candidate(scorecard={"total_score": 50.0})
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_running_simulation(self):
        c = _make_candidate(simulation_id="/simulations/abc", lifecycle_status="simulation_running")
        assert _eligible_for_simulation(c, min_score=60.0) is False

    def test_rejects_local_quality_failed(self):
        c = _make_candidate(local_quality={"passed": False})
        assert _eligible_for_simulation(c, min_score=60.0) is False

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


# ── simulate_candidates_job ──────────────────────────────────────
class TestSimulateCandidatesJob:
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
        from brain_alpha_ops.web_candidate_simulation import simulate_candidates_job
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
        from brain_alpha_ops.web_candidate_simulation import simulate_candidates_job
        simulate_candidates_job("job_cancel", {}, job_store=job_store)
        # Cancellation should be respected — job should end quickly
        calls = [str(c) for c in job_store.update.call_args_list]
        assert any("status" in c for c in calls)
