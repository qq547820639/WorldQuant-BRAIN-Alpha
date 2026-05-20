"""Tests for research budget limits, submission policy, and safety checks.

Covers components that had archive test coverage but with current API signatures:
- ResearchBudget limits (config.py)
- SubmissionPolicy daily/run/interval limits
- SubmissionLedger safety checks (safety.py)
- Mock source detection
"""

import pytest
from brain_alpha_ops.config import (
    ConfigValidationError,
    ResearchBudget,
    RunConfig,
    SubmissionPolicy,
    QualityThresholds,
    validate_run_config,
)
from brain_alpha_ops.research.safety import SubmissionLedger, mock_source_reasons, normalize, similarity


# ═══════════════════════════════════════════════════════════════════════
# Budget tests
# ═══════════════════════════════════════════════════════════════════════

class TestResearchBudget:
    def test_default_budget_limits(self):
        budget = ResearchBudget()
        assert budget.max_candidates_per_cycle == 20
        assert budget.max_official_simulations_per_cycle == 3
        assert budget.retained_alpha_pool_size == 10
        assert budget.min_prior_score_for_official_validation == 60.0
        assert budget.min_prior_score_for_official_simulation == 70.0

    def test_custom_budget(self):
        budget = ResearchBudget(
            max_candidates_per_cycle=10,
            max_official_simulations_per_cycle=2,
            retained_alpha_pool_size=5,
        )
        assert budget.max_candidates_per_cycle == 10
        assert budget.max_official_simulations_per_cycle == 2
        assert budget.retained_alpha_pool_size == 5

    def test_dataset_strategy_defaults(self):
        budget = ResearchBudget()
        assert budget.dataset_strategy == "rotate"
        assert budget.generation_mode_ratio == "70/20/10"

    def test_adaptive_strategy_defaults(self):
        budget = ResearchBudget()
        assert budget.adaptive_strategy_enabled is True
        assert budget.adaptive_min_official_results == 12
        assert budget.adaptive_min_cycles == 20

    def test_strategy_plugin_defaults_are_disabled(self):
        budget = ResearchBudget()
        assert budget.strategy_plugins_enabled is False
        assert budget.strategy_plugin_specs == []

    def test_strategy_plugin_config_validation_rejects_bad_specs(self):
        config = RunConfig()
        config.ops.budget.strategy_plugins_enabled = True
        config.ops.budget.strategy_plugin_specs = ["valid.module:Plugin", ""]

        with pytest.raises(ConfigValidationError, match="strategy_plugin_specs"):
            validate_run_config(config)


# ═══════════════════════════════════════════════════════════════════════
# Submission policy tests
# ═══════════════════════════════════════════════════════════════════════

class TestSubmissionPolicy:
    def test_default_policy_limits(self):
        policy = SubmissionPolicy()
        assert policy.max_auto_submissions_per_day == 3
        assert policy.max_auto_submissions_per_run == 2
        assert policy.min_minutes_between_auto_submissions == 120
        assert policy.max_expression_similarity == 0.90

    def test_policy_micro_variants_blocked(self):
        policy = SubmissionPolicy()
        assert policy.block_micro_variants is True
        assert policy.require_pre_submit_check_passed is True

    def test_custom_policy(self):
        policy = SubmissionPolicy(
            max_auto_submissions_per_day=5,
            max_auto_submissions_per_run=3,
            max_expression_similarity=0.85,
        )
        assert policy.max_auto_submissions_per_day == 5
        assert policy.max_auto_submissions_per_run == 3
        assert policy.max_expression_similarity == 0.85


# ═══════════════════════════════════════════════════════════════════════
# Safety tests
# ═══════════════════════════════════════════════════════════════════════

class TestSafety:
    def test_similarity_identical(self):
        result = similarity("rank(ts_delta(close, 20))", "rank(ts_delta(close, 20))")
        assert result == pytest.approx(1.0, abs=0.01)

    def test_similarity_very_different(self):
        result = similarity("rank(ts_delta(close, 20))", "group_rank(open, sector)")
        assert result < 0.5

    def test_normalize_removes_whitespace(self):
        a = normalize("  rank ( ts_delta ( close , 20 ) )  ")
        b = normalize("rank(ts_delta(close,20))")
        assert a == b

    def test_mock_source_detection(self):
        # mock_source_reasons accepts a candidate-like dict and returns reasons list
        assert len(mock_source_reasons({"alpha_id": "mock_alpha_001"})) > 0
        assert len(mock_source_reasons({"alpha_id": "demo_alpha_001"})) > 0
        assert len(mock_source_reasons({"alpha_id": "test_something"})) > 0
        assert len(mock_source_reasons({"alpha_id": "dry_run_test"})) > 0
        assert len(mock_source_reasons({"alpha_id": "real_alpha_id"})) == 0


# ═══════════════════════════════════════════════════════════════════════
# Threshold alignment tests (archive test_project_assessment equivalent)
# ═══════════════════════════════════════════════════════════════════════

class TestThresholdAlignment:
    """Verify all thresholds match BRAIN official Alpha Check standards."""

    def test_platform_hard_gates(self):
        t = QualityThresholds()
        # BRAIN: LOW_SHARPE if < 1.25 (Delay-1)
        assert t.min_sharpe == 1.25
        # BRAIN: LOW_FITNESS if < 1.0 (Delay-1)
        assert t.min_fitness == 1.0
        # BRAIN: HIGH_TURNOVER if > 70%
        assert t.platform_max_turnover == 0.70
        # BRAIN: SELF_CORRELATION if >= 0.70
        assert t.max_self_correlation == 0.70
        # BRAIN: CONCENTRATED_WEIGHT if single stock > 10%
        assert t.max_weight_concentration == 0.10

    def test_delay_aware_thresholds(self):
        t = QualityThresholds()
        # Delay-0 has higher bars
        assert t.min_sharpe_delay0 == 2.0
        assert t.min_fitness_delay0 == 1.3
        assert t.min_sharpe_delay0 > t.min_sharpe
        assert t.min_fitness_delay0 > t.min_fitness

    def test_advisor_quality_targets(self):
        t = QualityThresholds()
        assert t.target_max_turnover == 0.30
        assert t.min_margin_bps == 4.0

    def test_enforce_turnover_as_hard_gate_default(self):
        t = QualityThresholds()
        assert t.enforce_target_turnover_as_hard_gate is False

    def test_enforce_turnover_as_hard_gate_enabled(self):
        t = QualityThresholds(enforce_target_turnover_as_hard_gate=True)
        assert t.enforce_target_turnover_as_hard_gate is True

    def test_sub_universe_sharpe_ratio(self):
        t = QualityThresholds()
        # BRAIN: sub_sharpe < 0.75 × √(sub/alpha) × alpha_sharpe
        assert t.sub_universe_sharpe_min_ratio == 0.75
