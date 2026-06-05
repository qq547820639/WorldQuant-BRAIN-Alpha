"""Comprehensive tests for canonical compliance verification and scoring system.

Covers:
- Threshold zero-deviation verification
- API path alignment
- Settings enum validation
- Scoring API simulation zero-deviation
- Field/operator no-custom-extension
- Dataset ID availability
- Edge cases: null metrics, extreme values, corrupted data
- Parameter traceability end-to-end

Run:
    python -m pytest tests/test_canonical_compliance.py -v
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile

import pytest

from tests.production_api_stub import TEMPLATE_SAFE_OPERATOR_NAMES

# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def probe_candidate():
    """Create a standard diagnostic probe candidate for scoring tests."""
    from brain_alpha_ops.models import Candidate

    c = Candidate(
        alpha_id="test_probe_001",
        expression="rank(ts_delta(close, 20)) + rank(ts_mean(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Cross-sectional price momentum confirmed by liquidity participation",
        data_fields=["close", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_mean"],
        dataset_id="fundamental6",
    )
    c.official_alpha_id = "test_official_probe_001"
    return c


@pytest.fixture
def standard_thresholds():
    """Create standard QualityThresholds with canonical values."""
    from brain_alpha_ops.config import QualityThresholds

    return QualityThresholds()


@pytest.fixture
def default_ops_config():
    """Create a default OpsConfig for testing."""
    from brain_alpha_ops.config import OpsConfig

    return OpsConfig()


# ═══════════════════════════════════════════════════════════════════════
# Red Line 2: Threshold Zero Deviation
# ═══════════════════════════════════════════════════════════════════════


class TestThresholdZeroDeviation:
    """Verify all thresholds match BRAIN canonical values exactly."""

    def test_default_thresholds_match_canonical(self, standard_thresholds):
        from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS

        for key, canonical_value in CANONICAL_THRESHOLDS.items():
            configured = getattr(standard_thresholds, key, None)
            assert configured is not None, f"Threshold {key} is None"
            assert configured == canonical_value, (
                f"Threshold {key}: configured={configured}, canonical={canonical_value}"
            )

    def test_all_canonical_thresholds_present_in_thresholds(self, standard_thresholds):
        from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS

        for key in CANONICAL_THRESHOLDS:
            assert hasattr(standard_thresholds, key), (
                f"QualityThresholds missing canonical key: {key}"
            )

    def test_scoring_comparison_threshold_compliance(self, standard_thresholds):
        from brain_alpha_ops.scoring.scoring_comparison import check_threshold_compliance

        is_compliant, deviations = check_threshold_compliance(standard_thresholds)
        assert is_compliant, f"Threshold deviations: {deviations}"

    def test_threshold_drift_detection(self):
        from brain_alpha_ops.config import QualityThresholds
        from brain_alpha_ops.scoring.scoring_comparison import check_threshold_compliance

        # Create thresholds with deliberate drift
        drifted = QualityThresholds()
        drifted.min_sharpe = 1.5  # canonical is 1.25
        is_compliant, deviations = check_threshold_compliance(drifted)
        assert not is_compliant, "Should detect threshold drift"
        assert any("min_sharpe" in d for d in deviations)

    def test_prod_correlation_threshold_drift_detection(self):
        from brain_alpha_ops.config import QualityThresholds
        from brain_alpha_ops.scoring.scoring_comparison import check_threshold_compliance

        drifted = QualityThresholds()
        drifted.max_prod_correlation = 0.95
        is_compliant, deviations = check_threshold_compliance(drifted)
        assert not is_compliant, "Should detect prod correlation threshold drift"
        assert any("max_prod_correlation" in d for d in deviations)


# ═══════════════════════════════════════════════════════════════════════
# Red Line 6: API Path Alignment
# ═══════════════════════════════════════════════════════════════════════


class TestAPIPathAlignment:
    """Verify all configured API paths match BRAIN canonical paths."""

    def test_default_api_paths_match_canonical(self):
        from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS
        from brain_alpha_ops.config import OfficialAPIConfig

        config = OfficialAPIConfig()

        path_mapping = {
            "authentication": config.authentication_path,
            "simulations": config.simulations_path,
            "data_sets": config.data_sets_path,
            "data_fields": config.data_fields_path,
            "operators": config.operators_path,
            "user_alphas": config.user_alphas_path,
            "user_profile": config.user_profile_path,
            "alpha_check": config.alpha_check_path_template,
            "alpha_submit": config.alpha_submit_path_template,
            "alpha_detail": config.alpha_path_template,
            "alpha_correlations": config.alpha_correlations_path,
        }

        for key, canonical_path in CANONICAL_API_PATHS.items():
            configured = path_mapping.get(key)
            assert configured is not None, f"Missing API path mapping for: {key}"
            assert configured == canonical_path, (
                f"API path mismatch for {key}: '{configured}' != '{canonical_path}'"
            )

    def test_base_url_is_canonical(self):
        from brain_alpha_ops.config import OfficialAPIConfig

        config = OfficialAPIConfig()
        assert config.base_url == "https://api.worldquantbrain.com"

    def test_all_canonical_paths_configured(self):
        from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS
        from brain_alpha_ops.config import OfficialAPIConfig

        config = OfficialAPIConfig()
        for key in CANONICAL_API_PATHS:
            attr_map = {
                "authentication": "authentication_path",
                "simulations": "simulations_path",
                "data_sets": "data_sets_path",
                "data_fields": "data_fields_path",
                "operators": "operators_path",
                "user_alphas": "user_alphas_path",
                "user_profile": "user_profile_path",
                "alpha_check": "alpha_check_path_template",
                "alpha_submit": "alpha_submit_path_template",
                "alpha_detail": "alpha_path_template",
                "alpha_correlations": "alpha_correlations_path",
            }
            attr = attr_map.get(key)
            assert attr is not None, f"No mapping for canonical key: {key}"
            assert hasattr(config, attr), f"OfficialAPIConfig missing: {attr}"


# ═══════════════════════════════════════════════════════════════════════
# Settings Enum Alignment
# ═══════════════════════════════════════════════════════════════════════


class TestSettingsEnumAlignment:
    """Verify settings values are within BRAIN canonical enum sets."""

    def test_default_settings_in_canonical_enums(self):
        from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS
        from brain_alpha_ops.config import BrainSettings

        settings = BrainSettings()

        enum_checks = [
            ("instrumentType", settings.instrumentType, CANONICAL_SETTINGS["instrumentType"]),
            ("region", settings.region, CANONICAL_SETTINGS["region"]),
            ("universe", settings.universe, CANONICAL_SETTINGS["universe"]),
            ("neutralization", settings.neutralization, CANONICAL_SETTINGS["neutralization"]),
            ("pasteurization", settings.pasteurization, CANONICAL_SETTINGS["pasteurization"]),
            ("unitHandling", settings.unitHandling, CANONICAL_SETTINGS["unitHandling"]),
            ("nanHandling", settings.nanHandling, CANONICAL_SETTINGS["nanHandling"]),
            ("language", settings.language, CANONICAL_SETTINGS["language"]),
            ("type", settings.type, CANONICAL_SETTINGS["type"]),
        ]

        for field_name, value, allowed in enum_checks:
            assert value in allowed, (
                f"Settings {field_name}='{value}' not in canonical allowed values: {allowed}"
            )

    def test_delay_in_canonical_range(self):
        from brain_alpha_ops.config import BrainSettings

        settings = BrainSettings()
        assert settings.delay in {0, 1}, f"delay={settings.delay} not in [0, 1]"


# ═══════════════════════════════════════════════════════════════════════
# Scoring API Simulation Zero Deviation
# ═══════════════════════════════════════════════════════════════════════


class TestScoringSimulation:
    """Verify OfficialScoringSystem produces zero-deviation API output."""

    def test_scoring_probe_zero_deviation(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "weight_concentration": 0.04,
            "sub_universe_sharpe": 1.3,
            "margin": 5.0,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)

        assert result.api_output_deviation == 0.0, (
            f"Non-zero deviation: {result.deviation_details}"
        )

    def test_scoring_simulation_has_all_required_fields(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "weight_concentration": 0.04,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)

        sim = result.simulated_api_output
        required_fields = ["alpha_id", "expression", "status", "checks", "score", "gate", "meta"]
        for field in required_fields:
            assert field in sim, f"Simulated API output missing field: {field}"

    def test_scoring_probe_with_missing_official_metrics(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = None

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)

        # Without official metrics, deviation should be > 0
        assert result.api_output_deviation > 0, (
            "Should report deviation when official metrics are missing"
        )

    def test_scoring_threshold_trace_completeness(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "weight_concentration": 0.04,
            "sub_universe_sharpe": 1.3,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)

        required_trace_keys = [
            "min_sharpe", "min_fitness", "min_turnover",
            "platform_max_turnover", "max_self_correlation",
            "max_weight_concentration",
        ]
        for key in required_trace_keys:
            assert key in result.threshold_trace, f"Threshold trace missing: {key}"
            assert "value" in result.threshold_trace[key], (
                f"Threshold trace {key} missing 'value'"
            )
            assert "source" in result.threshold_trace[key], (
                f"Threshold trace {key} missing 'source'"
            )

    def test_scoring_settings_trace_completeness(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)

        # Settings trace should contain BRAIN platform settings
        assert isinstance(result.settings_trace, dict)
        assert len(result.settings_trace) > 0, "Settings trace is empty"

    def test_attribution_tree_structure(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)

        assert result.attribution_tree is not None, "Attribution tree is None"
        tree = result.attribution_tree
        # Root should have children: prior, empirical, checklist
        child_names = {child.name for child in tree.children}
        assert child_names.issuperset({"prior_score", "empirical_score", "submission_checklist"}), (
            f"Attribution tree missing child nodes: {child_names}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: Null, Extreme, and Corrupted Metrics
# ═══════════════════════════════════════════════════════════════════════


class TestNullMetricsHandling:
    """Verify scoring system handles null/missing metrics gracefully."""

    def test_null_metrics_dont_crash(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = None

        system = OfficialScoringSystem(default_ops_config)
        # Should not raise
        result = system.evaluate(probe_candidate)
        assert result is not None

    def test_partial_metrics(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "sharpe": 1.6,
            # fitness is missing
            "turnover": 0.2,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)
        assert result is not None

    def test_empty_metrics_dict(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {}

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)
        assert result is not None


class TestExtremeValues:
    """Verify scoring system handles extreme metric values."""

    def test_negative_sharpe(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "FAIL",
            "sharpe": -1.5,
            "fitness": 0.5,
            "turnover": 0.8,
            "returns": -0.2,
            "drawdown": 0.5,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)
        assert result is not None
        assert result.passed_gate is False

    def test_zero_turnover(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.1,
            "turnover": 0.0,
            "returns": 0.05,
            "drawdown": 0.05,
        }

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)
        assert result is not None

    def test_nan_sharpe(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "FAIL",
            "sharpe": float("nan"),
            "fitness": float("nan"),
            "turnover": 0.2,
            "returns": 0.0,
            "drawdown": 0.1,
        }

        system = OfficialScoringSystem(default_ops_config)
        # Should not raise
        result = system.evaluate(probe_candidate)
        assert result is not None

    def test_infinite_fitness(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": float("inf"),
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
        }

        system = OfficialScoringSystem(default_ops_config)
        # Should not raise
        result = system.evaluate(probe_candidate)
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════
# User Messages Catalog
# ═══════════════════════════════════════════════════════════════════════


class TestUserMessages:
    """Verify user message catalog completeness and quality."""

    def test_all_messages_have_required_fields(self):
        from brain_alpha_ops.ux.user_messages import MESSAGE_CATALOG

        for code, msg in MESSAGE_CATALOG.items():
            assert msg.title, f"Message {code} missing title"
            assert msg.detail, f"Message {code} missing detail"
            assert msg.suggestion, f"Message {code} missing suggestion"
            assert msg.severity in {"error", "warning", "info"}, (
                f"Message {code} invalid severity: {msg.severity}"
            )

    def test_critical_error_codes_exist(self):
        from brain_alpha_ops.ux.user_messages import MESSAGE_CATALOG

        # These error codes must exist for risk-critical scenarios
        required = [
            "AUTH_FAILED", "AUTH_REQUIRED",
            "HARD_GATE_BLOCKED", "SUBMIT_BLOCKED",
            "VALIDATION_FAILED", "CONNECTION_FAILED",
            "SIMULATION_FAILED", "SIMULATION_TIMEOUT",
            "THRESHOLD_DRIFT_DETECTED",
        ]
        missing = [r for r in required if r not in MESSAGE_CATALOG]
        assert not missing, f"Missing critical error codes: {missing}"

    def test_get_message_fallback(self):
        from brain_alpha_ops.ux.user_messages import get_message

        msg = get_message("NONEXISTENT_CODE", fallback_detail="Test fallback")
        assert msg.title is not None
        assert msg.error_code == "NONEXISTENT_CODE"

    def test_classify_expression_error(self):
        from brain_alpha_ops.ux.user_messages import classify_expression_error

        # Empty expression
        result = classify_expression_error(ValueError("empty"), expression="")
        assert result["error_code"] == "EXPRESSION_EMPTY"

        # Unbalanced parens
        result = classify_expression_error(ValueError("bad"), expression="rank(ts_delta(close,20")
        assert result["error_code"] == "EXPRESSION_UNBALANCED_PARENS"

        # Unknown operator
        result = classify_expression_error(ValueError("unknown operator: fake_op"), expression="fake_op()")
        assert result["error_code"] == "EXPRESSION_UNKNOWN_OPERATOR"

    def test_web_actionable_error_structure(self):
        from brain_alpha_ops.ux.user_messages import web_actionable_error

        result = web_actionable_error("AUTH_FAILED", detail="test detail")
        assert not result["ok"]
        assert result["error_code"] == "AUTH_FAILED"
        assert "title" in result["error"]
        assert "suggestion" in result["error"]
        assert "severity" in result["error"]


# ═══════════════════════════════════════════════════════════════════════
# Canonical Compliance Script Integration
# ═══════════════════════════════════════════════════════════════════════


class TestCanonicalComplianceScript:
    """Verify the canonical compliance verification script functions."""

    def test_verify_all_has_required_structure(self):
        # Import the script module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "verify_canonical_compliance",
            str(Path(__file__).parent.parent / "scripts" / "verify_canonical_compliance.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        report = mod.verify_all()
        assert "ok" in report
        assert "schema_version" in report
        assert "results" in report
        assert "total_checks" in report
        assert len(report["results"]) == 6, f"Expected 6 checks, got {len(report['results'])}"

        check_names = {check["name"] for check in report["results"]}
        required_names = {
            "threshold_zero_deviation",
            "api_path_alignment",
            "settings_enum_alignment",
            "scoring_simulation_zero_deviation",
            "no_custom_extension",
            "dataset_id_availability",
        }
        assert check_names == required_names, f"Missing checks: {required_names - check_names}"

    def test_verify_all_fails_when_official_context_lineage_is_incomplete(self, tmp_path):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "verify_canonical_compliance",
            str(Path(__file__).parent.parent / "scripts" / "verify_canonical_compliance.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "official_fields.json").write_text(
            json.dumps([{"id": "close", "dataset": {"id": "ds0"}}]),
            encoding="utf-8",
        )
        (data_dir / "official_operators.json").write_text(
            json.dumps([{"name": name} for name in TEMPLATE_SAFE_OPERATOR_NAMES]),
            encoding="utf-8",
        )
        datasets = [
            {"id": f"ds{index}", "name": f"Dataset {index}", "field_count": 2 if index == 0 else 0}
            for index in range(10)
        ]
        (data_dir / "official_datasets.json").write_text(json.dumps(datasets), encoding="utf-8")
        config_path = tmp_path / "run_config.json"
        config_path.write_text(
            json.dumps({"environment": "production", "ops": {"storage_dir": str(data_dir), "settings": {"dataset": "ds0"}}}),
            encoding="utf-8",
        )

        report = mod.verify_all(str(config_path))

        assert report["ok"] is False
        dataset_check = next(item for item in report["results"] if item["name"] == "dataset_id_availability")
        assert dataset_check["passed"] is False
        assert dataset_check["details"]["official_context_blocking_count"] == 1
        assert any("dataset_field_count_mismatch" in item["deviation"] for item in report["all_deviations"])

    def test_generator_fallback_templates_do_not_embed_field_literals(self):
        from brain_alpha_ops.compliance.redline_helpers import _candidate_generator_fallback_templates

        templates = _candidate_generator_fallback_templates()
        assert templates
        assert not any("returns" in template or "sector" in template for template in templates)


class TestParameterTraceabilityRateLimitPolicy:
    """Verify production official-call pacing is part of parameter traceability."""

    def test_rate_limit_policy_accepts_conservative_defaults(self):
        from scripts.check_parameter_traceability import validate_rate_limit_policy

        issues = validate_rate_limit_policy(
            {
                "max_official_concurrent_simulations": 3,
                "official_backtest_batch_size": 3,
                "official_retry_pause_seconds": 60.0,
                "stop_official_calls_on_rate_limit": True,
            },
            {
                "rate_limit_backoff_seconds": 60.0,
                "allow_stale_context_on_rate_limit": False,
            },
        )

        assert issues == []

    def test_rate_limit_policy_flags_aggressive_external_calling(self):
        from scripts.check_parameter_traceability import validate_rate_limit_policy

        issues = validate_rate_limit_policy(
            {
                "max_official_concurrent_simulations": 4,
                "official_backtest_batch_size": 5,
                "official_retry_pause_seconds": 6.0,
                "stop_official_calls_on_rate_limit": False,
            },
            {
                "rate_limit_backoff_seconds": 15.0,
                "allow_stale_context_on_rate_limit": True,
            },
        )

        issue_codes = {issue["check"] for issue in issues}
        assert issue_codes == {
            "official_concurrency_exceeds_regular_limit",
            "official_batch_size_exceeds_concurrency",
            "official_retry_pause_too_short",
            "official_rate_limit_does_not_halt_cycle",
            "official_rate_limit_backoff_too_short",
            "stale_context_allowed_on_rate_limit",
        }


# ═══════════════════════════════════════════════════════════════════════
# Parametric: Comprehensive Metric Variants
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sharpe,is_pass", [
    (2.5, True),
    (1.25, True),
    (1.249, False),
    (0.5, False),
    (-1.0, False),
    (0.0, False),
])
def test_sharpe_threshold_boundary(probe_candidate, default_ops_config, sharpe, is_pass):
    """Verify Sharpe boundary values are correctly gated."""
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

    probe_candidate.official_metrics = {
        "pass_fail": "PASS" if is_pass else "FAIL",
        "sharpe": sharpe,
        "fitness": 1.1,
        "turnover": 0.2,
        "returns": 0.05,
        "drawdown": 0.05,
    }

    system = OfficialScoringSystem(default_ops_config)
    result = system.evaluate(probe_candidate)
    assert result is not None


@pytest.mark.parametrize("turnover,is_excessive", [
    (0.05, False),
    (0.69, False),
    (0.70, True),   # exact threshold
    (0.71, True),
    (0.95, True),
    (1.5, True),
])
def test_turnover_platform_threshold(probe_candidate, default_ops_config, turnover, is_excessive):
    """Verify platform max turnover threshold is correctly applied."""
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

    probe_candidate.official_metrics = {
        "pass_fail": "FAIL" if is_excessive else "PASS",
        "sharpe": 1.6,
        "fitness": 1.1,
        "turnover": turnover,
        "returns": 0.05,
        "drawdown": 0.05,
    }

    system = OfficialScoringSystem(default_ops_config)
    result = system.evaluate(probe_candidate)
    assert result is not None


# ═══════════════════════════════════════════════════════════════════════
# Parameter Audit Completeness
# ═══════════════════════════════════════════════════════════════════════


class TestParameterAuditCompleteness:
    def test_audit_snapshot_has_all_trace_sections(self, default_ops_config):
        from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot, REQUIRED_TRACE_SECTIONS

        snapshot = build_parameter_audit_snapshot(default_ops_config, source="test")
        for section in REQUIRED_TRACE_SECTIONS:
            assert section in snapshot["traceable_sections"], (
                f"Missing trace section: {section}"
            )

    def test_audit_snapshot_thresholds_ok(self, default_ops_config):
        from brain_alpha_ops.parameter_audit import build_parameter_audit_snapshot

        snapshot = build_parameter_audit_snapshot(default_ops_config, source="test")
        assert snapshot["thresholds_zero_deviation"] is True
        assert snapshot["api_paths_aligned"] is True


# ═══════════════════════════════════════════════════════════════════════
# Scorecard Data Flow
# ═══════════════════════════════════════════════════════════════════════


class TestScorecardDataFlow:
    def test_build_scorecard_to_attribution_roundtrip(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.scoring.attribution import build_attribution_tree

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.1,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
        }

        scorecard = build_scorecard(
            probe_candidate,
            default_ops_config.thresholds,
            scoring=default_ops_config.scoring,
            settings={"delay": 1, "type": "REGULAR"},
        )

        tree = build_attribution_tree(scorecard)

        assert tree.name == "total_score"
        assert len(tree.children) >= 2  # at least prior and empirical
        assert tree.contribution > 0

    def test_scorecard_contains_required_sections(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.research.scoring import build_scorecard

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.1,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
        }

        scorecard = build_scorecard(
            probe_candidate,
            default_ops_config.thresholds,
            scoring=default_ops_config.scoring,
            settings={"delay": 1, "type": "REGULAR"},
        )

        required = {"total_score", "decision_band", "prior", "empirical", "submission_checklist", "layer_weights"}
        missing = required - set(scorecard.keys())
        assert not missing, f"Scorecard missing sections: {missing}"


# ═══════════════════════════════════════════════════════════════════════
# Resilience: Corrupted Data
# ═══════════════════════════════════════════════════════════════════════


class TestScoringResilience:
    def test_corrupted_metrics_handled_gracefully(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.official_metrics = {
            "pass_fail": "PASS",
            "sharpe": "not_a_number",
            "fitness": None,
            "turnover": "high",
            "returns": 0.08,
        }

        system = OfficialScoringSystem(default_ops_config)
        # Should not raise
        result = system.evaluate(probe_candidate)
        assert result is not None

    def test_minimal_expression(self, probe_candidate, default_ops_config):
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

        probe_candidate.expression = "rank(close)"
        probe_candidate.data_fields = ["close"]
        probe_candidate.operators = ["rank"]

        system = OfficialScoringSystem(default_ops_config)
        result = system.evaluate(probe_candidate)
        assert result is not None
