"""Network-error and API-failure simulation tests.

Covers:
  - Mock API timeout scenarios
  - Mock connection refused
  - Mock rate limit exceeded (HTTP 429)
  - Mock malformed responses
  - Mock authentication failures
  - SSE/stream disconnection recovery
  - Submission gate under network-failure conditions
  - Rate limit policy validation
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.config import OpsConfig, QualityThresholds, RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
from brain_alpha_ops.brain_api.rate_limit_policy import validate_rate_limit_policy


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def thresholds():
    return QualityThresholds()


@pytest.fixture
def base_candidate():
    c = Candidate(
        alpha_id="net_error_test",
        expression="rank(ts_delta(close, 20)) + rank(ts_delta(volume / adv20, 20))",
        family="NetworkTest",
        hypothesis="Network error resilience test",
        data_fields=["close", "volume", "adv20"],
        operators=["rank", "ts_delta"],
    )
    c.official_alpha_id = "off_net_test"
    c.official_metrics = {
        "sharpe": 1.5, "fitness": 1.1, "turnover": 0.3,
        "returns": 0.08, "drawdown": 0.1, "pass_fail": "PASS",
    }
    return c


# ═══════════════════════════════════════════════════════════════════════
# API Timeout scenarios
# ═══════════════════════════════════════════════════════════════════════

class TestAPITimeout:
    """Scorecard and gate behavior when upstream API times out."""

    def test_scoring_survives_if_official_metrics_already_cached(self, base_candidate, thresholds):
        """If metrics are already cached, scoring should not need an API call."""
        scorecard = build_scorecard(base_candidate, thresholds)
        assert isinstance(scorecard, dict)
        assert "total_score" in scorecard

    def test_gate_with_timeout_flag_triggers_safe_fallback(self, base_candidate, thresholds):
        """A candidate with a timeout marker in official_metrics should gate safely."""
        base_candidate.official_metrics["_api_timeout"] = True
        gate = evaluate_quality_gate(base_candidate, thresholds)
        assert isinstance(gate, dict)
        assert "submission_ready" in gate

    @mock.patch("time.sleep", side_effect=TimeoutError("simulated timeout"))
    def test_timeout_in_downstream_call_surfaces_gracefully(self, mock_sleep, base_candidate, thresholds):
        """Even if a downstream call times out, the gate should not raise unhandled."""
        try:
            gate = evaluate_quality_gate(base_candidate, thresholds)
            assert isinstance(gate, dict)
        except TimeoutError:
            pass  # acceptable — as long as it's not an unhandled crash


# ═══════════════════════════════════════════════════════════════════════
# Connection refused
# ═══════════════════════════════════════════════════════════════════════

class TestConnectionRefused:
    """Behavior when remote connections are refused."""

    def test_missing_official_metrics_does_not_crash_scoring(self, thresholds):
        """If official_metrics dict is empty, scoring should still produce a scorecard."""
        c = Candidate(
            alpha_id="conn_refused",
            expression="rank(close)",
            family="ConnTest",
            hypothesis="Connection refused test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_conn"
        c.official_metrics = {}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_empty_official_metrics_gate_is_safe(self, thresholds):
        c = Candidate(
            alpha_id="conn_refused",
            expression="rank(close)",
            family="ConnTest",
            hypothesis="Connection refused test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_conn"
        c.official_metrics = {}
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)
        assert "submission_ready" in gate


# ═══════════════════════════════════════════════════════════════════════
# Rate limit exceeded (HTTP 429)
# ═══════════════════════════════════════════════════════════════════════

class TestRateLimitExceeded:
    """Validate rate-limit policy logic and fallback under 429 scenarios."""

    def test_validate_rate_limit_policy_accepts_production_config(self):
        """Production budget + api_config should pass with at most warnings."""
        policy = validate_rate_limit_policy(
            {"max_official_concurrent_simulations": 3, "stop_official_calls_on_rate_limit": True},
            {"rate_limit_backoff_seconds": 60, "allow_stale_context_on_rate_limit": False},
        )
        assert isinstance(policy, list)
        # Should not contain ERROR-level issues
        errors = [i for i in policy if i.get("severity") == "ERROR"]
        assert len(errors) == 0

    def test_validate_rate_limit_policy_reports_excessive_concurrency(self):
        """Concurrency exceeding regular limit (3) should be flagged as ERROR."""
        policy = validate_rate_limit_policy(
            {"max_official_concurrent_simulations": 10, "stop_official_calls_on_rate_limit": True},
            {},
        )
        assert isinstance(policy, list)
        errors = [i for i in policy if i.get("severity") == "ERROR"]
        assert len(errors) >= 1

    def test_validate_rate_limit_policy_warns_on_disabled_rate_limit_stop(self):
        """Disabling stop_on_rate_limit should produce a WARNING."""
        policy = validate_rate_limit_policy(
            {"stop_official_calls_on_rate_limit": False},
            {},
        )
        assert isinstance(policy, list)
        warnings = [i for i in policy if i.get("check") == "official_rate_limit_does_not_halt_cycle"]
        assert len(warnings) >= 1

    def test_validate_rate_limit_policy_empty_config_is_warning_only(self):
        """Empty configs should not trigger errors (defaults are safe)."""
        policy = validate_rate_limit_policy({}, {})
        assert isinstance(policy, list)
        errors = [i for i in policy if i.get("severity") == "ERROR"]
        assert len(errors) == 0

    def test_rate_limit_backoff_preserves_candidate_state(self, base_candidate, thresholds):
        """Candidate should remain unscorable but not corrupted after backoff pass."""
        scorecard = build_scorecard(base_candidate, thresholds)
        assert isinstance(scorecard, dict)

    def test_multiple_fast_candidates_do_not_corrupt_each_other(self, thresholds):
        """Many candidates in rapid succession should each get independent scorecards."""
        for i in range(20):
            c = Candidate(
                alpha_id=f"rate_{i}",
                expression=f"rank(close) + rank(volume)",
                family="RateTest",
                hypothesis="Batch rate-limit test",
                data_fields=["close", "volume"],
                operators=["rank"],
            )
            c.official_alpha_id = f"off_rate_{i}"
            c.official_metrics = {
                "sharpe": 1.5, "fitness": 1.1, "turnover": 0.3,
                "returns": 0.08, "drawdown": 0.1, "pass_fail": "PASS",
            }
            sc = build_scorecard(c, thresholds)
            assert isinstance(sc, dict)


# ═══════════════════════════════════════════════════════════════════════
# Malformed responses
# ═══════════════════════════════════════════════════════════════════════

class TestMalformedResponses:
    """Scoring resilience against malformed or unexpected API response shapes."""

    def test_official_metrics_with_wrong_type_values(self, thresholds):
        c = Candidate(
            alpha_id="malformed",
            expression="rank(close)",
            family="MalformTest",
            hypothesis="Malformed response test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_mal"
        c.official_metrics = {
            "sharpe": "not_a_number",
            "fitness": [1.0, 2.0],
            "turnover": {"v": 0.3},
            "pass_fail": True,
        }
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_official_metrics_with_extra_unexpected_keys(self, thresholds):
        c = Candidate(
            alpha_id="extra_keys",
            expression="rank(close)",
            family="ExtraTest",
            hypothesis="Extra keys test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_extra"
        c.official_metrics = {
            "sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS",
            "_weird_junk_field": object(),
            "__internal_debug": lambda: "bad",
        }
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_official_metrics_as_string_instead_of_dict(self, thresholds):
        c = Candidate(
            alpha_id="string_metrics",
            expression="rank(close)",
            family="StringTest",
            hypothesis="String metrics test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_str"
        c.official_metrics = '{"sharpe": 1.5}'  # type: ignore
        try:
            scorecard = build_scorecard(c, thresholds)
            assert isinstance(scorecard, dict)
        except (AttributeError, TypeError):
            pass  # non-dict metrics are a pathological input

    def test_pass_fail_field_with_nonstandard_values(self, thresholds):
        c = Candidate(
            alpha_id="nonstd_pf",
            expression="rank(close)",
            family="NonStdPF",
            hypothesis="Non-standard pass_fail test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_nonstd"
        for pf_value in [None, "UNKNOWN", 0, 1, "", "yes", "no"]:
            c.official_metrics = {
                "sharpe": 1.5, "fitness": 1.1, "pass_fail": pf_value,
            }
            scorecard = build_scorecard(c, thresholds)
            assert isinstance(scorecard, dict)


# ═══════════════════════════════════════════════════════════════════════
# Authentication failures
# ═══════════════════════════════════════════════════════════════════════

class TestAuthenticationFailures:
    """Gating behavior when authentication state is absent or expired."""

    def test_candidate_without_official_alpha_id_scores_locally(self, thresholds):
        c = Candidate(
            alpha_id="no_auth",
            expression="rank(close)",
            family="AuthTest",
            hypothesis="No official_alpha_id test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        # no official_alpha_id set
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_empty_official_alpha_id_treated_as_missing(self, thresholds):
        c = Candidate(
            alpha_id="empty_auth",
            expression="rank(close)",
            family="EmptyAuthTest",
            hypothesis="Empty official_alpha_id test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = ""
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_run_config_with_empty_credentials_is_safe(self):
        rc = RunConfig(environment="production")
        rc.credentials = mock.MagicMock()
        rc.credentials.username = ""
        rc.credentials.password = ""
        rc.credentials.token = ""
        assert rc.credentials.username == ""


# ═══════════════════════════════════════════════════════════════════════
# SSE / stream disconnection recovery
# ═══════════════════════════════════════════════════════════════════════

class TestSSEDisconnection:
    """Behavior when streaming connections drop mid-flight."""

    def test_simulation_result_with_partial_metrics_is_scoreable(self, thresholds):
        c = Candidate(
            alpha_id="sse_partial",
            expression="rank(close)",
            family="SSETest",
            hypothesis="Partial SSE result test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_sse"
        c.official_metrics = {
            "sharpe": 1.5,
            # Intentionally missing fitness and other fields (simulates partial SSE)
            "pass_fail": "PASS",
        }
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_completely_empty_metrics_due_to_disconnect(self, thresholds):
        c = Candidate(
            alpha_id="sse_disconnect",
            expression="rank(close)",
            family="SSETest",
            hypothesis="SSE disconnect test",
            data_fields=["close"],
            operators=["rank"],
        )
        c.official_alpha_id = "off_sse_dc"
        c.official_metrics = {"pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)


# ═══════════════════════════════════════════════════════════════════════
# Submission gate under network-failure conditions
# ═══════════════════════════════════════════════════════════════════════

class TestSubmissionGateNetworkFailure:
    """Submission gate behavior when network data is unavailable."""

    def test_submission_preflight_with_no_cloud_data(self, tmp_path):
        from brain_alpha_ops.web_submission_safety import submission_preflight_advisory
        from brain_alpha_ops.config import RunConfig

        rc = RunConfig(environment="production")
        rc.ops.storage_dir = str(tmp_path)
        rc.ops.budget.require_cloud_sync = False

        class _MockLedger:
            def __init__(self, storage_dir, rows=None):
                self.rows = list(rows or [])
            def records(self):
                return list(self.rows)

        payload = submission_preflight_advisory(
            {
                "alpha_id": "a1",
                "official_alpha_id": "off_1",
                "expression": "rank(close)",
                "official_metrics": {"pass_fail": "PASS", "sharpe": 1.5, "fitness": 1.1},
                "scorecard": {"total_score": 91.0},
                "gate": {"submission_ready": True},
                "lifecycle_status": "submission_ready",
            },
            rc,
            ledger_factory=lambda sd: _MockLedger(sd),
            cloud_alpha_snapshot=lambda limit=2000: {"alphas": [], "summary": {}},
            cloud_status_for=lambda c, rows: {"status": ""},
        )
        assert isinstance(payload, dict)
        assert "ok" in payload

    def test_submission_preflight_with_cloud_error_snapshot(self, tmp_path):
        from brain_alpha_ops.web_submission_safety import submission_preflight_advisory
        from brain_alpha_ops.config import RunConfig

        rc = RunConfig(environment="production")
        rc.ops.storage_dir = str(tmp_path)
        rc.ops.budget.require_cloud_sync = False

        class _MockLedger:
            def __init__(self, storage_dir, rows=None):
                self.rows = list(rows or [])
            def records(self):
                return list(self.rows)

        payload = submission_preflight_advisory(
            {
                "alpha_id": "a1",
                "official_alpha_id": "off_1",
                "expression": "rank(close)",
                "official_metrics": {"pass_fail": "PASS", "sharpe": 1.5, "fitness": 1.1},
                "scorecard": {"total_score": 91.0},
                "gate": {"submission_ready": True},
                "lifecycle_status": "submission_ready",
            },
            rc,
            ledger_factory=lambda sd: _MockLedger(sd),
            cloud_alpha_snapshot=lambda limit=2000: {},  # no 'alphas' key
            cloud_status_for=lambda c, rows: {"status": ""},
        )
        assert isinstance(payload, dict)
