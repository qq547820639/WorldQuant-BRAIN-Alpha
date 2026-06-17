"""Integration and regression tests for the full alpha production lifecycle.
from __future__ import annotations

Tests cover:
  - Dataset ID tracing through generation→scoring→submission
  - Expression diversity guard integration
  - LLM service review and guidance (offline mode)
  - Parameter traceability audit
  - Edge cases: empty inputs, null values, extreme values, error conditions
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from brain_alpha_ops.models import Candidate
from tests.production_api_stub import write_template_safe_official_context


# ═══════════════════════════════════════════════════════════════════════
# Dataset Trace Tests
# ═══════════════════════════════════════════════════════════════════════

class TestDatasetTraceValidator:
    """Test dataset_id full-chain tracing."""

    def test_all_valid(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(
            official_datasets=["model77", "analyst4"],
            active_dataset_id="model77",
        )
        candidates = [
            Candidate(alpha_id="a1", expression="rank(returns)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id="model77"),
            Candidate(alpha_id="a2", expression="ts_mean(close,20)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id="analyst4"),
        ]
        report = validator.validate_candidates(candidates)
        assert report.all_valid is True
        assert report.total == 2
        assert report.without_dataset == 0
        assert report.invalid_dataset == 0

    def test_missing_dataset_id(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(
            official_datasets=["model77"],
            active_dataset_id="model77",
        )
        candidates = [
            Candidate(alpha_id="a1", expression="rank(returns)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id=""),
            Candidate(alpha_id="a2", expression="ts_mean(close,20)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id=""),
        ]
        report = validator.validate_candidates(candidates)
        assert report.all_valid is False
        assert report.without_dataset == 2

    def test_invalid_dataset_id(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(
            official_datasets=["model77", "analyst4"],
        )
        candidates = [
            Candidate(alpha_id="a1", expression="rank(returns)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id="unknown_ds"),
        ]
        report = validator.validate_candidates(candidates)
        assert report.invalid_dataset == 1

    def test_auto_fix_missing(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(
            official_datasets=["model77"],
            active_dataset_id="model77",
        )
        candidates = [
            Candidate(alpha_id="a1", expression="rank(returns)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id=""),
        ]
        fixed, report = validator.auto_fix_missing(candidates)
        assert report.fixed_count == 1
        assert fixed[0].dataset_id == "model77"

    def test_auto_fix_no_fallback(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(
            official_datasets=["model77"],
            active_dataset_id="",  # No active dataset
        )
        candidates = [
            Candidate(alpha_id="a1", expression="rank(returns)", family="momentum",
                     hypothesis="momentum hypothesis", dataset_id=""),
        ]
        fixed, report = validator.auto_fix_missing(candidates)
        # No active dataset and no default → cannot fix
        assert report.fixed_count == 0
        assert "no active" in str(report.details.get("error", ""))

    def test_check_single_candidate_valid(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(official_datasets=["model77"])
        candidate = Candidate(
            alpha_id="a1", expression="rank(returns)", family="momentum",
            hypothesis="momentum hypothesis", dataset_id="model77",
        )
        assert validator.check_candidate(candidate) is True

    def test_check_single_candidate_missing(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(official_datasets=["model77"])
        candidate = Candidate(
            alpha_id="a1", expression="rank(returns)", family="momentum",
            hypothesis="momentum hypothesis", dataset_id="",
        )
        assert validator.check_candidate(candidate) is False

    def test_check_single_candidate_raises(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(official_datasets=["model77"])
        candidate = Candidate(
            alpha_id="a1", expression="rank(returns)", family="momentum",
            hypothesis="momentum hypothesis", dataset_id="",
        )
        with pytest.raises(ValueError, match="missing dataset_id"):
            validator.check_candidate(candidate, raise_on_missing=True)

    def test_compute_coverage(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(official_datasets=["m1", "m2"])
        candidates = [
            Candidate(alpha_id="a1", expression="r1", family="f1", hypothesis="h1", dataset_id="m1"),
            Candidate(alpha_id="a2", expression="r2", family="f1", hypothesis="h1", dataset_id="m1"),
            Candidate(alpha_id="a3", expression="r3", family="f1", hypothesis="h1", dataset_id="m2"),
        ]
        coverage = validator.compute_dataset_coverage(candidates)
        assert coverage["m1"] == 2
        assert coverage["m2"] == 1

    def test_report_to_dict(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(official_datasets=["model77"])
        candidates = [
            Candidate(alpha_id="a1", expression="r1", family="f1", hypothesis="h1", dataset_id="model77"),
        ]
        report = validator.validate_candidates(candidates)
        d = report.to_dict()
        assert d["total"] == 1
        assert d["all_valid"] is True


# ═══════════════════════════════════════════════════════════════════════
# LLM Service Tests
# ═══════════════════════════════════════════════════════════════════════

class TestLLMService:
    """Test LLM service (offline mode)."""

    def test_offline_review_produces_result(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        result = service.review_expression("rank(returns)")
        assert isinstance(result.quality_score, float)
        assert 0.0 <= result.quality_score <= 10.0
        assert result.provider_name == "offline_heuristic"

    def test_offline_review_short_expression(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        result = service.review_expression("rank(ret)")
        # Short expressions get lower scores
        assert result.quality_score < 5.0
        assert len(result.suggestions) > 0

    def test_offline_review_empty_expression(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        result = service.review_expression("")
        assert result.error != ""

    def test_offline_review_with_context(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        result = service.review_expression(
            "rank(returns)",
            context={"fields": ["returns", "close", "volume"], "dataset": "model77"},
        )
        assert isinstance(result.to_dict(), dict)

    def test_cross_review_offline(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        results = service.cross_review_expression("rank(returns)")
        assert "primary" in results
        assert "secondary" in results
        assert results["primary"].provider_name == "offline_heuristic"
        assert results["secondary"].provider_name == "offline_heuristic"

    def test_heuristic_guidance(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        guidance = service.generate_guidance(
            pool_performance={"avg_sharpe": 1.5},
            convergence_status={"stalled": False},
            hypotheses=["value_reversal", "momentum"],
        )
        assert len(guidance.recommended_operators) > 0
        assert len(guidance.recommended_windows) > 0

    def test_heuristic_guidance_stalled(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        guidance = service.generate_guidance(
            convergence_status={"stalled": True, "sharpe_trend": "declining"},
        )
        # Stalled + declining → should recommend diversification
        assert guidance.diversification_strategy != ""

    def test_strategy_recommendation_stalled(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        result = service.recommend_strategy(
            strategy_history=[{"profile": "USA_TOP3000"} for _ in range(20)],
            convergence_report={"stalled": True, "sharpe_trend": "declining"},
            production_rate=0.03,
        )
        assert result["switch_recommended"] is True

    def test_strategy_recommendation_adequate(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        result = service.recommend_strategy(
            strategy_history=[{"profile": "USA_TOP3000"}],
            convergence_report={"stalled": False, "sharpe_trend": "stable"},
        )
        assert result["switch_recommended"] is False

    def test_result_to_dict(self):
        from brain_alpha_ops.research.llm_service import LLMService, LLMReviewResult

        result = LLMReviewResult(
            expression="rank(returns)",
            quality_score=7.5,
            critique="Good but lacks diversification",
            suggestions=["Add neutralization"],
            risk_flags=["no_winsorize"],
            confidence=0.8,
            provider_name="offline_heuristic",
        )
        d = result.to_dict()
        assert d["quality_score"] == 7.5
        assert d["confidence"] == 0.8
        assert "suggestions" in d
        assert "risk_flags" in d

    def test_guidance_to_dict(self):
        from brain_alpha_ops.research.llm_service import LLMGenerationGuidance

        guidance = LLMGenerationGuidance(
            recommended_hypothesis="value_reversal",
            recommended_operators=["rank", "ts_mean"],
            recommended_windows=[20, 60],
            diversification_strategy="switch_operator_family",
            confidence=0.75,
        )
        d = guidance.to_dict()
        assert d["recommended_hypothesis"] == "value_reversal"
        assert d["confidence"] == 0.75


# ═══════════════════════════════════════════════════════════════════════
# Parameter Audit Tests
# ═══════════════════════════════════════════════════════════════════════

class TestParameterAudit:
    """Test parameter traceability audit script."""

    def test_audit_with_valid_config(self, tmp_path):
        """Run audit against an isolated, lineage-consistent official context."""
        from scripts.check_parameter_traceability import run_parameter_audit

        data_dir = tmp_path / "data"
        fixture_config = SimpleNamespace(
            ops=SimpleNamespace(
                storage_dir=str(data_dir),
                official_api=SimpleNamespace(context_cache_ttl_seconds=3600),
            )
        )
        write_template_safe_official_context(fixture_config)
        config_path = tmp_path / "run_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "environment": "production",
                    "ops": {
                        "storage_dir": str(data_dir),
                        "settings": {
                            "instrumentType": "EQUITY",
                            "region": "USA",
                            "universe": "TOP3000",
                            "delay": 1,
                            "language": "FASTEXPR",
                            "type": "REGULAR",
                            "dataset": "pv1",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        data = run_parameter_audit(config_path=str(config_path), data_dir=str(data_dir))

        assert data["passed"] is True
        assert data["errors"] == 0
        assert data["checks"]["official_context_validation"]["passed"] is True

    def test_audit_fails_when_official_context_lineage_is_incomplete(self, tmp_path):
        from scripts.check_parameter_traceability import run_parameter_audit

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "official_fields.json").write_text(
            json.dumps([{"id": "close", "dataset": {"id": "pv1"}}]),
            encoding="utf-8",
        )
        (data_dir / "official_operators.json").write_text(
            json.dumps([{"name": "rank"}, {"name": "ts_delta"}, {"name": "ts_std_dev"}]),
            encoding="utf-8",
        )
        (data_dir / "official_datasets.json").write_text(
            json.dumps([{"id": "pv1", "name": "Price Volume", "field_count": 2}]),
            encoding="utf-8",
        )
        config_path = tmp_path / "run_config.json"
        config_path.write_text(
            json.dumps({"ops": {"storage_dir": str(data_dir), "settings": {"dataset": "pv1"}}}),
            encoding="utf-8",
        )

        data = run_parameter_audit(config_path=str(config_path), data_dir=str(data_dir))

        assert data["passed"] is False
        assert data["errors"] >= 1
        assert any(
            item["check"] == "official_context_dataset_field_count_mismatch"
            for item in data["errors_list"]
        )

    def test_audit_validate_settings(self):
        from scripts.check_parameter_traceability import validate_brain_settings

        # Valid settings
        issues = validate_brain_settings({"instrumentType": "EQUITY", "region": "USA", "universe": "TOP3000"})
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) == 0

    def test_audit_detect_invalid_setting(self):
        from scripts.check_parameter_traceability import validate_brain_settings

        # Invalid value
        issues = validate_brain_settings({"instrumentType": "FUTURES"})
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) >= 1

    def test_audit_detect_unknown_setting(self):
        from scripts.check_parameter_traceability import validate_brain_settings

        # Unknown setting
        issues = validate_brain_settings({"customParam": "value123"})
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) >= 1

    def test_audit_validate_thresholds_passing(self):
        from scripts.check_parameter_traceability import validate_thresholds

        issues = validate_thresholds({
            "min_sharpe": 1.25,
            "min_fitness": 1.0,
            "platform_max_turnover": 0.70,
            "max_self_correlation": 0.70,
            "max_weight_concentration": 0.10,
        })
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) == 0

    def test_audit_detect_threshold_deviation(self):
        from scripts.check_parameter_traceability import validate_thresholds

        # Wrong threshold value
        issues = validate_thresholds({"min_sharpe": 2.0})  # Should be 1.25
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) >= 1
        assert "min_sharpe" in errors[0]["details"]

    def test_audit_validate_api_paths(self):
        from scripts.check_parameter_traceability import validate_api_paths

        issues = validate_api_paths({
            "authentication_path": "/authentication",
            "simulations_path": "/simulations",
        })
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) == 0

    def test_audit_detect_api_path_deviation(self):
        from scripts.check_parameter_traceability import validate_api_paths

        issues = validate_api_paths({
            "simulations_path": "/wrong/path",
        })
        errors = [i for i in issues if i["severity"] == "ERROR"]
        assert len(errors) >= 1


# ═══════════════════════════════════════════════════════════════════════
# Pipeline Diversity Mixin Tests
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineDiversityMixin:
    """Test the expression diversity pipeline integration mixin."""

    class MockPipeline:
        """Minimal mock pipeline for diversity mixin testing."""

        def __init__(self):
            self.events: list[dict] = []
            self._diversity_guard = None
            self._diversity_alerted = set()
            self._diversity_stall_count = 0
            self._diversity_max_stall = 5

        def _event(self, name, message, *, level="INFO", data=None):
            self.events.append({"name": name, "message": message, "level": level, "data": data or {}})

    def setup_method(self):
        from brain_alpha_ops.research.pipeline_diversity import PipelineDiversityMixin

        # Create a mock class that inherits the mixin
        self.MockWithDiversity: type = type(
            "MockWithDiversity",
            (self.MockPipeline, PipelineDiversityMixin),
            {},
        )

    def test_diversity_check_diverse_pool(self):
        mock = self.MockWithDiversity()
        result = mock._check_expression_diversity(
            pool_expressions=[
                "rank(returns)",
                "ts_mean(close, 20)",
                "group_rank(volume, sector)",
                "ts_std(returns, 60)",
                "decay_linear(close, 10)",
            ],
        )
        assert result["is_converged"] is False
        assert result["recommended_action"] == "none"

    def test_diversity_check_converged_pool(self):
        mock = self.MockWithDiversity()
        result = mock._check_expression_diversity(
            pool_expressions=[
                "rank(returns)",
                "rank(market_cap)",
                "rank(volume)",
                "rank(close)",
                "ts_mean(returns, 20)",
            ],
            new_expression="rank(some_field)",
        )
        # 5 in pool, 4 share rank skeleton + new = 5/6 = 83.3% > 30%
        assert result["is_converged"] is True
        assert result["recommended_action"] in ("diversity_warning", "force_diversify")

    def test_get_diversification_strategies(self):
        mock = self.MockWithDiversity()
        strategies = mock._get_diversification_strategies("rank(returns)")
        assert len(strategies) > 0
        assert all(isinstance(s, str) for s in strategies)

    def test_reset_stall(self):
        mock = self.MockWithDiversity()
        mock._diversity_stall_count = 10
        mock._reset_diversity_stall()
        assert mock._diversity_stall_count == 0

    def test_record_diversity_alert(self):
        mock = self.MockWithDiversity()
        # Trigger convergence
        mock._check_expression_diversity(
            pool_expressions=["rank(returns)", "rank(close)", "rank(volume)"],
        )
        mock._record_diversity_alert(
            cycle=1,
            report={"most_common_skeleton": "rank(FIELD)", "convergence_rate": 0.75, "unique_skeletons": 1},
        )
        # Should generate an alert event
        assert len(mock.events) > 0
        assert any("expression_diversity_alert" in str(e) for e in mock.events)


# ═══════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test boundary and edge cases across all new modules."""

    def test_empty_candidates_dataset_trace(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator()
        report = validator.validate_candidates([])
        assert report.total == 0
        assert report.all_valid is True  # Vacuously true

    def test_none_dataset_id_candidate(self):
        from brain_alpha_ops.research.dataset_trace import DatasetTraceValidator

        validator = DatasetTraceValidator(official_datasets=["model77"])
        # dataset_id is None in extra_fields but not on model
        candidate = Candidate(
            alpha_id="a1", expression="rank(returns)", family="f1",
            hypothesis="h1", dataset_id="",
        )
        report = validator.validate_candidates([candidate])
        assert report.without_dataset == 1

    def test_very_long_expression_llm_review(self):
        from brain_alpha_ops.research.llm_service import LLMService

        service = LLMService(provider=None)
        long_expr = "group_neutralize(decay_linear(ts_delta(winsorize(" + "market_cap + volume, 0.01), 60), 20), industry)"
        result = service.review_expression(long_expr)
        assert isinstance(result.quality_score, float)

    def test_llm_service_no_provider_max_retries_exhausted(self):
        from brain_alpha_ops.research.llm_service import LLMService

        # Without a provider, should fall back to offline
        service = LLMService(provider=None, max_retries=3)
        result = service.review_expression("rank(returns)")
        assert result.provider_name == "offline_heuristic"

    def test_parameter_audit_no_config(self):
        from scripts.check_parameter_traceability import run_parameter_audit

        result = run_parameter_audit(config_path=None)
        assert "audit_version" in result
        # Without config, no settings to check → should pass
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════
# TypedDict Integration Tests
# ═══════════════════════════════════════════════════════════════════════


class TestTypedDictIntegration:
    """Test TypedDict definitions are valid and importable."""

    def test_all_web_typeddicts_importable(self):
        """Verify all web TypedDicts can be imported."""
        from brain_alpha_ops.types import (
            WebRouteResponse,
            CandidateListResponse,
            SimulationJobResponse,
            BacktestSlotResponse,
            CloudSnapshotResponse,
            ConfigResponse,
            SubmissionReadinessResponse,
            QualityCheckResponse,
            SSEEvent,
            UserSession,
        )
        # All imports should succeed
        assert WebRouteResponse is not None
        assert CandidateListResponse is not None
        assert SimulationJobResponse is not None
        assert BacktestSlotResponse is not None
        assert CloudSnapshotResponse is not None
        assert ConfigResponse is not None
        assert SubmissionReadinessResponse is not None
        assert QualityCheckResponse is not None
        assert SSEEvent is not None
        assert UserSession is not None

    def test_all_api_typeddicts_importable(self):
        """Verify all API TypedDicts can be imported."""
        from brain_alpha_ops.types import (
            OfficialMetrics,
            ScorecardDict,
            GateResultDict,
            BrainAPIResponse,
            CandidateDict,
            PipelineSummaryDict,
            RedlineViolationDict,
        )
        assert OfficialMetrics is not None
        assert ScorecardDict is not None
        assert GateResultDict is not None
        assert BrainAPIResponse is not None
        assert CandidateDict is not None
        assert PipelineSummaryDict is not None
        assert RedlineViolationDict is not None

    def test_typeddict_instances_are_dict(self):
        """Verify TypedDict instances work as dicts."""
        from brain_alpha_ops.types import OfficialMetrics
        metrics: OfficialMetrics = {"sharpe": 1.5, "fitness": 1.1}
        assert isinstance(metrics, dict)
        assert metrics["sharpe"] == 1.5


# ═══════════════════════════════════════════════════════════════════════
# PipelineServices Composition Tests
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineServicesComposition:
    """Test PipelineServices composition pattern."""

    def test_pipeline_services_property_exists(self):
        """Verify pipeline.services property is accessible."""
        from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
        from brain_alpha_ops.config import OpsConfig
        from tests.production_api_stub import ProductionBrainAPIStub

        config = OpsConfig()
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())

        services = pipeline.services
        assert services is not None

    def test_pipeline_services_has_expected_services(self):
        """Verify PipelineServices has all expected service objects."""
        from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
        from brain_alpha_ops.config import OpsConfig
        from tests.production_api_stub import ProductionBrainAPIStub

        config = OpsConfig()
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())

        services = pipeline.services
        assert hasattr(services, "candidate_pool")
        assert hasattr(services, "backtest_submission")
        assert hasattr(services, "official_workflow")
        assert hasattr(services, "experience_feedback")
        assert hasattr(services, "fusion_candidates")
        assert hasattr(services, "secondary_fusion")

    def test_pipeline_services_caching(self):
        """Verify PipelineServices caches service instances."""
        from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
        from brain_alpha_ops.config import OpsConfig
        from tests.production_api_stub import ProductionBrainAPIStub

        config = OpsConfig()
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())

        services1 = pipeline.services
        services2 = pipeline.services
        # Same instance should be returned (cached)
        assert services1 is services2


