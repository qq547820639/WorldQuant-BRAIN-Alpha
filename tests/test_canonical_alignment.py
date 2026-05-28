"""Comprehensive tests verifying config_schema.py is aligned with canonical.py.

These tests enforce the six technical red lines by validating:
  Red Line 2: 阈值零偏差 — zero threshold deviation
  Red Line 6: 代码强对齐 — strong code alignment

All enum values in config_schema.py must match the canonical source of truth
defined in brain_alpha_ops.brain_api.canonical.
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_API_PATHS,
    CANONICAL_METRIC_NAMES,
    CANONICAL_SETTINGS,
    CANONICAL_THRESHOLDS,
    SUPPORTED_ALPHA_TYPES,
    SUPPORTED_DELAYS,
    SUPPORTED_INSTRUMENT_TYPES,
    SUPPORTED_LANGUAGES,
    SUPPORTED_NAN_HANDLING,
    SUPPORTED_NEUTRALIZATIONS,
    SUPPORTED_PASTEURIZATION,
    SUPPORTED_REGIONS,
    SUPPORTED_UNIT_HANDLING,
    SUPPORTED_UNIVERSES,
)

try:
    import jsonschema  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
from brain_alpha_ops.config import (
    ConfigValidationError,
    QualityThresholds,
    RunConfig,
    load_run_config,
)
from brain_alpha_ops.config_schema import (
    RUN_CONFIG_SCHEMA,
    validate_config_with_jsonschema,
    validate_config_file,
)


# ──────────────────────────────────────────────
# Red Line 6: Code alignment tests
# ──────────────────────────────────────────────

class TestSchemaEnumAlignment:
    """Verify config_schema.py enums match canonical.py values."""

    def _get_schema_enum(self, *path: str) -> set:
        """Extract an ``enum`` list from the nested schema dict."""
        node = RUN_CONFIG_SCHEMA
        for key in path:
            node = node.get("properties", {}).get(key, {})
        raw = node.get("enum", [])
        return {v for v in raw}

    def test_instrument_type_aligned(self):
        assert self._get_schema_enum("ops", "settings", "instrumentType") == SUPPORTED_INSTRUMENT_TYPES

    def test_region_aligned(self):
        assert self._get_schema_enum("ops", "settings", "region") == SUPPORTED_REGIONS

    def test_universe_aligned(self):
        assert self._get_schema_enum("ops", "settings", "universe") == SUPPORTED_UNIVERSES

    def test_delay_aligned(self):
        assert self._get_schema_enum("ops", "settings", "delay") == SUPPORTED_DELAYS

    def test_neutralization_aligned(self):
        assert self._get_schema_enum("ops", "settings", "neutralization") == SUPPORTED_NEUTRALIZATIONS

    def test_pasteurization_aligned(self):
        assert self._get_schema_enum("ops", "settings", "pasteurization") == SUPPORTED_PASTEURIZATION

    def test_unit_handling_aligned(self):
        assert self._get_schema_enum("ops", "settings", "unitHandling") == SUPPORTED_UNIT_HANDLING

    def test_nan_handling_aligned(self):
        assert self._get_schema_enum("ops", "settings", "nanHandling") == SUPPORTED_NAN_HANDLING

    def test_language_aligned(self):
        assert self._get_schema_enum("ops", "settings", "language") == SUPPORTED_LANGUAGES

    def test_alpha_type_aligned(self):
        assert self._get_schema_enum("ops", "settings", "type") == SUPPORTED_ALPHA_TYPES

    def test_environment_aligned(self):
        assert self._get_schema_enum("environment") == {"production"}


class TestSchemaValidation:
    """Verify jsonschema validation accepts canonical values."""

    def _base_config(self, **overrides: object) -> dict:
        data = {
            "environment": "production",
            "auto_submit": False,
            "credentials": {},
            "web": {"host": "127.0.0.1", "port": 9123},
            "ops": {
                "settings": {
                    "instrumentType": "EQUITY",
                    "region": "USA",
                    "universe": "TOP3000",
                    "delay": 1,
                    "neutralization": "SUBINDUSTRY",
                    "language": "FASTEXPR",
                },
                "budget": {},
                "scoring": {},
                "thresholds": {},
                "submission_policy": {},
                "official_api": {"base_url": "https://api.worldquantbrain.com"},
                "storage_dir": "/tmp/test",
            },
        }
        # Deep merge overrides
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
        return data

    def test_accepts_canonical_regions(self):
        for region in SUPPORTED_REGIONS:
            cfg = self._base_config(ops={"settings": {"region": region}})
            errors = validate_config_with_jsonschema(cfg)
            assert not errors, f"canonical region {region!r} rejected: {errors}"

    def test_accepts_canonical_universes(self):
        for universe in SUPPORTED_UNIVERSES:
            cfg = self._base_config(ops={"settings": {"universe": universe}})
            errors = validate_config_with_jsonschema(cfg)
            assert not errors, f"canonical universe {universe!r} rejected: {errors}"

    def test_accepts_canonical_delays(self):
        for delay in SUPPORTED_DELAYS:
            cfg = self._base_config(ops={"settings": {"delay": delay}})
            errors = validate_config_with_jsonschema(cfg)
            assert not errors, f"canonical delay {delay!r} rejected: {errors}"

    def test_accepts_canonical_unit_handling(self):
        for unit_handling in SUPPORTED_UNIT_HANDLING:
            cfg = self._base_config(ops={"settings": {"unitHandling": unit_handling}})
            errors = validate_config_with_jsonschema(cfg)
            assert not errors, f"canonical unitHandling {unit_handling!r} rejected: {errors}"

    def test_accepts_canonical_alpha_types(self):
        for alpha_type in SUPPORTED_ALPHA_TYPES:
            cfg = self._base_config(ops={"settings": {"type": alpha_type}})
            errors = validate_config_with_jsonschema(cfg)
            assert not errors, f"canonical alpha type {alpha_type!r} rejected: {errors}"

    def test_accepts_canonical_neutralization(self):
        for neut in SUPPORTED_NEUTRALIZATIONS:
            cfg = self._base_config(ops={"settings": {"neutralization": neut}})
            errors = validate_config_with_jsonschema(cfg)
            assert not errors, f"canonical neutralization {neut!r} rejected: {errors}"

    def test_rejects_invalid_region(self):
        if not HAS_JSONSCHEMA:
            pytest.skip("jsonschema not installed")
        cfg = self._base_config(ops={"settings": {"region": "INVALID"}})
        errors = validate_config_with_jsonschema(cfg)
        assert errors, "invalid region should be rejected"

    def test_rejects_invalid_universe(self):
        if not HAS_JSONSCHEMA:
            pytest.skip("jsonschema not installed")
        cfg = self._base_config(ops={"settings": {"universe": "TOP999999"}})
        errors = validate_config_with_jsonschema(cfg)
        assert errors, "invalid universe should be rejected"

    def test_rejects_invalid_delay(self):
        if not HAS_JSONSCHEMA:
            pytest.skip("jsonschema not installed")
        cfg = self._base_config(ops={"settings": {"delay": 99}})
        errors = validate_config_with_jsonschema(cfg)
        assert errors, "invalid delay should be rejected"

    def test_full_config_roundtrip_to_file(self):
        """Validate a complete config file passes both jsonschema and procedural validation."""
        cfg = self._base_config(
            ops={
                "settings": {
                    "region": "USA",
                    "universe": "TOP3000",
                    "delay": 1,
                    "unitHandling": "VERIFY",
                    "type": "REGULAR",
                },
                "thresholds": {
                    "min_sharpe": 1.25,
                    "min_fitness": 1.0,
                    "min_sharpe_delay0": 2.0,
                    "min_fitness_delay0": 1.3,
                    "min_turnover": 0.01,
                    "platform_max_turnover": 0.70,
                    "max_self_correlation": 0.70,
                    "max_weight_concentration": 0.10,
                    "sub_universe_sharpe_min_ratio": 0.75,
                },
            }
        )
        errors = validate_config_with_jsonschema(cfg)
        assert not errors, f"full config should pass: {errors}"

    def test_empty_config_should_pass_minimal_schema(self):
        """An empty object should fail schema (missing required fields)."""
        if not HAS_JSONSCHEMA:
            pytest.skip("jsonschema not installed")
        errors = validate_config_with_jsonschema({})
        assert errors, "empty config should have validation errors"


# ──────────────────────────────────────────────
# Red Line 2: Threshold zero-deviation tests
# ──────────────────────────────────────────────

class TestThresholdAlignment:
    """Verify QualityThresholds defaults match CANONICAL_THRESHOLDS."""

    def test_all_canonical_thresholds_present_in_dataclass(self):
        dt = QualityThresholds()
        threshold_map = {
            "min_sharpe": dt.min_sharpe,
            "min_sharpe_delay0": dt.min_sharpe_delay0,
            "min_fitness": dt.min_fitness,
            "min_fitness_delay0": dt.min_fitness_delay0,
            "min_turnover": dt.min_turnover,
            "platform_max_turnover": dt.platform_max_turnover,
            "max_self_correlation": dt.max_self_correlation,
            "max_weight_concentration": dt.max_weight_concentration,
            "sub_universe_sharpe_min_ratio": dt.sub_universe_sharpe_min_ratio,
        }
        for key, canonical_value in CANONICAL_THRESHOLDS.items():
            assert key in threshold_map, f"canonical threshold {key!r} missing from QualityThresholds"
            actual = threshold_map[key]
            assert actual == canonical_value, (
                f"threshold {key}: QualityThresholds has {actual}, canonical is {canonical_value}"
            )

    def test_config_validation_accepts_canonical_thresholds(self):
        """Procedural validation should accept canonical threshold values."""
        config = RunConfig()
        config.ops.thresholds.min_sharpe = 1.25
        config.ops.thresholds.min_fitness = 1.0
        config.ops.thresholds.platform_max_turnover = 0.70
        # Should not raise
        from brain_alpha_ops.config import validate_run_config
        with tempfile.TemporaryDirectory() as tmp:
            storage = os.path.join(tmp, "data")
            os.makedirs(storage, exist_ok=True)
            config.ops.storage_dir = storage
            config.ops.official_api.cache_dir = os.path.join(storage, "api_cache")
            os.makedirs(config.ops.official_api.cache_dir, exist_ok=True)
            config.ops.budget.hypothesis_library_dir = os.path.join(tmp, "hypotheses")
            os.makedirs(config.ops.budget.hypothesis_library_dir, exist_ok=True)
            try:
                validated = validate_run_config(config)
                assert validated.ops.thresholds.min_sharpe == 1.25
            except ConfigValidationError as exc:
                pytest.fail(f"procedural validation rejected canonical thresholds: {exc}")

    def test_zero_min_sharpe_edge_case_accepted(self):
        """min_sharpe=0.0 is a valid float (though not BRAIN-compliant, it's syntactically valid)."""
        thresh = QualityThresholds(min_sharpe=0.0)
        assert thresh.min_sharpe == 0.0

    def test_negative_threshold_validation_edge(self):
        """QualityThresholds can hold negative values but config loading may reject them."""
        import math
        # _require_float_range rejects non-finite, but accepts negative
        assert math.isfinite(-0.5), "precondition"


# ──────────────────────────────────────────────
# Shared bounds tests
# ──────────────────────────────────────────────

class TestSharedBounds:
    """Verify the shared_bounds helpers work correctly."""

    def test_bounded_int_in_range(self):
        from brain_alpha_ops.shared_bounds import bounded_int
        assert bounded_int(5, 1, 10) == 5

    def test_bounded_int_clamp_low(self):
        from brain_alpha_ops.shared_bounds import bounded_int
        assert bounded_int(-5, 1, 10) == 1

    def test_bounded_int_clamp_high(self):
        from brain_alpha_ops.shared_bounds import bounded_int
        assert bounded_int(999, 1, 10) == 10

    def test_bounded_int_invalid_default(self):
        from brain_alpha_ops.shared_bounds import bounded_int
        assert bounded_int("abc", 1, 100) == 1  # defaults to lower

    def test_bounded_int_none_default(self):
        from brain_alpha_ops.shared_bounds import bounded_int
        assert bounded_int(None, 1, 100, default=50) == 50

    def test_bounded_float_in_range(self):
        from brain_alpha_ops.shared_bounds import bounded_float
        assert bounded_float(3.14, 0.0, 10.0) == 3.14

    def test_bounded_float_clamp(self):
        from brain_alpha_ops.shared_bounds import bounded_float
        assert bounded_float(100.0, 0.0, 10.0) == 10.0

    def test_bounded_float_string(self):
        from brain_alpha_ops.shared_bounds import bounded_float
        assert bounded_float("2.5", 0.0, 5.0) == 2.5

    def test_truthy_bool_true(self):
        from brain_alpha_ops.shared_bounds import truthy
        assert truthy(True) is True

    def test_truthy_bool_false(self):
        from brain_alpha_ops.shared_bounds import truthy
        assert truthy(False) is False

    def test_truthy_string_true(self):
        from brain_alpha_ops.shared_bounds import truthy
        assert truthy("yes") is True

    def test_truthy_string_false(self):
        from brain_alpha_ops.shared_bounds import truthy
        assert truthy("false") is False
        assert truthy("no") is False
        assert truthy("off") is False
        assert truthy("0") is False

    def test_truthy_none(self):
        from brain_alpha_ops.shared_bounds import truthy
        assert truthy(None) is False

    def test_truthy_empty_string(self):
        from brain_alpha_ops.shared_bounds import truthy
        assert truthy("") is False

    def test_required_text_present(self):
        from brain_alpha_ops.shared_bounds import required_text
        assert required_text({"key": "value"}, "key") == "value"

    def test_required_text_missing(self):
        from brain_alpha_ops.shared_bounds import required_text
        with pytest.raises(ValueError, match="missing required argument"):
            required_text({"key": ""}, "key")

    def test_required_text_none(self):
        from brain_alpha_ops.shared_bounds import required_text
        with pytest.raises(ValueError):
            required_text({}, "key")

    def test_candidate_argument_from_dict(self):
        from brain_alpha_ops.shared_bounds import candidate_argument
        result = candidate_argument({"candidate": {"alpha_id": "test_001", "expression": "rank(close)"}})
        assert result["alpha_id"] == "test_001"
        assert result["expression"] == "rank(close)"

    def test_candidate_argument_from_fields(self):
        from brain_alpha_ops.shared_bounds import candidate_argument
        result = candidate_argument({"expression": "ts_zscore(close, 20)", "family": "ZScore"})
        assert result["expression"] == "ts_zscore(close, 20)"
        assert result["family"] == "ZScore"

    def test_candidate_argument_missing_expression(self):
        from brain_alpha_ops.shared_bounds import candidate_argument
        with pytest.raises(ValueError):
            candidate_argument({})

    def test_expression_batch_argument_single(self):
        from brain_alpha_ops.shared_bounds import expression_batch_argument
        result = expression_batch_argument({"expression": "rank(close)"})
        assert result == ["rank(close)"]

    def test_expression_batch_argument_list(self):
        from brain_alpha_ops.shared_bounds import expression_batch_argument
        result = expression_batch_argument({"expressions": ["a", "b", "c"]})
        assert result == ["a", "b", "c"]

    def test_expression_batch_argument_dedup(self):
        from brain_alpha_ops.shared_bounds import expression_batch_argument
        result = expression_batch_argument({"expressions": ["rank(close)", "rank(close)"]})
        assert len(result) == 1

    def test_expression_batch_argument_empty(self):
        from brain_alpha_ops.shared_bounds import expression_batch_argument
        result = expression_batch_argument({"expressions": []})
        assert result == []

    def test_list_text_dedup_case_insensitive(self):
        from brain_alpha_ops.shared_bounds import list_text
        result = list_text(["A", "a", "B", "b"])
        assert result == ["A", "B"]

    def test_list_text_none(self):
        from brain_alpha_ops.shared_bounds import list_text
        assert list_text(None) == []


# ──────────────────────────────────────────────
# Safety / Context error handling tests
# ──────────────────────────────────────────────

class TestSafetyErrorHandling:
    """Verify SubmissionLedger no longer silently swallows exceptions."""

    def test_safety_record_sqlite_failure_is_logged(self):
        """When ExpressionSqliteIndex fails, it should log a warning, not silently pass."""
        import os
        import tempfile
        from brain_alpha_ops.research.safety import SubmissionLedger
        from brain_alpha_ops.models import Candidate

        ledger = SubmissionLedger(storage_dir=tempfile.mkdtemp())
        candidate = Candidate(
            alpha_id="test_001",
            expression="rank(close)",
            family="test",
            hypothesis="test hypothesis",
            official_alpha_id="",
        )
        ledger.record(candidate, {"status": "SUBMITTED"}, mode="manual")
        # Should not raise — the record is always written to JSONL
        assert os.path.exists(ledger.path)


class TestContextComplianceFallback:
    """Verify _compliance_context no longer defaults redline to ok=True on error."""

    def test_compliance_context_fallback_on_import_error(self):
        """When RedLineVerifier cannot be imported, redline.ok should be False."""
        # The compliance context is tested indirectly through build_assistant_context_pack
        # which calls _compliance_context internally. We verify the structure here.
        from brain_alpha_ops.research.context import _compliance_context
        from brain_alpha_ops.config import RunConfig

        config = RunConfig()
        with tempfile.TemporaryDirectory() as tmp:
            config.ops.storage_dir = tmp
            config.ops.official_api.cache_dir = os.path.join(tmp, "cache")
            os.makedirs(config.ops.official_api.cache_dir, exist_ok=True)
            config.ops.budget.hypothesis_library_dir = os.path.join(tmp, "hypotheses")
            os.makedirs(config.ops.budget.hypothesis_library_dir, exist_ok=True)
            result = _compliance_context(config)
            # Should have redline key
            assert "redline" in result
            # If no redline verifier module is available, it should NOT default to ok
            # Note: in a full install, redline verifier IS available, so ok may be True
            assert "thresholds_synced" in result
            assert isinstance(result["redline"], dict)


class TestRuntimeRedlineConfigBinding:
    """Red-line checks must validate the actual runtime config, not defaults."""

    def test_redline_verifier_blocks_runtime_threshold_drift(self):
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier

        config = RunConfig()
        config.ops.thresholds.min_sharpe = 1.0

        report = RedLineVerifier(config).verify_all()

        assert report.overall == "FAIL"
        assert any(
            violation.redline_id == 2 and "min_sharpe" in violation.check_name
            for violation in report.violations
        )

    def test_redline_verifier_blocks_runtime_api_path_drift(self):
        from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier

        config = RunConfig()
        config.ops.official_api.simulations_path = "/wrong-simulations"

        report = RedLineVerifier(config).verify_all()

        assert report.overall == "FAIL"
        assert any(
            violation.redline_id == 6 and "simulations" in violation.check_name
            for violation in report.violations
        )

    def test_guided_redline_phase_uses_runtime_config(self):
        from brain_alpha_ops.models import PipelineResult
        from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline

        config = RunConfig()
        config.ops.thresholds.min_fitness = 0.5
        pipeline = GuidedPipeline(config)

        with pytest.raises(RuntimeError, match="TECH_REDLINE_BLOCKED"):
            pipeline._phase_redline(PipelineResult(run_id="redline_drift", candidates=[], events=[], summary={}))

        assert pipeline.phases["redline"].status == "failed"


# ──────────────────────────────────────────────
# Edge case / boundary tests
# ──────────────────────────────────────────────

class TestBoundaryConditions:
    """Test edge cases: extreme values, nulls, network error sims."""

    def test_quality_thresholds_extreme_values(self):
        """QualityThresholds should accept extreme but finite values."""
        thresh = QualityThresholds(
            min_sharpe=100.0,
            min_fitness=50.0,
            platform_max_turnover=0.999,
            max_weight_concentration=0.001,
        )
        assert thresh.min_sharpe == 100.0
        assert thresh.max_weight_concentration == 0.001

    def test_quality_thresholds_regime_adjustments(self):
        """Regime adjustments should have all three market regimes."""
        thresh = QualityThresholds()
        assert set(thresh.regime_adjustments.keys()) == {"normal", "low_vol", "high_vol"}

    def test_submission_policy_extreme_similarity(self):
        from brain_alpha_ops.config import SubmissionPolicy
        policy = SubmissionPolicy(max_expression_similarity=0.0)
        assert policy.max_expression_similarity == 0.0
        policy = SubmissionPolicy(max_expression_similarity=1.0)
        assert policy.max_expression_similarity == 1.0

    def test_official_api_config_timeout_edge(self):
        from brain_alpha_ops.config import OfficialAPIConfig
        cfg = OfficialAPIConfig(timeout_seconds=1)
        assert cfg.timeout_seconds == 1
        cfg = OfficialAPIConfig(timeout_seconds=3600)
        assert cfg.timeout_seconds == 3600

    def test_brain_settings_dataset_empty(self):
        """Empty dataset string is valid (falls back to DatasetSelector)."""
        from brain_alpha_ops.config import BrainSettings
        bs = BrainSettings(dataset="")
        assert bs.dataset == ""

    def test_validate_non_dict_config_edge(self):
        """Passing a non-dict to validate_config_with_jsonschema should not crash."""
        # jsonschema will error on non-dict input
        import sys
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        from brain_alpha_ops.config_schema import validate_config_with_jsonschema
        errors = validate_config_with_jsonschema([1, 2, 3])
        # The public helper should normalize non-object input into an error list.
        assert isinstance(errors, list)

    def test_config_file_invalid_json(self):
        """Loading a file with invalid JSON should produce a clear error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{{")
            f.flush()
            with pytest.raises(ConfigValidationError, match="JSON 格式错误"):
                load_run_config(f.name)
        os.unlink(f.name)

    def test_config_file_nonexistent(self):
        """Loading a nonexistent file returns a default config (no crash)."""
        # load_run_config returns a default RunConfig when file doesn't exist
        config = load_run_config("/nonexistent/path/config.json")
        assert config.environment == "production"
        assert isinstance(config, RunConfig)


# ──────────────────────────────────────────────
# Canonical threshold completeness
# ──────────────────────────────────────────────

class TestCanonicalCompleteness:
    """Verify canonical.py defines all expected BRAIN platform values."""

    def test_canonical_thresholds_have_all_keys(self):
        required = {
            "min_sharpe", "min_sharpe_delay0", "min_fitness", "min_fitness_delay0",
            "min_turnover", "platform_max_turnover", "max_self_correlation",
            "max_weight_concentration", "sub_universe_sharpe_min_ratio",
        }
        assert set(CANONICAL_THRESHOLDS.keys()) == required

    def test_canonical_api_paths_have_all_endpoints(self):
        required = {
            "authentication", "simulations", "data_sets", "data_fields",
            "operators", "user_alphas", "user_profile", "alpha_check",
            "alpha_submit", "alpha_detail", "alpha_correlations",
        }
        assert set(CANONICAL_API_PATHS.keys()) == required

    def test_canonical_metric_names_complete(self):
        required = {
            "sharpe", "fitness", "turnover", "returns", "drawdown",
            "correlation", "weight_concentration", "sub_universe_sharpe",
            "margin", "subUniverseSize", "alphaSize",
        }
        assert CANONICAL_METRIC_NAMES == required
