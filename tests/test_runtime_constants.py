"""Tests for brain_alpha_ops.runtime_constants — hardcoded safety constants."""
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
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

        assert real_submit_test_override_enabled() is False

    def test_real_submit_test_override_requires_all_test_approval_env(self, monkeypatch):
        monkeypatch.setenv("BRAIN_ALPHA_FORCE_REAL_SUBMIT", "1")
        monkeypatch.setenv("BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS", "1")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert real_submit_test_override_enabled() is False

        monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_runtime_constants.py::test_case (call)")
        assert real_submit_test_override_enabled() is True


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