# ═══════════════════════════════════════════════════════════════════════
# End-to-End Alpha Lifecycle Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAlphaLifecycleEndToEnd:
    """End-to-end tests for the complete alpha lifecycle."""

    def test_alpha_generation_to_scoring(self):
        """Test complete flow from alpha generation to scoring."""
        from brain_alpha_ops.research.generator import CandidateGenerator
        from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
        from brain_alpha_ops.config import QualityThresholds

        # Generate a candidate
        generator = CandidateGenerator()
        candidates = generator.generate(5, dataset_id="pv1")
        assert len(candidates) > 0

        # Score the first candidate
        candidate = candidates[0]
        thresholds = QualityThresholds()
        scorecard = build_scorecard(candidate, thresholds)
        assert "total_score" in scorecard
        assert "decision_band" in scorecard
        assert 0 <= scorecard["total_score"] <= 100

    def test_alpha_scoring_with_official_metrics(self):
        """Test scoring with official BRAIN metrics."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.config import QualityThresholds

        # Create candidate with official metrics
        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Price momentum test",
        )
        candidate.official_metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.3,
            "self_correlation": 0.1,
            "prod_correlation": 0.2,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.3,
            "pass_fail": "PASS",
        }

        thresholds = QualityThresholds()
        scorecard = build_scorecard(candidate, thresholds)

        assert scorecard["total_score"] > 0
        assert scorecard["score_basis"] == "official_verified"

    def test_alpha_gate_evaluation(self):
        """Test hard gate evaluation with official metrics."""
        from brain_alpha_ops.scoring.gates import GateConfig, OFFICIAL_HARD_GATE_NAMES
        from brain_alpha_ops.config import QualityThresholds

        thresholds = QualityThresholds()
        gate_config = GateConfig(thresholds)

        # Add all official hard gates
        for gate_name in OFFICIAL_HARD_GATE_NAMES:
            gate_config.add_hard_gate(
                gate_name,
                lambda metrics, thresholds, name=gate_name: metrics.get(name, 0) > 0,
            )

        # Evaluate with passing metrics (include all required gates)
        metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover_min": 0.02,
            "turnover_platform": 0.5,
            "self_correlation": 0.1,
            "prod_correlation": 0.2,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.3,
        }

        result = gate_config.evaluate(metrics)
        # Check that all configured gates passed
        assert all(item.get("configured_passed") for item in result.check_items)

    def test_alpha_attribution_tree(self):
        """Test attribution tree generation."""
        from brain_alpha_ops.scoring.attribution import build_attribution_tree

        scorecard = {
            "total_score": 75.0,
            "prior": {"score": 80.0, "items": []},
            "empirical": {"score": 70.0, "items": []},
            "submission_checklist": {"score": 85.0, "items": []},
            "layer_weights": {"prior": 0.3, "empirical": 0.45, "checklist": 0.25},
        }

        tree = build_attribution_tree(scorecard)
        assert tree is not None
        assert tree.name == "total_score"
        assert len(tree.children) == 3  # prior, empirical, checklist

    def test_alpha_convergence_tracking(self):
        """Test convergence tracking across cycles."""
        from brain_alpha_ops.research.convergence import ConvergenceTracker

        tracker = ConvergenceTracker(window_size=5, stall_threshold=3)

        # Record cycles with improving scores
        for cycle in range(10):
            tracker.record_cycle(
                cycle=cycle,
                produced=10,
                passed_local=5,
                simulated=3,
                passed_gate=1,
                submitted=0,
                candidates=[],
            )

        summary = tracker.summary()
        assert "sharpe_trend" in summary
        assert "stalled" in summary
        assert "recommendation" in summary

    def test_alpha_official_api_simulation_flow(self):
        """Test simulation flow with stub API."""
        from tests.production_api_stub import ProductionBrainAPIStub

        api = ProductionBrainAPIStub()

        # Test simulation
        simulation_id = api.submit_simulation(
            "rank(ts_delta(close, 20))",
            {"region": "USA", "delay": 1, "universe": "TOP3000"},
        )
        assert simulation_id is not None

        # Test polling
        status = api.poll_simulation(simulation_id)
        assert status in ["RUNNING", "COMPLETED", "FAILED"]

    def test_alpha_check_and_submit_flow(self):
        """Test check and submit flow with stub API."""
        from tests.production_api_stub import ProductionBrainAPIStub

        api = ProductionBrainAPIStub()

        # Test check
        check = api.check_alpha("test_alpha_id")
        assert "status" in check

        # Test submit_simulation
        simulation_id = api.submit_simulation(
            "rank(ts_delta(close, 20))",
            {"region": "USA", "delay": 1},
        )
        assert simulation_id is not None

    def test_alpha_score_history_tracking(self):
        """Test score history tracking for convergence analysis."""
        from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem
        from brain_alpha_ops.models import Candidate

        scorer = OfficialScoringSystem(persist_history=False)

        # Create and score multiple candidates
        for i in range(5):
            candidate = Candidate(
                alpha_id=f"alpha_{i}",
                expression=f"rank(ts_delta(close, {20 + i}))",
                family="momentum",
                hypothesis=f"Test hypothesis {i}",
            )
            candidate.official_metrics = {
                "sharpe": 1.0 + i * 0.1,
                "fitness": 1.0 + i * 0.05,
                "turnover": 0.3,
                "pass_fail": "PASS",
            }
            result = scorer.evaluate(candidate)
            assert result.total_score > 0

        # Check score trend
        trend = scorer.get_score_trend("alpha_0")
        assert trend in ["improving", "stable", "declining", None]
