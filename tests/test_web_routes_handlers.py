"""Tests for web route handler logic.

Covers: route dispatch, config sanitization, status queries,
JSONL payload construction, backtest slot computation,
candidate blocker detection.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from brain_alpha_ops.web_routes import (
    _public_config,
    _status_payload,
    _query_limit,
    _read_jsonl_tail,
    _jsonl_payload,
    _backtest_slot_limit,
    _backtest_slots_payload,
    _slot_payload,
    _slot_active,
    _slot_has_official_work_record,
    _candidate_score,
    _candidate_local_valid,
    _candidate_official_review_blockers,
    _candidate_submit_evidence_blockers,
    _is_submit_only_quality_reason,
    _candidate_high_cloud_similarity_blocked,
    _candidate_local_backtest_failed,
    _backtest_queue_next_action,
    _official_simulation_score_threshold,
    _submit_readiness_payload,
    _cloud_snapshot_payload,
)
from brain_alpha_ops.web.dispatch.get_routes import _helpers as _routes_helpers
from brain_alpha_ops.web.dispatch.get_routes._helpers import (
    _build_submit_readiness_payload as _shared_submit_readiness_payload,
)


# ═══════════════════════ Public Config Tests ═════════════════════════

class TestPublicConfig:
    def test_redacts_credentials(self):
        config = {
            "environment": "production",
            "credentials": {
                "username": "secret_user",
                "password": "secret_pass",
                "token": "secret_token",
                "username_env": "BRAIN_USERNAME",
            },
            "ops": {"storage_dir": "data"},
        }
        result = _public_config(config)
        creds = result["credentials"]
        assert creds["username"] == ""
        assert creds["password"] == ""
        assert creds["token"] == ""
        assert creds["username_env"] == "BRAIN_USERNAME"

    def test_missing_credentials(self):
        result = _public_config({"environment": "dev"})
        assert "credentials" in result
        assert result["credentials"]["username"] == ""

    def test_none_input(self):
        result = _public_config({})  # type: ignore[arg-type]
        assert isinstance(result, dict)


def test_web_routes_submit_readiness_uses_shared_compact_contract(monkeypatch):
    # Patch run_live_submit_readiness_check in the exact module globals that
    # submit_readiness_payload looks it up from. The web_* bridge creates
    # duplicate module objects, so dotted-string monkeypatch targets resolve
    # to a different object than the one owning submit_readiness_payload.
    monkeypatch.setitem(
        _shared_submit_readiness_payload.__globals__,
        "run_live_submit_readiness_check",
        lambda: {
            "ok": True,
            "ready_to_submit": False,
            "candidate_count": 2,
            "eligible_count": 0,
            "latest_blocking_reason_counts": {"missing_official_alpha_id": 2},
            "job_family_blocking_reason_counts": {"missing_official_metrics": 3},
            "best_candidate": {"alpha_id": "alpha_1", "blocking_reasons": ["missing_official_alpha_id"]},
            "job_audits": [{"large": "omitted"}],
        },
    )

    payload = _submit_readiness_payload()

    assert payload["source"] == "check_live_submit_readiness.py"
    assert payload["authoritative_stop_rule"] == "scripts/check_live_submit_readiness.py --config config/run_config.json --json"
    assert payload["validation_command"] == "scripts/check_live_submit_readiness.py --config config/run_config.json --json"
    assert payload["official_api_called"] is False
    assert payload["non_submit_flow"] is True
    assert payload["real_submit_performed"] is False
    assert payload["ready_to_submit"] is False
    assert payload["submit_ready_claim_allowed"] is False
    assert payload["ready"] is False
    assert payload["candidate_count"] == 2
    assert payload["eligible_count"] == 0
    assert payload["top_blocking_reasons"] == [{"reason": "missing_official_alpha_id", "count": 2}]
    assert payload["top_family_blocking_reasons"] == [{"reason": "missing_official_metrics", "count": 3}]
    assert payload["best_candidate"]["alpha_id"] == "alpha_1"
    assert "job_audits" not in payload


# ═══════════════════════ Query Limit Tests ════════════════════════════

class TestQueryLimit:
    def test_default(self):
        assert _query_limit({}) == 1000

    def test_valid_number(self):
        assert _query_limit({"limit": ["50"]}) == 50

    def test_clamp_high(self):
        assert _query_limit({"limit": ["10000"]}) == 5000

    def test_clamp_low(self):
        assert _query_limit({"limit": ["0"]}) == 1

    def test_invalid_number(self):
        assert _query_limit({"limit": ["abc"]}) == 1000

    def test_none_input(self):
        assert _query_limit({}) == 1000  # type: ignore[arg-type]


# ═══════════════════════ JSONL Read Tests ════════════════════════════

class TestReadJSONLTail:
    def test_empty_file(self):
        rows, total, path = _read_jsonl_tail("nonexistent.jsonl", limit=10)
        assert rows == []
        assert total == 0

    def test_read_valid_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"id": 1, "data": "a"}) + "\n")
            f.write(json.dumps({"id": 2, "data": "b"}) + "\n")
            f.write(json.dumps({"id": 3, "data": "c"}) + "\n")
            temp_path = f.name

        try:
            # Patch _storage_file on the module where _read_jsonl_tail looks
            # it up (its __globals__). The web_* bridge creates duplicate
            # module objects, so patching brain_alpha_ops.web_routes would
            # mutate a different namespace than the one bound to the function.
            with patch.object(_routes_helpers, "_storage_file", return_value=Path(temp_path)):
                rows, total, _ = _read_jsonl_tail("test.jsonl", limit=10)
                assert len(rows) == 3
                assert total == 3
        finally:
            import os
            os.unlink(temp_path)

    def test_limit_enforcement(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(20):
                f.write(json.dumps({"id": i}) + "\n")
            temp_path = f.name

        try:
            with patch.object(_routes_helpers, "_storage_file", return_value=Path(temp_path)):
                rows, _, _ = _read_jsonl_tail("test.jsonl", limit=5)
                # deque limit = 5, so we get last 5 items
                assert len(rows) == 5
        finally:
            import os
            os.unlink(temp_path)

    def test_skip_invalid_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write("not json\n")
            f.write(json.dumps({"id": 1}) + "\n")
            f.write("[1, 2, 3]\n")  # not a dict
            f.write(json.dumps({"id": 2}) + "\n")
            temp_path = f.name

        try:
            with patch.object(_routes_helpers, "_storage_file", return_value=Path(temp_path)):
                rows, total, _ = _read_jsonl_tail("test.jsonl", limit=10)
                assert len(rows) == 2  # only dict rows
                assert total == 2
        finally:
            import os
            os.unlink(temp_path)


# ═══════════════════════ Slot Tests ══════════════════════════════════

class TestSlotActive:
    def test_running_is_active(self):
        assert _slot_active("running") is True

    def test_pending_is_active(self):
        assert _slot_active("pending") is True

    def test_starting_is_active(self):
        assert _slot_active("STARTING") is True

    def test_submitted_rate_limited_and_poll_error_are_active(self):
        assert _slot_active("SUBMITTED") is True
        assert _slot_active("RATE_LIMITED") is True
        assert _slot_active("POLL_ERROR") is True

    def test_completed_not_active(self):
        assert _slot_active("completed") is False

    def test_terminal_failures_not_active(self):
        assert _slot_active("POLL_TIMEOUT") is False
        assert _slot_active("STALL_DETECTED") is False
        assert _slot_active("RESULT_FETCH_FAILED") is False

    def test_empty_not_active(self):
        assert _slot_active("empty") is False

    def test_none_not_active(self):
        assert _slot_active(None) is False


class TestSlotHasOfficialWorkRecord:
    def test_with_alpha_id(self):
        assert _slot_has_official_work_record({"status": "running", "alpha_id": "abc123"}) is True

    def test_with_simulation_id(self):
        assert _slot_has_official_work_record({"status": "running", "simulation_id": "sim456"}) is True

    def test_empty_slot(self):
        assert _slot_has_official_work_record({"status": "EMPTY"}) is False

    def test_capacity_wait(self):
        assert _slot_has_official_work_record({"status": "CAPACITY_WAIT"}) is False


class TestSlotPayload:
    def test_empty_slot(self):
        result = _slot_payload(1, None)
        assert result["slot"] == 1
        assert result["status"] == "empty"

    def test_populated_slot(self):
        row = {
            "status": "completed",
            "alpha_id": "alpha123",
            "expression": "rank(close/close10)",
            "sharpe": 1.5,
            "fitness": 1.2,
        }
        result = _slot_payload(3, row)
        assert result["slot"] == 3
        assert result["status"] == "completed"
        assert result["sharpe"] == 1.5


# ═══════════════════════ Candidate Tests ═════════════════════════════

class TestCandidateScore:
    def test_score_from_scorecard(self):
        c = {"scorecard": {"total_score": 85.5}}
        assert _candidate_score(c) == 85.5

    def test_score_fallback(self):
        c = {"score": 70.0}
        assert _candidate_score(c) == 70.0

    def test_score_nan(self):
        c = {"scorecard": {"total_score": float("nan")}}
        assert _candidate_score(c) == 0.0

    def test_score_missing(self):
        assert _candidate_score({}) == 0.0


class TestCandidateLocalValid:
    def test_diagnosis_valid(self):
        c = {"quality_diagnosis": {"local_candidate_valid": True}}
        assert _candidate_local_valid(c) is True

    def test_local_quality_passed(self):
        c = {"local_quality": {"passed": True}}
        assert _candidate_local_valid(c) is True

    def test_not_valid(self):
        c = {}
        assert _candidate_local_valid(c) is False


class TestOfficialReviewBlockers:
    def test_missing_quality_diagnosis(self):
        blockers = _candidate_official_review_blockers({}, min_score=70.0)
        assert "missing_quality_diagnosis" in blockers

    def test_score_below_threshold(self):
        c = {
            "quality_diagnosis": {"local_candidate_valid": True, "reasons": []},
            "scorecard": {"total_score": 50.0},
        }
        blockers = _candidate_official_review_blockers(c, min_score=70.0)
        assert "score_below_official_simulation_threshold" in blockers

    def test_local_invalid(self):
        c = {"quality_diagnosis": {"local_candidate_valid": False}}
        blockers = _candidate_official_review_blockers(c, min_score=70.0)
        assert "local_candidate_invalid" in blockers

    def test_blocking_reasons(self):
        c = {
            "quality_diagnosis": {
                "local_candidate_valid": True,
                "reasons": [
                    {"severity": "blocking", "code": "high_turnover", "category": "numeric_out_of_bounds"},
                ],
            },
            "scorecard": {"total_score": 80.0},
        }
        blockers = _candidate_official_review_blockers(c, min_score=70.0)
        assert "high_turnover" in blockers

    def test_high_cloud_similarity(self):
        c = {
            "quality_diagnosis": {"local_candidate_valid": True, "reasons": []},
            "scorecard": {"total_score": 80.0},
            "cloud_correlation_risk": {"level": "high"},
        }
        blockers = _candidate_official_review_blockers(c, min_score=70.0)
        assert "high_cloud_similarity" in blockers

    def test_lifecycle_blocked(self):
        c = {
            "quality_diagnosis": {"local_candidate_valid": True, "reasons": []},
            "scorecard": {"total_score": 80.0},
            "lifecycle_status": "blocked_high_cloud_similarity",
        }
        blockers = _candidate_official_review_blockers(c, min_score=70.0)
        assert "high_cloud_similarity" in blockers


class TestSubmitEvidenceBlockers:
    def test_submit_only_reasons(self):
        c = {
            "quality_diagnosis": {
                "reasons": [
                    {"severity": "blocking", "code": "missing_official_alpha_id", "category": "official_evidence_missing"},
                ],
            },
        }
        blockers = _candidate_submit_evidence_blockers(c)
        assert "missing_official_alpha_id" in blockers

    def test_fallback_reasons(self):
        c = {
            "quality_diagnosis": {
                "blocking_reasons": ["missing_official_metrics"],
            },
        }
        blockers = _candidate_submit_evidence_blockers(c)
        assert "missing_official_metrics" in blockers


class TestIsSubmitOnlyQualityReason:
    def test_known_code(self):
        assert _is_submit_only_quality_reason("missing_official_alpha_id", "") is True

    def test_known_category(self):
        assert _is_submit_only_quality_reason("", "official_evidence_missing") is True

    def test_unknown(self):
        assert _is_submit_only_quality_reason("high_turnover", "numeric_out_of_bounds") is False


# ═══════════════════════ Queue Next Action Tests ═════════════════════

class TestBacktestQueueNextAction:
    def test_no_candidates(self):
        assert _backtest_queue_next_action(candidate_count=0, review_candidate_count=0, open_slot_count=3) == "generate_candidates"

    def test_review_candidates_with_slots(self):
        assert _backtest_queue_next_action(candidate_count=10, review_candidate_count=3, open_slot_count=2) == "trusted_environment_official_simulation_required"

    def test_review_candidates_no_slots(self):
        assert _backtest_queue_next_action(candidate_count=10, review_candidate_count=3, open_slot_count=0) == "wait_for_open_backtest_slot"

    def test_no_review_candidates(self):
        assert _backtest_queue_next_action(candidate_count=10, review_candidate_count=0, open_slot_count=3) == "improve_or_regenerate_candidates"


# ═══════════════════════ Threshold Tests ═════════════════════════════

class TestOfficialSimulationScoreThreshold:
    @patch("brain_alpha_ops.web_routes.load_run_config")
    def test_returns_budget_threshold(self, mock_load):
        mock_config = MagicMock()
        mock_config.ops.budget.min_prior_score_for_official_simulation = 70.0
        mock_load.return_value = mock_config
        assert _official_simulation_score_threshold() == 70.0

    @patch("brain_alpha_ops.web_routes.load_run_config")
    def test_fallback_on_error(self, mock_load):
        mock_load.side_effect = RuntimeError("config not found")
        assert _official_simulation_score_threshold() == 70.0
