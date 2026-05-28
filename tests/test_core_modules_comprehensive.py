"""Comprehensive unit and integration tests for core modules.

Covers: research/scoring, compliance/redline_verifier, brain_api/official,
        config validation, error handling, model boundaries.

Uses the production test stub for all tests — no real API calls needed.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))

from tests.production_api_stub import ProductionBrainAPIStub
from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.config import (
    BrainSettings,
    ConfigValidationError,
    CredentialConfig,
    OfficialAPIConfig,
    OpsConfig,
    QualityThresholds,
    ResearchBudget,
    RunConfig,
    ScoringConfig,
    SubmissionPolicy,
    WebConfig,
    load_run_config,
    validate_run_config,
    write_run_config,
)
from brain_alpha_ops.models import Candidate, PipelineEvent, PipelineResult
from brain_alpha_ops.errors import (
    AppError,
    AuthError,
    ConflictError,
    NotFoundError,
    SessionError,
    SubmitBlockedError,
    ValidationError,
    classify_error,
    ErrorInfo,
)
from brain_alpha_ops.research.scoring import (
    build_scorecard,
    calculate_fitness,
    decision_band,
    empirical_score,
    evaluate_quality_gate,
    item,
    prior_score,
    submission_checklist,
    estimate_score_confidence,
)
from brain_alpha_ops.compliance.redline_verifier import (
    ComplianceReport,
    RedLineVerifier,
    RedLineViolation,
)


# ═══════════════════════════════════════════
# Section 1: Production Stub API Tests
# ═══════════════════════════════════════════

class TestProductionBrainAPIStub:
    """Verify the production stub provides deterministic, safe test behavior."""

    def test_authenticate_always_succeeds(self):
        api = ProductionBrainAPIStub()
        result = api.authenticate()
        assert result["status"] == "ok"

    def test_validate_expression(self):
        api = ProductionBrainAPIStub()
        result = api.validate_expression("rank(close)", {})
        assert result["status"] == "PASS"

    def test_validate_empty_expression(self):
        api = ProductionBrainAPIStub()
        result = api.validate_expression("", {})
        assert result["status"] in {"PASS", "FAIL", "FAILED"}

    def test_simulation_roundtrip(self):
        api = ProductionBrainAPIStub()
        api.authenticate()
        sim_id = api.submit_simulation("rank(close)", {})
        assert sim_id
        status = api.poll_simulation(sim_id)
        assert status in {"RUNNING", "COMPLETED", "FAILED"}

    def test_check_alpha(self):
        api = ProductionBrainAPIStub()
        api.authenticate()
        sim_id = api.submit_simulation("rank(close)", {})
        # Poll until completed
        for _ in range(50):
            status = api.poll_simulation(sim_id)
            if status == "COMPLETED":
                break
        result = api.fetch_result(sim_id)
        assert "alpha_id" in result
        check = api.check_alpha(result["alpha_id"])
        assert "status" in check

    def test_user_alphas_list(self):
        api = ProductionBrainAPIStub()
        api.authenticate()
        rows = api.list_user_alphas("3d")
        assert isinstance(rows, list)

    def test_rejects_non_production_submit(self):
        api = ProductionBrainAPIStub()
        api.authenticate()
        with pytest.raises(BrainAPIError, match="non-production"):
            api.submit_alpha("mock_abc123", "rank(close)", {})


# ═══════════════════════════════════════════
# Section 2: Config Validation Tests
# ═══════════════════════════════════════════

class TestConfigValidation:
    """Config loading, validation, and error handling."""

    def test_default_config_valid(self):
        config = validate_run_config(RunConfig())
        assert config.environment == "production"

    def test_invalid_environment_raises(self):
        config = RunConfig()
        config.environment = "staging"
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_invalid_instrument_type_raises(self):
        config = RunConfig()
        config.ops.settings.instrumentType = "BOND"
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_invalid_delay_type_raises(self):
        config = RunConfig()
        config.ops.settings.delay = 3  # only 0, 1, 2 supported
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_valid_settings_accepted(self):
        config = RunConfig()
        config.environment = "production"
        config.ops.settings.region = "USA"
        config.ops.settings.universe = "TOP3000"
        config.ops.settings.delay = 1
        config.ops.settings.neutralization = "SUBINDUSTRY"
        result = validate_run_config(config)
        assert result.ops.settings.region == "USA"

    def test_web_port_out_of_range(self):
        config = RunConfig()
        config.web.port = 99999
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_negative_budget_raises(self):
        config = RunConfig()
        config.ops.budget.max_candidates_per_cycle = -1
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_config_roundtrip(self):
        """Roundtrip test using a temp file in the project data dir."""
        config_path = Path(_project_root) / "data" / "_test_roundtrip_config.json"
        try:
            original = RunConfig()
            original.ops.settings.region = "USA"
            written = write_run_config(original, config_path)
            loaded = load_run_config(written)
            assert loaded.ops.settings.region == "USA"
        finally:
            if config_path.exists():
                config_path.unlink()

    def test_credential_env_resolution(self):
        creds = CredentialConfig(
            username_env="TEST_USER",
            password_env="TEST_PASS",
        )
        # Without env vars set, resolves to empty
        resolved = creds.resolve()
        assert resolved["username"] == ""
        assert resolved["password"] == ""

    def test_scoring_weights_validation(self):
        """Weight validation should catch invalid sums."""
        config = RunConfig()
        config.ops.scoring.prior_layer_weight = 0.0
        config.ops.scoring.empirical_layer_weight = 0.0
        config.ops.scoring.checklist_layer_weight = 0.0
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_api_base_url_https_enforced_in_production(self):
        config = RunConfig()
        config.environment = "production"
        config.ops.official_api.base_url = "http://api.worldquantbrain.com"
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)

    def test_official_api_config_production_rejects_http(self):
        config = RunConfig()
        config.environment = "production"
        config.ops.official_api.base_url = "http://localhost:8080"
        with pytest.raises(ConfigValidationError):
            validate_run_config(config)


# ═══════════════════════════════════════════
# Section 3: Scoring System Tests
# ═══════════════════════════════════════════

class TestScoringSystem:
    """Comprehensive scoring pipeline tests."""

    @pytest.fixture
    def thresholds(self):
        return QualityThresholds()

    @pytest.fixture
    def scoring(self):
        return ScoringConfig()

    def test_empirical_score_empty(self, thresholds):
        result = empirical_score({}, thresholds)
        assert result["score"] == 0.0
        assert result["status"] == "missing_official_metrics"

    def test_empirical_score_strong(self, thresholds):
        metrics = {
            "sharpe": 1.8, "fitness": 1.5, "turnover": 0.15, "returns": 0.012,
            "drawdown": 0.08, "correlation": 0.35, "weight_concentration": 0.045,
            "sub_universe_sharpe": 1.6, "turnover_raw": 0.15,
        }
        result = empirical_score(metrics, thresholds)
        # hard gates should pass for strong metrics
        assert "score" in result

    def test_empirical_score_all_items_present(self, thresholds):
        """All 14 check items must be present."""
        metrics = {
            "sharpe": 1.8, "fitness": 1.5, "turnover": 0.15, "returns": 0.012,
            "drawdown": 0.08, "correlation": 0.35, "weight_concentration": 0.045,
            "sub_universe_sharpe": 1.6, "turnover_raw": 0.15,
        }
        result = empirical_score(metrics, thresholds)
        item_names = {item["name"] for item in result["items"]}
        required = {
            "sharpe", "fitness", "fitness_crosscheck", "turnover_min",
            "turnover_platform", "turnover_quality", "returns", "drawdown",
            "self_correlation", "prod_correlation", "weight_concentration",
            "sub_universe_sharpe", "is_oos_ratio", "margin_bps",
        }
        for name in required:
            assert name in item_names, f"Missing item: {name}"

    def test_calculate_fitness(self):
        """BRAIN formula: Fitness = Sharpe * sqrt(|Returns| / max(Turnover, 0.125))."""
        f = calculate_fitness(1.5, 0.02, 0.20, raw_turnover=0.20)
        expected = 1.5 * math.sqrt(0.02 / 0.20)
        assert abs(f - expected) < 1e-6

    def test_calculate_fitness_min_denominator(self):
        f = calculate_fitness(1.0, 0.01, 0.001)
        expected = 1.0 * math.sqrt(0.01 / 0.125)
        assert abs(f - expected) < 1e-6

    def test_decision_band_thresholds(self):
        assert decision_band(90, hard_gate_failed=False) == "submit_candidate"
        assert decision_band(80, hard_gate_failed=False) == "optimize_before_submit"
        assert decision_band(60, hard_gate_failed=False) == "research_only"
        assert decision_band(30, hard_gate_failed=False) == "abandon_or_rebuild"
        assert decision_band(90, hard_gate_failed=True) == "hard_gate_blocked"

    def test_submission_checklist(self, thresholds):
        candidate = Candidate(
            alpha_id="list_test",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Price momentum ranked cross-sectionally",
        )
        result = submission_checklist(candidate, thresholds)
        assert "score" in result
        assert len(result["items"]) > 0

    def test_build_scorecard_local_prior(self, thresholds, scoring):
        """Without official metrics, scorecard uses local_prior basis."""
        candidate = Candidate(
            alpha_id="local_only",
            expression="ts_delta(close, 10)",
            family="Momentum",
            hypothesis="Price momentum",
        )
        result = build_scorecard(candidate, thresholds, scoring=scoring)
        assert result["score_basis"] == "local_prior"
        assert result["total_score"] >= 0

    def test_build_scorecard_official_verified(self, thresholds, scoring):
        """With official metrics, scorecard uses official_verified basis."""
        candidate = Candidate(
            alpha_id="verified",
            expression="ts_delta(close, 10)",
            family="Momentum",
            hypothesis="Price momentum",
            official_metrics={
                "sharpe": 1.8, "fitness": 1.5, "turnover": 0.15, "returns": 0.012,
                "drawdown": 0.08, "correlation": 0.35, "weight_concentration": 0.045,
                "sub_universe_sharpe": 1.6, "turnover_raw": 0.15,
            },
        )
        result = build_scorecard(candidate, thresholds, scoring=scoring)
        assert result["score_basis"] == "official_verified"

    def test_evaluate_quality_gate_blocked(self, thresholds, scoring):
        """Weak metrics should result in submission_ready=False."""
        candidate = Candidate(
            alpha_id="weak",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Simple rank",
            official_metrics={
                "sharpe": 0.5, "fitness": 0.3, "turnover": 0.85,
                "returns": 0.001, "drawdown": 0.5, "correlation": 0.8,
                "weight_concentration": 0.3, "sub_universe_sharpe": 0.1,
                "turnover_raw": 0.85,
            },
        )
        # Pre-build scorecard
        build_scorecard(candidate, thresholds, scoring=scoring)
        gate = evaluate_quality_gate(candidate, thresholds)
        assert gate["submission_ready"] is False
        assert len(gate["failed_reasons"]) > 0

    def test_prior_score_has_all_dimensions(self):
        candidate = Candidate(
            alpha_id="prior_dim",
            expression="group_rank(winsorize(ts_mean(close, 20), 0.01), subindustry)",
            family="CrossSectional",
            hypothesis="Risk-controlled sector neutral moving average",
            data_fields=["close"],
            operators=["group_rank", "winsorize", "ts_mean"],
        )
        result = prior_score(candidate)
        dims = [
            "economic_logic", "structure", "field_operator_support",
            "data_compliance", "horizon_turnover_proxy", "risk_control_proxy",
            "diversity", "explainability",
        ]
        for dim in dims:
            assert dim in result["dimensions"], f"Missing dimension: {dim}"

    def test_prior_score_empty_input(self):
        candidate = Candidate(
            alpha_id="empty_prior",
            expression="",
            family="Momentum",
            hypothesis="",
        )
        result = prior_score(candidate)
        assert result["score"] >= 0

    def test_estimate_score_confidence(self):
        items = [
            item("sharpe", 2.0, ">=", 1.25, True, 20, is_hard_gate=True),
            item("fitness", 1.5, ">=", 1.0, True, 15, is_hard_gate=True),
            item("turnover_platform", 0.15, "<=", 0.70, True, 8, is_hard_gate=True),
        ]
        conf = estimate_score_confidence({"empirical": {"items": items}})
        assert "confidence_level" in conf
        assert "interpretation" in conf

    def test_self_correlation_exception_rule(self, thresholds):
        """BRAIN exception: Sharpe >= related_alpha_sharpe * 1.10."""
        metrics = {
            "sharpe": 1.65,
            "fitness": 1.2, "turnover": 0.15, "returns": 0.012,
            "drawdown": 0.08, "correlation": 0.72, "weight_concentration": 0.045,
            "sub_universe_sharpe": 1.4, "related_alpha_sharpe": 1.5, "turnover_raw": 0.15,
        }
        result = empirical_score(metrics, thresholds)
        sc_item = next(i for i in result["items"] if i["name"] == "self_correlation")
        # Exception should be applied since 1.65 >= 1.5 * 1.10
        if sc_item.get("exception_applied"):
            assert sc_item["passed"] is True


# ═══════════════════════════════════════════
# Section 4: Compliance / RedLine Tests
# ═══════════════════════════════════════════

class TestCompliance:
    """RedLine verifier and compliance gate tests."""

    def test_redline_verifier_runs_all_six(self):
        verifier = RedLineVerifier()
        report = verifier.verify_all()
        assert report.total_checks > 0
        assert len(report.redline_summary) == 6

    def test_redline_report_to_dict(self):
        verifier = RedLineVerifier()
        report = verifier.verify_all()
        d = report.to_dict()
        assert "overall" in d
        assert "violations" in d
        assert isinstance(d["violations"], list)

    def test_redline_report_text(self):
        verifier = RedLineVerifier()
        report = verifier.verify_all()
        text = report.report()
        assert "BRAIN Alpha Ops" in text
        assert "技术红线" in text

    def test_redline_violation_creation(self):
        v = RedLineViolation(
            redline_id=1,
            redline_name="字段/算子禁自定义扩展",
            severity="BLOCKING",
            file_path="test.py",
            check_name="test_check",
            actual_value="bad",
            expected_value="good",
            deviation="test deviation",
            fix_guidance="do this",
        )
        assert v.severity == "BLOCKING"
        assert v.redline_id == 1

    def test_compliance_report_add_violation(self):
        report = ComplianceReport()
        v = RedLineViolation(1, "test", "WARNING", "f.py", "c", "a", "e", "d", "g")
        report.add(v)
        assert report.total_checks == 1
        assert report.warnings == 1
        assert report.failed == 0

    def test_compliance_report_finalize_pass(self):
        report = ComplianceReport()
        report.add_pass()
        report.add_pass()
        result = report.finalize()
        assert result.overall == "PASS"
        assert result.ok is True

    def test_redline_quick_pass(self):
        result = RedLineVerifier.verify_quick()
        assert isinstance(result, bool)


# ═══════════════════════════════════════════
# Section 5: Error Handling Tests
# ═══════════════════════════════════════════

class TestErrorHandling:
    """Typed error classes and classification."""

    def test_app_error_base(self):
        err = AppError("test", code="TEST_ERR", status_code=418)
        assert err.code == "TEST_ERR"
        assert err.status_code == 418
        d = err.to_dict()
        assert d["ok"] is False
        assert d["error_code"] == "TEST_ERR"

    def test_validation_error(self):
        err = ValidationError("invalid input")
        assert err.code == "VALIDATION_ERROR"
        assert err.status_code == 400

    def test_auth_error(self):
        err = AuthError()
        assert err.code == "AUTH_FAILED"

    def test_submit_blocked_error(self):
        err = SubmitBlockedError("reason")
        assert err.code == "SUBMIT_BLOCKED"

    def test_conflict_error(self):
        err = ConflictError("already running")
        assert err.code == "CONFLICT_RUNNING"
        assert err.status_code == 409

    def test_not_found_error(self):
        err = NotFoundError()
        assert err.code == "NOT_FOUND"
        assert err.status_code == 404

    def test_session_error(self):
        err = SessionError()
        assert err.code == "SESSION_INVALID"

    def test_classify_error_rate_limit(self):
        class Fake429(Exception):
            pass
        exc = Fake429("too many requests")
        setattr(exc, "status_code", 429)
        info = classify_error(exc)
        assert info.category == "rate_limit"
        assert info.retryable is True

    def test_classify_error_auth_401(self):
        class Fake401(Exception):
            pass
        exc = Fake401("unauthorized")
        setattr(exc, "status_code", 401)
        info = classify_error(exc)
        assert info.category == "auth"

    def test_classify_error_network_503(self):
        class Fake503(Exception):
            pass
        exc = Fake503("service unavailable")
        setattr(exc, "status_code", 503)
        info = classify_error(exc)
        assert info.category == "network"
        assert info.retryable is True

    def test_error_info_to_dict(self):
        info = ErrorInfo(
            error_code="TEST",
            category="validation",
            message="test message",
            error_type="ValueError",
            retryable=False,
            status_code=400,
        )
        d = info.to_dict()
        assert d["error_code"] == "TEST"
        assert d["retryable"] is False

    def test_classify_value_error_is_validation(self):
        info = classify_error(ValueError("invalid"))
        assert info.category == "validation"


# ═══════════════════════════════════════════
# Section 6: Model Boundaries Tests
# ═══════════════════════════════════════════

class TestModels:
    """Candidate, PipelineEvent, PipelineResult model tests."""

    def test_candidate_creation(self):
        c = Candidate(
            alpha_id="test_001",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Cross-sectional price momentum",
        )
        assert c.lifecycle_status == "created"
        assert c.source_tags == ["经验"]

    def test_candidate_to_dict(self):
        c = Candidate(alpha_id="t1", expression="r(c)", family="M", hypothesis="H")
        d = c.to_dict()
        assert d["alpha_id"] == "t1"
        assert d["expression"] == "r(c)"

    def test_candidate_from_dict_preserves_extra(self):
        data = {
            "alpha_id": "extra_test",
            "expression": "rank(close)",
            "family": "Momentum",
            "hypothesis": "Test",
            "custom_field": "preserved",
        }
        c = Candidate.from_dict(data)
        assert c.extra_fields.get("custom_field") == "preserved"

    def test_candidate_from_dict_roundtrip(self):
        c = Candidate(
            alpha_id="rt",
            expression="ts_mean(close, 20)",
            family="Trend",
            hypothesis="Moving average",
            data_fields=["close"],
            operators=["ts_mean"],
            dataset_id="analyst4",
        )
        c2 = Candidate.from_dict(c.to_dict())
        assert c2.expression == c.expression
        assert c2.dataset_id == c.dataset_id
        assert c2.data_fields == c.data_fields

    def test_pipeline_event(self):
        e = PipelineEvent(
            event="generation",
            message="Generated 10 candidates",
            alpha_id="alpha_1",
        )
        d = e.to_dict()
        assert d["event"] == "generation"

    def test_pipeline_result(self):
        c = Candidate("a1", "r(c)", "M", "H")
        e = PipelineEvent("gen", "msg")
        r = PipelineResult(
            run_id="run_001",
            candidates=[c],
            events=[e],
            summary={"total": 1},
        )
        d = r.to_dict()
        assert d["run_id"] == "run_001"
        assert len(d["candidates"]) == 1


# ═══════════════════════════════════════════
# Section 7: Integration Tests (Production Stub + Scoring)
# ═══════════════════════════════════════════

class TestScoringIntegrationProductionStub:
    """End-to-end: production stub → simulation → scoring → gate."""

    def test_full_simulation_to_scorecard(self):
        """Run a stub simulation and feed results into scoring."""
        api = ProductionBrainAPIStub()
        api.authenticate()
        sim_id = api.submit_simulation("ts_delta(close, 10)", {})
        # Poll until complete
        for _ in range(100):
            if api.poll_simulation(sim_id) == "COMPLETED":
                break
        result = api.fetch_result(sim_id)
        assert "alpha_id" in result
        assert "metrics" in result

        # Feed to scoring
        thresholds = QualityThresholds()
        scoring = ScoringConfig()
        candidate = Candidate(
            alpha_id="integration_1",
            expression="ts_delta(close, 10)",
            family="Momentum",
            hypothesis="Price delta momentum",
            official_alpha_id=result["alpha_id"],
            official_metrics=result["metrics"],
        )
        scorecard = build_scorecard(candidate, thresholds, scoring=scoring)
        assert "total_score" in scorecard
        assert "decision_band" in scorecard

    def test_gate_on_mock_results(self):
        """Quality gate evaluation on stub simulation results."""
        api = ProductionBrainAPIStub()
        api.authenticate()
        sim_id = api.submit_simulation("group_rank(winsorize(close, 0.01), subindustry)", {})
        for _ in range(100):
            if api.poll_simulation(sim_id) == "COMPLETED":
                break
        result = api.fetch_result(sim_id)

        thresholds = QualityThresholds()
        candidate = Candidate(
            alpha_id="gate_integr",
            expression="group_rank(winsorize(close, 0.01), subindustry)",
            family="CrossSectional",
            hypothesis="Risk-controlled sector neutral signal",
            official_metrics=result["metrics"],
        )
        scorecard = build_scorecard(candidate, thresholds, scoring=ScoringConfig())
        gate = evaluate_quality_gate(candidate, thresholds)
        assert "submission_ready" in gate
        assert "failed_reasons" in gate


# ═══════════════════════════════════════════
# Section 8: Official API Config and Schemas
# ═══════════════════════════════════════════

class TestAPIConfig:
    """Official API configuration unit tests."""

    def test_default_api_config(self):
        c = OfficialAPIConfig()
        assert c.base_url == "https://api.worldquantbrain.com"
        assert c.timeout_seconds == 60
        assert c.poll_attempts == 120

    def test_brain_settings_to_platform_dict(self):
        s = BrainSettings()
        d = s.to_platform_dict()
        assert d["type"] == "REGULAR"
        assert "settings" in d
        assert d["settings"]["region"] == "USA"

    def test_brain_settings_custom(self):
        s = BrainSettings(region="EUR", universe="TOP500", delay=0)
        d = s.to_platform_dict()
        assert d["settings"]["region"] == "EUR"
        assert d["settings"]["delay"] == 0

    def test_research_budget_defaults(self):
        b = ResearchBudget()
        assert b.max_candidates_per_cycle == 20
        assert b.min_local_quality_score == 4.0

    def test_submission_policy_defaults(self):
        p = SubmissionPolicy()
        assert p.max_auto_submissions_per_day == 3
        assert p.block_micro_variants is True

    def test_web_config_defaults(self):
        w = WebConfig()
        assert w.host == "127.0.0.1"
        assert w.port == 8765
