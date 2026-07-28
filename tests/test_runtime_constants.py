"""Tests for brain_alpha_ops.runtime_constants — hardcoded safety constants."""
import os
import subprocess
import sys

from brain_alpha_ops.runtime_constants import (
    REAL_SUBMIT_DISABLED_WEB_FLOW,
    WebDefaults,
    HILDefaults,
    ScoringDefaults,
    PipelineDefaults,
    real_submit_test_override_enabled,
)


class TestSubmissionSafety:
    def test_real_submit_disabled_is_always_true(self):
        """REAL_SUBMIT_DISABLED_WEB_FLOW must ALWAYS be True — this is the safety kill switch."""
        assert REAL_SUBMIT_DISABLED_WEB_FLOW is True

    def test_real_submit_disabled_is_final(self):
        """The constant should be a Final type annotation (static check)."""
        # At runtime, just verify it's a bool True
        assert isinstance(REAL_SUBMIT_DISABLED_WEB_FLOW, bool)

    def test_real_submit_test_override_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("BRAIN_ALPHA_FORCE_REAL_SUBMIT", raising=False)
        monkeypatch.delenv("BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS", raising=False)

        assert real_submit_test_override_enabled() is False

    def test_real_submit_test_override_requires_both_envs(self, monkeypatch):
        # F-005: only one approval env set -> False
        monkeypatch.setenv("BRAIN_ALPHA_FORCE_REAL_SUBMIT", "1")
        monkeypatch.delenv("BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS", raising=False)
        assert real_submit_test_override_enabled() is False

        # F-005: both envs set AND called from within pytest -> True
        monkeypatch.setenv("BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS", "1")
        assert real_submit_test_override_enabled() is True

    def test_real_submit_test_override_rejects_non_pytest_call_stack(self):
        # F-005: env spoofing from a non-pytest process must NOT bypass the
        # guard. Spawn a plain ``python -c`` subprocess (no pytest frame on
        # the call stack) with both approval envs set and verify the override
        # returns False. This is the regression test for the env-forge flaw.
        code = (
            "from brain_alpha_ops.runtime_constants import "
            "real_submit_test_override_enabled as f;"
            "raise SystemExit(0 if f() is False else 1)"
        )
        env = dict(os.environ)
        env["BRAIN_ALPHA_FORCE_REAL_SUBMIT"] = "1"
        env["BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS"] = "1"
        env.pop("PYTEST_CURRENT_TEST", None)
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
        )
        assert result.returncode == 0, (
            f"non-pytest process should NOT bypass submit guard (F-005); "
            f"stderr={result.stderr.decode(errors='replace')}"
        )


class TestWebDefaults:
    def test_local_only_binding(self):
        assert WebDefaults.HOST == "127.0.0.1"

    def test_reasonable_body_limit(self):
        assert WebDefaults.MAX_BODY_BYTES > 0

    def test_port_is_well_known(self):
        assert WebDefaults.PORT == 8765

    def test_sse_duration_capped(self):
        """SSE streams must have a hard lifetime cap."""
        assert WebDefaults.MAX_SSE_DURATION > 0
        assert WebDefaults.MAX_SSE_DURATION <= 3600  # max 1 hour


class TestHILDefaults:
    def test_simulation_confirmation_required(self):
        """HIL gate must be enabled by default."""
        assert HILDefaults.SIMULATION_CONFIRM_REQUIRED is True

    def test_confirmation_field_name_is_stable(self):
        """The confirmation field name is a contract with the frontend."""
        assert HILDefaults.SIMULATION_CONFIRM_FIELD == "confirm_simulation"

    def test_error_code_is_non_empty(self):
        assert len(HILDefaults.SIMULATION_CONFIRM_ERROR_CODE) > 0


class TestScoringDefaults:
    def test_weights_sum_approximately_one(self):
        total = (
            ScoringDefaults.DEFAULT_PRIOR_LAYER_WEIGHT
            + ScoringDefaults.DEFAULT_EMPIRICAL_LAYER_WEIGHT
            + ScoringDefaults.DEFAULT_CHECKLIST_LAYER_WEIGHT
        )
        assert abs(total - 1.0) < 0.01

    def test_thresholds_monotonic(self):
        assert (
            ScoringDefaults.DEFAULT_SUBMIT_THRESHOLD
            > ScoringDefaults.DEFAULT_OPTIMIZE_THRESHOLD
            > ScoringDefaults.DEFAULT_RESEARCH_THRESHOLD
        )


class TestPipelineDefaults:
    def test_defaults_are_positive(self):
        assert PipelineDefaults.DEFAULT_MAX_CANDIDATES_PER_CYCLE > 0
        assert PipelineDefaults.DEFAULT_MAX_VALIDATIONS_PER_CYCLE > 0
        assert PipelineDefaults.DEFAULT_MIN_LOCAL_QUALITY > 0
