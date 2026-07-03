"""Unit tests for brain_alpha_ops.scoring.policy — ScoringPolicy & friends.

Covers:
  1. LayerWeights: creation, validation, defaults, to_dict
  2. ThresholdProfile: defaults, properties, to_dict
  3. GateRuleSet: defaults, is_fixable, to_dict
  4. ScoreResult / GateDecision / AttributionTree: frozen, defaults
  5. ScoringPolicy.default(): usable default policy
  6. ScoringPolicy.score(): composite scoring with/without regime
  7. ScoringPolicy.decide_gate(): correct action mapping
  8. ScoringPolicy.explain(): attribution tree shape
  9. ScoringPolicy.from_config(): factory from OpsConfig
  10. ScoringPolicy.with_regime(): returns new frozen instance
  11. ScoringPolicy frozen=True: mutation raises FrozenInstanceError
  12. FIXABLE_GATE_HINTS: constants match expectations
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.scoring.policy import (
    ScoringPolicy,
    LayerWeights,
    ThresholdProfile,
    GateRuleSet,
    ScoreResult,
    GateDecision,
    AttributionTree,
    FIXABLE_GATE_HINTS,
)


# ═══════════════════════════════════════════════════════════════
# LayerWeights
# ═══════════════════════════════════════════════════════════════

class TestLayerWeights:
    def test_default_weights_sum_to_one(self):
        w = LayerWeights()
        assert w.prior + w.empirical + w.checklist == pytest.approx(1.0)

    def test_custom_weights_valid(self):
        w = LayerWeights(prior=0.20, empirical=0.50, checklist=0.30)
        assert w.prior == 0.20
        assert w.empirical == 0.50
        assert w.checklist == 0.30

    def test_small_rounding_tolerated(self):
        w = LayerWeights(prior=0.333, empirical=0.333, checklist=0.334)
        assert w.prior + w.empirical + w.checklist == pytest.approx(1.0, abs=0.0011)

    def test_invalid_weights_raise(self):
        with pytest.raises(ValueError, match="must sum to 1"):
            LayerWeights(prior=0.5, empirical=0.5, checklist=0.5)

    def test_weights_frozen(self):
        w = LayerWeights()
        with pytest.raises(dataclasses.FrozenInstanceError):
            w.prior = 0.99  # type: ignore[misc]

    def test_to_dict_returns_correct_keys(self):
        d = LayerWeights(prior=0.30, empirical=0.45, checklist=0.25).to_dict()
        assert d == {"prior": 0.30, "empirical": 0.45, "checklist": 0.25}


# ═══════════════════════════════════════════════════════════════
# ThresholdProfile
# ═══════════════════════════════════════════════════════════════

class TestThresholdProfile:
    def test_defaults_are_production_safe(self):
        t = ThresholdProfile()
        assert t.min_sharpe == 1.25
        assert t.min_fitness == 1.0
        assert t.min_turnover == 0.01
        assert t.platform_max_turnover == 0.70
        assert t.max_self_correlation == 0.70
        assert t.require_official_pass is True
        assert t.threshold_mode == "static"

    def test_max_turnover_alias_points_to_platform_max_turnover(self):
        t = ThresholdProfile(platform_max_turnover=0.60)
        assert t.max_turnover == 0.60

    def test_frozen(self):
        t = ThresholdProfile()
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.min_sharpe = 99.0  # type: ignore[misc]

    def test_to_dict_contains_all_keys(self):
        d = ThresholdProfile().to_dict()
        assert "min_sharpe" in d
        assert "min_fitness" in d
        assert "max_self_correlation" in d
        assert "require_official_pass" in d
        assert d["min_sharpe"] == 1.25

    def test_custom_thresholds_persist(self):
        t = ThresholdProfile(min_sharpe=2.0, min_fitness=1.5, threshold_mode="dynamic")
        assert t.min_sharpe == 2.0
        assert t.threshold_mode == "dynamic"


# ═══════════════════════════════════════════════════════════════
# GateRuleSet
# ═══════════════════════════════════════════════════════════════

class TestGateRuleSet:
    def test_defaults(self):
        g = GateRuleSet()
        assert g.submit_threshold == 85.0
        assert g.optimize_threshold == 70.0
        assert g.research_threshold == 50.0
        assert g.enable_secondary_fusion_on_stall is True

    def test_is_fixable_known_gates(self):
        g = GateRuleSet()
        assert g.is_fixable("turnover_min") is True
        assert g.is_fixable("margin_bps") is True
        assert g.is_fixable("returns") is True

    def test_is_fixable_unknown_gate(self):
        g = GateRuleSet()
        assert g.is_fixable("nonexistent_gate") is False

    def test_to_dict_returns_sorted_fixable_hints(self):
        d = GateRuleSet().to_dict()
        assert "fixable_hints" in d
        assert d["fixable_hints"] == sorted(FIXABLE_GATE_HINTS)

    def test_custom_thresholds_persist(self):
        g = GateRuleSet(submit_threshold=90.0, optimize_threshold=75.0, research_threshold=55.0)
        assert g.submit_threshold == 90.0
        assert g.optimize_threshold == 75.0
        assert g.research_threshold == 55.0

    def test_frozen(self):
        g = GateRuleSet()
        with pytest.raises(dataclasses.FrozenInstanceError):
            g.submit_threshold = 99.0  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# ScoreResult
# ═══════════════════════════════════════════════════════════════

class TestScoreResult:
    def test_creation_and_fields(self):
        r = ScoreResult(total=88.5, layer_scores={"prior": 30.0, "empirical": 35.0, "checklist": 23.5}, passed=True, threshold=85.0)
        assert r.total == 88.5
        assert r.layer_scores["prior"] == 30.0
        assert r.passed is True
        assert r.threshold == 85.0

    def test_frozen(self):
        r = ScoreResult(total=50.0, layer_scores={}, passed=False, threshold=85.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.total = 99.0  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# GateDecision
# ═══════════════════════════════════════════════════════════════

class TestGateDecision:
    def test_creation_and_fields(self):
        gd = GateDecision(action="queue_simulation", reason="score >= submit threshold", passed=True)
        assert gd.action == "queue_simulation"
        assert gd.reason == "score >= submit threshold"
        assert gd.passed is True

    def test_frozen(self):
        gd = GateDecision(action="discard_archive", reason="low", passed=False)
        with pytest.raises(dataclasses.FrozenInstanceError):
            gd.action = "changed"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# AttributionTree
# ═══════════════════════════════════════════════════════════════

class TestAttributionTree:
    def test_creation_and_fields(self):
        at = AttributionTree(total=88.5, layers={"prior": 30.0, "empirical": 35.0, "checklist": 23.5}, components={})
        assert at.total == 88.5
        assert at.layers["prior"] == 30.0
        assert at.components == {}

    def test_frozen(self):
        at = AttributionTree(total=50.0, layers={}, components={})
        with pytest.raises(dataclasses.FrozenInstanceError):
            at.total = 99.0  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: default()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyDefault:
    def test_default_returns_usable_policy(self):
        p = ScoringPolicy.default()
        assert isinstance(p, ScoringPolicy)
        assert p.layers.prior == 0.30
        assert p.gates.submit_threshold == 85.0
        assert p.market_regime == "normal"

    def test_default_is_idempotent(self):
        p1 = ScoringPolicy.default()
        p2 = ScoringPolicy.default()
        assert p1.layers.to_dict() == p2.layers.to_dict()
        assert p1.gates.to_dict() == p2.gates.to_dict()
        # p1 and p2 are different instances
        assert p1 is not p2


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: score()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyScore:
    def test_score_high_metrics_passes(self):
        p = ScoringPolicy.default()
        # With best-possible metrics under default weights:
        #   prior:  sharpe=2.5,fitness=2.5 → min(100, 137.5)=100
        #   empirical: turnover=0,self_corr=0 → 60 (base) − 0 − 0 = 60
        #   checklist: brain_pass=True → 100
        #   total = 0.30×100 + 0.45×60 + 0.25×100 = 30+27+25 = 82
        # (Default gate=85 is unreachable with these weights; this is the configured behaviour.)
        metrics = {"sharpe": 2.5, "fitness": 2.5, "turnover": 0.0, "self_correlation": 0.0, "brain_pass": True}
        result = p.score(metrics)
        assert result.total == pytest.approx(82.0)
        assert result.total > 80
        assert result.passed is False  # below 85 submit threshold

    def test_score_low_metrics_fails(self):
        p = ScoringPolicy.default()
        metrics = {"sharpe": 0.3, "fitness": 0.4, "turnover": 0.9, "self_correlation": 0.95, "brain_pass": False}
        result = p.score(metrics)
        assert result.total < 50
        assert result.passed is False

    def test_score_missing_metrics_uses_zero_defaults(self):
        p = ScoringPolicy.default()
        result = p.score({})
        # All metrics default to 0 → prior = 0, empirical = 40, checklist = 50
        # prior: (0*40)+(0*15)=0 → 0. empirical: 60 - 0 - 0 = 60
        # total = 0.30*0 + 0.45*60 + 0.25*50 = 27 + 12.5 = 39.5
        assert result.total == pytest.approx(39.5)
        assert result.passed is False

    def test_score_with_none_metrics_treated_as_zero(self):
        p = ScoringPolicy.default()
        result = p.score({"sharpe": None, "fitness": None, "turnover": None, "self_correlation": None, "brain_pass": None})
        assert result.total == pytest.approx(39.5)
        assert result.passed is False

    def test_score_regime_context_overrides_default(self):
        p = ScoringPolicy.default()
        metrics = {"sharpe": 1.5, "fitness": 1.2, "turnover": 0.3, "self_correlation": 0.3, "brain_pass": True}
        # with "low_vol" regime, sharpe_factor=1.15 inflates prior
        result_normal = p.score(metrics, context={"regime": "normal"})
        result_low_vol = p.score(metrics, context={"regime": "low_vol"})
        assert result_low_vol.total > result_normal.total

    def test_score_returns_structured_result(self):
        p = ScoringPolicy.default()
        result = p.score({"sharpe": 1.0, "fitness": 1.0, "turnover": 0.2, "self_correlation": 0.4})
        assert isinstance(result, ScoreResult)
        assert "prior" in result.layer_scores
        assert "empirical" in result.layer_scores
        assert "checklist" in result.layer_scores
        assert result.threshold == 85.0

    def test_score_prior_capped_at_100(self):
        """sharpe=3.0, fitness=3.0 → prior = 120+45=165 → capped at 100"""
        p = ScoringPolicy.default()
        result = p.score({"sharpe": 3.0, "fitness": 3.0, "turnover": 0.0, "self_correlation": 0.0, "brain_pass": True})
        assert result.layer_scores["prior"] <= 100.0

    def test_score_empirical_capped_at_100(self):
        p = ScoringPolicy.default()
        result = p.score({"sharpe": 0.0, "fitness": 0.0, "turnover": 0.0, "self_correlation": 0.0, "brain_pass": True})
        assert result.layer_scores["empirical"] <= 100.0

    def test_score_negative_sharpe_produces_zero_prior(self):
        p = ScoringPolicy.default()
        result = p.score({"sharpe": -1.0, "fitness": 0.0, "turnover": 0.5, "self_correlation": 0.5})
        assert result.layer_scores["prior"] == 0.0


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: decide_gate()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyDecideGate:
    def test_above_submit_queues_simulation(self):
        p = ScoringPolicy.default()
        sr = ScoreResult(total=90.0, layer_scores={}, passed=True, threshold=85.0)
        gd = p.decide_gate(sr)
        assert gd.action == "queue_simulation"
        assert gd.passed is True

    def test_in_optimize_band(self):
        p = ScoringPolicy.default()
        sr = ScoreResult(total=80.0, layer_scores={}, passed=False, threshold=85.0)
        gd = p.decide_gate(sr)
        assert gd.action == "continue_optimization"
        assert gd.passed is False

    def test_in_research_band(self):
        p = ScoringPolicy.default()
        sr = ScoreResult(total=60.0, layer_scores={}, passed=False, threshold=85.0)
        gd = p.decide_gate(sr)
        assert gd.action == "continue_research"
        assert gd.passed is False

    def test_below_research_discards(self):
        p = ScoringPolicy.default()
        sr = ScoreResult(total=30.0, layer_scores={}, passed=False, threshold=85.0)
        gd = p.decide_gate(sr)
        assert gd.action == "discard_archive"
        assert gd.passed is False

    def test_boundary_exactly_at_threshold(self):
        p = ScoringPolicy.default()
        sr = ScoreResult(total=85.0, layer_scores={}, passed=True, threshold=85.0)
        gd = p.decide_gate(sr)
        assert gd.action == "queue_simulation"

    def test_boundary_just_below_optimize(self):
        p = ScoringPolicy.default()
        sr = ScoreResult(total=69.99, layer_scores={}, passed=False, threshold=85.0)
        gd = p.decide_gate(sr)
        assert gd.action == "continue_research"


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: explain()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyExplain:
    def test_explain_returns_attribution_tree(self):
        p = ScoringPolicy.default()
        sr = p.score({"sharpe": 1.5, "fitness": 1.1, "turnover": 0.2, "self_correlation": 0.3})
        at = p.explain(sr)
        assert isinstance(at, AttributionTree)
        assert at.total == sr.total
        assert at.layers == sr.layer_scores

    def test_explain_components_is_dict(self):
        p = ScoringPolicy.default()
        sr = p.score({"sharpe": 1.0, "fitness": 1.0})
        at = p.explain(sr)
        assert isinstance(at.components, dict)


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: from_config()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyFromConfig:
    @staticmethod
    def _make_ops_config(scoring_attrs=None, thresholds_attrs=None, budget_attrs=None):
        """Build a minimal OpsConfig-like object with optional overrides."""
        from unittest.mock import MagicMock

        config = MagicMock()

        # Scoring sub-object
        scoring = MagicMock()
        defaults_s = {
            "prior_layer_weight": 0.30, "empirical_layer_weight": 0.45, "checklist_layer_weight": 0.25,
            "local_prior_weight": 0.65, "local_quality_weight": 0.35,
            "assistant_guidance_score_adjustment_enabled": True,
            "assistant_guidance_score_min_confidence": 0.6,
            "assistant_guidance_score_min_outcome_count": 1,
            "assistant_guidance_score_bonus_cap": 4.0,
            "assistant_guidance_score_penalty_cap": 5.0,
            "market_regime": "normal",
            "decision_thresholds": {"submit": 85.0, "optimize": 70.0, "research": 50.0},
        }
        if scoring_attrs:
            defaults_s.update(scoring_attrs)
        for k, v in defaults_s.items():
            setattr(scoring, k, v)
        config.scoring = scoring

        # Thresholds sub-object
        thresholds = MagicMock()
        defaults_t = {
            "min_sharpe": 1.25, "min_fitness": 1.0, "min_sharpe_delay0": 2.0,
            "min_fitness_delay0": 1.3, "min_turnover": 0.01, "platform_max_turnover": 0.70,
            "max_self_correlation": 0.70, "max_prod_correlation": 0.70,
            "max_weight_concentration": 0.10, "sub_universe_sharpe_min_ratio": 0.75,
            "target_max_turnover": 0.30, "min_margin_bps": 4.0, "max_drawdown": 0.25,
            "min_returns": 0.0, "enforce_target_turnover_as_hard_gate": False,
            "require_official_pass": True, "require_official_metrics": True,
            "require_data_compliance": True, "require_economic_logic": True,
            "threshold_mode": "static", "regime_adjustments": {},
        }
        if thresholds_attrs:
            defaults_t.update(thresholds_attrs)
        for k, v in defaults_t.items():
            setattr(thresholds, k, v)
        config.thresholds = thresholds

        # Budget sub-object
        budget = MagicMock()
        defaults_b = {
            "enable_secondary_fusion": True,
            "min_prior_score_for_official_validation": 50.0,
            "min_prior_score_for_official_simulation": 70.0,
        }
        if budget_attrs:
            defaults_b.update(budget_attrs)
        for k, v in defaults_b.items():
            setattr(budget, k, v)
        config.budget = budget

        return config

    def test_from_default_config_produces_valid_policy(self):
        config = self._make_ops_config()
        p = ScoringPolicy.from_config(config)
        assert isinstance(p, ScoringPolicy)
        assert p.layers.prior == 0.30
        assert p.gates.submit_threshold == 85.0
        assert p.market_regime == "normal"

    def test_custom_layer_weights_from_config(self):
        config = self._make_ops_config(scoring_attrs={"prior_layer_weight": 0.25, "empirical_layer_weight": 0.50, "checklist_layer_weight": 0.25})
        p = ScoringPolicy.from_config(config)
        assert p.layers.prior == 0.25
        assert p.layers.empirical == 0.50

    def test_custom_thresholds_from_config(self):
        config = self._make_ops_config(thresholds_attrs={"min_sharpe": 2.0, "max_drawdown": 0.15})
        p = ScoringPolicy.from_config(config)
        assert p.thresholds.min_sharpe == 2.0
        assert p.thresholds.max_drawdown == 0.15

    def test_custom_gate_thresholds_from_decision_thresholds(self):
        config = self._make_ops_config(scoring_attrs={
            "decision_thresholds": {"submit": 90.0, "optimize": 75.0, "research": 55.0}
        })
        p = ScoringPolicy.from_config(config)
        assert p.gates.submit_threshold == 90.0
        assert p.gates.optimize_threshold == 75.0
        assert p.gates.research_threshold == 55.0

    def test_from_config_missing_scoring_falls_back_to_defaults(self):
        config = self._make_ops_config()
        del config.scoring
        p = ScoringPolicy.from_config(config)
        assert p.layers.prior == 0.30  # default

    def test_from_config_missing_thresholds_falls_back_to_defaults(self):
        config = self._make_ops_config()
        del config.thresholds
        p = ScoringPolicy.from_config(config)
        assert p.thresholds.min_sharpe == 1.25  # default

    def test_from_config_regime_adjustments_propagated(self):
        config = self._make_ops_config(thresholds_attrs={
            "regime_adjustments": {"custom_regime": {"sharpe_factor": 0.5, "fitness_factor": 0.5, "turnover_factor": 0.5}}
        })
        p = ScoringPolicy.from_config(config)
        assert "custom_regime" in p.regime_adjustments

    def test_from_config_budget_override(self):
        config = self._make_ops_config(budget_attrs={
            "enable_secondary_fusion": False,
            "min_prior_score_for_official_validation": 60.0,
            "min_prior_score_for_official_simulation": 80.0,
        })
        p = ScoringPolicy.from_config(config)
        assert p.gates.enable_secondary_fusion_on_stall is False
        assert p.gates.min_prior_score_for_official_validation == 60.0
        assert p.gates.min_prior_score_for_official_simulation == 80.0


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: with_regime()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyWithRegime:
    def test_with_regime_returns_new_instance(self):
        p = ScoringPolicy.default()
        p2 = p.with_regime("low_vol")
        assert p2 is not p
        assert p2.market_regime == "low_vol"

    def test_with_regime_adjusts_thresholds(self):
        p = ScoringPolicy.default()
        p2 = p.with_regime("low_vol")
        # low_vol: sharpe_factor=1.15 → min_sharpe should increase
        assert p2.thresholds.min_sharpe == pytest.approx(p.thresholds.min_sharpe * 1.15)
        assert p2.thresholds.min_fitness == pytest.approx(p.thresholds.min_fitness * 1.10)
        assert p2.thresholds.target_max_turnover == pytest.approx(p.thresholds.target_max_turnover * 0.90)

    def test_with_regime_high_vol(self):
        p = ScoringPolicy.default()
        p2 = p.with_regime("high_vol")
        # high_vol: sharpe_factor=0.85 → min_sharpe should decrease
        assert p2.thresholds.min_sharpe == pytest.approx(p.thresholds.min_sharpe * 0.85)

    def test_with_regime_same_regime_returns_self(self):
        p = ScoringPolicy.default()
        p2 = p.with_regime("normal")
        assert p2 is p  # same regime, returns self

    def test_with_regime_unknown_regime_uses_identity_factors(self):
        p = ScoringPolicy.default()
        p2 = p.with_regime("unknown_regime")
        assert p2.market_regime == "unknown_regime"
        # Identity factors → thresholds unchanged
        assert p2.thresholds.min_sharpe == p.thresholds.min_sharpe

    def test_with_regime_does_not_mutate_original(self):
        p = ScoringPolicy.default()
        _ = p.with_regime("low_vol")
        # Original still has "normal" regime
        assert p.market_regime == "normal"
        assert p.thresholds.min_sharpe == 1.25


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: frozen=True
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyFrozen:
    def test_cannot_mutate_layers(self):
        p = ScoringPolicy.default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.layers = LayerWeights()  # type: ignore[misc]

    def test_cannot_mutate_thresholds(self):
        p = ScoringPolicy.default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.thresholds = ThresholdProfile()  # type: ignore[misc]

    def test_cannot_mutate_gates(self):
        p = ScoringPolicy.default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.gates = GateRuleSet()  # type: ignore[misc]

    def test_cannot_mutate_regime_adjustments(self):
        p = ScoringPolicy.default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.regime_adjustments = {}  # type: ignore[misc]

    def test_cannot_mutate_scalar_fields(self):
        p = ScoringPolicy.default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.market_regime = "changed"  # type: ignore[misc]

    def test_can_use_dataclasses_replace_for_updates(self):
        p = ScoringPolicy.default()
        p2 = dataclasses.replace(p, market_regime="low_vol")
        assert p2.market_regime == "low_vol"
        assert p.market_regime == "normal"  # original unchanged


# ═══════════════════════════════════════════════════════════════
# ScoringPolicy: to_dict()
# ═══════════════════════════════════════════════════════════════

class TestScoringPolicyToDict:
    def test_to_dict_contains_expected_top_level_keys(self):
        d = ScoringPolicy.default().to_dict()
        for key in ("layers", "thresholds", "gates", "regime_adjustments", "market_regime"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_roundtrips_layer_weights(self):
        d = ScoringPolicy.default().to_dict()
        assert d["layers"]["prior"] == 0.30

    def test_to_dict_roundtrips_gate_thresholds(self):
        d = ScoringPolicy.default().to_dict()
        assert d["gates"]["submit_threshold"] == 85.0


# ═══════════════════════════════════════════════════════════════
# FIXABLE_GATE_HINTS constants
# ═══════════════════════════════════════════════════════════════

class TestFixableGateHints:
    def test_is_frozenset(self):
        assert isinstance(FIXABLE_GATE_HINTS, frozenset)

    def test_contains_expected_gates(self):
        assert "turnover_min" in FIXABLE_GATE_HINTS
        assert "turnover_quality" in FIXABLE_GATE_HINTS
        assert "drawdown_cap" in FIXABLE_GATE_HINTS
        assert "margin_bps" in FIXABLE_GATE_HINTS
        assert "is_oos_ratio" in FIXABLE_GATE_HINTS
        assert "fitness_crosscheck" in FIXABLE_GATE_HINTS
        assert "returns" in FIXABLE_GATE_HINTS
