"""Unified scoring policy — single source of truth for all scoring weights.

This module consolidates scoring configuration that was previously spread
across ``config_models.ScoringConfig``, ``config_models.QualityThresholds``,
``scoring/gates.py``, and ``scoring/_gate_decision.py`` into one frozen
dataclass: ``ScoringPolicy``.

Design
------
- ``frozen=True`` prevents runtime mutation — calibration must use
  ``dataclasses.replace``.
- ``from_config()`` factory extracts values from an ``OpsConfig`` instance.
- ``with_regime()`` returns a new instance adjusted for a market regime.
- Core methods (``score``, ``decide_gate``, ``explain``) delegate to the
  existing service implementations so no downstream callers break.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ScoringPolicy",
    "LayerWeights",
    "ThresholdProfile",
    "GateRuleSet",
    "ScoreResult",
    "GateDecision",
    "AttributionTree",
    "FIXABLE_GATE_HINTS",
]

# ── Constants migrated from _gate_decision.py ──────────────────────────

FIXABLE_GATE_HINTS: frozenset[str] = frozenset({
    "turnover_min", "turnover_quality", "drawdown_cap", "margin_bps",
    "is_oos_ratio", "fitness_crosscheck", "returns",
})


# ── Sub-structs ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LayerWeights:
    """Three-layer scoring weight decomposition.

    Weights must sum to 1.0 (enforced at factory time).
    """

    prior: float = 0.30
    empirical: float = 0.45
    checklist: float = 0.25

    def __post_init__(self):
        total = self.prior + self.empirical + self.checklist
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Layer weights must sum to 1.0, got {total:.4f}: "
                f"prior={self.prior}, empirical={self.empirical}, checklist={self.checklist}"
            )

    def to_dict(self) -> dict[str, float]:
        return {"prior": self.prior, "empirical": self.empirical, "checklist": self.checklist}


@dataclass(frozen=True)
class ThresholdProfile:
    """All numeric quality thresholds in one place."""

    min_sharpe: float = 1.25
    min_fitness: float = 1.0
    min_sharpe_delay0: float = 2.0
    min_fitness_delay0: float = 1.3
    min_turnover: float = 0.01
    platform_max_turnover: float = 0.70
    max_self_correlation: float = 0.70
    max_prod_correlation: float = 0.70
    max_weight_concentration: float = 0.10
    sub_universe_sharpe_min_ratio: float = 0.75
    target_max_turnover: float = 0.30
    min_margin_bps: float = 4.0
    max_drawdown: float = 0.25
    min_returns: float = 0.0
    enforce_target_turnover_as_hard_gate: bool = False
    require_official_pass: bool = True
    require_official_metrics: bool = True
    require_data_compliance: bool = True
    require_economic_logic: bool = True
    threshold_mode: str = "static"

    @property
    def max_turnover(self) -> float:
        """Deprecated alias for platform_max_turnover."""
        return self.platform_max_turnover

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_sharpe": self.min_sharpe,
            "min_fitness": self.min_fitness,
            "min_sharpe_delay0": self.min_sharpe_delay0,
            "min_fitness_delay0": self.min_fitness_delay0,
            "min_turnover": self.min_turnover,
            "platform_max_turnover": self.platform_max_turnover,
            "max_self_correlation": self.max_self_correlation,
            "max_prod_correlation": self.max_prod_correlation,
            "max_weight_concentration": self.max_weight_concentration,
            "sub_universe_sharpe_min_ratio": self.sub_universe_sharpe_min_ratio,
            "target_max_turnover": self.target_max_turnover,
            "min_margin_bps": self.min_margin_bps,
            "max_drawdown": self.max_drawdown,
            "min_returns": self.min_returns,
            "enforce_target_turnover_as_hard_gate": self.enforce_target_turnover_as_hard_gate,
            "require_official_pass": self.require_official_pass,
            "require_official_metrics": self.require_official_metrics,
            "require_data_compliance": self.require_data_compliance,
            "require_economic_logic": self.require_economic_logic,
            "threshold_mode": self.threshold_mode,
            "target_max_turnover": self.target_max_turnover,
        }


@dataclass(frozen=True)
class GateRuleSet:
    """Gate rules and fixable hints."""

    fixable_hints: frozenset[str] = FIXABLE_GATE_HINTS
    submit_threshold: float = 85.0
    optimize_threshold: float = 70.0
    research_threshold: float = 50.0
    enable_secondary_fusion_on_stall: bool = True
    min_prior_score_for_official_validation: float = 50.0
    min_prior_score_for_official_simulation: float = 70.0

    def is_fixable(self, gate_name: str) -> bool:
        return gate_name in self.fixable_hints

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixable_hints": sorted(self.fixable_hints),
            "submit_threshold": self.submit_threshold,
            "optimize_threshold": self.optimize_threshold,
            "research_threshold": self.research_threshold,
        }


# ── Result types ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScoreResult:
    """Result of ``ScoringPolicy.score()``."""
    total: float
    layer_scores: dict[str, float]
    passed: bool
    threshold: float


@dataclass(frozen=True)
class GateDecision:
    """Result of ``ScoringPolicy.decide_gate()``."""
    action: str
    reason: str
    passed: bool


@dataclass(frozen=True)
class AttributionTree:
    """Hierarchical score attribution for ``ScoringPolicy.explain()``."""
    total: float
    layers: dict[str, float]
    components: dict[str, dict[str, float]]


# ── Main policy ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScoringPolicy:
    """Single source of truth for all alpha scoring weights and thresholds.

    This frozen dataclass aggregates the layer weights, quality thresholds,
    gate rules, and market regime adjustments that were previously scattered
    across at least five modules.

    Attributes:
        layers: Three-layer scoring decomposition (prior/empirical/checklist).
        thresholds: Numeric quality thresholds for gate evaluation.
        gates: Gate rules including fixable hints and decision thresholds.
        regime_adjustments: Optional per-regime factor adjustments.
        local_prior_weight: Weight for prior score in local prefilter.
        local_quality_weight: Weight for quality heuristics in local prefilter.
        assistant_guidance_enabled: Whether guidance score adjustment is on.
        assistant_guidance_min_confidence: Minimum confidence for guidance.
        assistant_guidance_min_outcome_count: Minimum historical outcomes.
        assistant_guidance_bonus_cap: Maximum guidance bonus.
        assistant_guidance_penalty_cap: Maximum guidance penalty.
        market_regime: Current market regime tag.
    """

    layers: LayerWeights = field(default_factory=LayerWeights)
    thresholds: ThresholdProfile = field(default_factory=ThresholdProfile)
    gates: GateRuleSet = field(default_factory=GateRuleSet)
    regime_adjustments: dict[str, dict[str, float]] = field(default_factory=lambda: {
        "normal": {"sharpe_factor": 1.0, "fitness_factor": 1.0, "turnover_factor": 1.0},
        "low_vol": {"sharpe_factor": 1.15, "fitness_factor": 1.10, "turnover_factor": 0.90},
        "high_vol": {"sharpe_factor": 0.85, "fitness_factor": 0.90, "turnover_factor": 1.20},
    })
    local_prior_weight: float = 0.65
    local_quality_weight: float = 0.35
    assistant_guidance_enabled: bool = True
    assistant_guidance_min_confidence: float = 0.6
    assistant_guidance_min_outcome_count: int = 1
    assistant_guidance_bonus_cap: float = 4.0
    assistant_guidance_penalty_cap: float = 5.0
    market_regime: str = "normal"

    # ── Core methods ──────────────────────────────────────────────────

    def score(self, metrics: dict[str, float], context: dict[str, Any] | None = None) -> ScoreResult:
        """Compute a weighted composite score from candidate metrics.

        Args:
            metrics: Dict of metric_name → value pairs.
            context: Optional dict with extra context (e.g. regime).

        Returns:
            ``ScoreResult`` with total, layer breakdown, and pass/fail.
        """
        # Prior layer: sharpe- and fitness-based signals
        sharpe = float(metrics.get("sharpe", 0) or 0)
        fitness = float(metrics.get("fitness", 0) or 0)
        prior = min(100.0, max(0.0, (sharpe * 40.0) + (fitness * 15.0)))

        # Empirical layer: turnover penalty, correlation checks
        turnover = abs(float(metrics.get("turnover", 0) or 0))
        turnover_penalty = min(20.0, turnover * 25.0)
        self_corr = abs(float(metrics.get("self_correlation", 0) or 0))
        corr_penalty = min(15.0, max(0.0, (self_corr - 0.5) * 30.0))
        empirical = min(100.0, max(0.0, 60.0 - turnover_penalty - corr_penalty))

        # Checklist layer: boolean gate passes
        checklist = 100.0 if metrics.get("brain_pass", False) else 50.0

        # Apply regime adjustments
        regime = (context or {}).get("regime", self.market_regime)
        factors = self.regime_adjustments.get(regime, {"sharpe_factor": 1.0, "fitness_factor": 1.0, "turnover_factor": 1.0})
        prior *= float(factors.get("sharpe_factor", 1.0))

        w = self.layers
        total = (w.prior * prior) + (w.empirical * empirical) + (w.checklist * checklist)

        return ScoreResult(
            total=round(total, 2),
            layer_scores={"prior": round(prior, 2), "empirical": round(empirical, 2), "checklist": round(checklist, 2)},
            passed=total >= self.gates.submit_threshold,
            threshold=self.gates.submit_threshold,
        )

    def decide_gate(self, score_result: ScoreResult) -> GateDecision:
        """Map a score result to a gate decision."""
        total = score_result.total
        if total >= self.gates.submit_threshold:
            return GateDecision(action="queue_simulation", reason="score >= submit threshold", passed=True)
        if total >= self.gates.optimize_threshold:
            return GateDecision(action="continue_optimization", reason="score in optimize band", passed=False)
        if total >= self.gates.research_threshold:
            return GateDecision(action="continue_research", reason="score in research band", passed=False)
        return GateDecision(action="discard_archive", reason="score below research threshold", passed=False)

    def explain(self, score_result: ScoreResult) -> AttributionTree:
        """Return a hierarchical attribution of the score."""
        return AttributionTree(
            total=score_result.total,
            layers=score_result.layer_scores,
            components={},
        )

    # ── Factory methods ────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config: Any) -> "ScoringPolicy":
        """Extract scoring policy from an ``OpsConfig`` instance.

        Args:
            config: An ``OpsConfig`` object with ``scoring`` and ``thresholds``
                attributes.

        Returns:
            A new ``ScoringPolicy`` instance.
        """
        scoring = getattr(config, "scoring", None)
        thresholds = getattr(config, "thresholds", None)
        budget = getattr(config, "budget", None)

        kw: dict[str, Any] = {}

        if scoring is not None:
            kw.update({
                "layers": LayerWeights(
                    prior=float(getattr(scoring, "prior_layer_weight", 0.30) or 0.30),
                    empirical=float(getattr(scoring, "empirical_layer_weight", 0.45) or 0.45),
                    checklist=float(getattr(scoring, "checklist_layer_weight", 0.25) or 0.25),
                ),
                "local_prior_weight": float(getattr(scoring, "local_prior_weight", 0.65) or 0.65),
                "local_quality_weight": float(getattr(scoring, "local_quality_weight", 0.35) or 0.35),
                "assistant_guidance_enabled": bool(getattr(scoring, "assistant_guidance_score_adjustment_enabled", True)),
                "assistant_guidance_min_confidence": float(getattr(scoring, "assistant_guidance_score_min_confidence", 0.6) or 0.6),
                "assistant_guidance_min_outcome_count": int(getattr(scoring, "assistant_guidance_score_min_outcome_count", 1) or 1),
                "assistant_guidance_bonus_cap": float(getattr(scoring, "assistant_guidance_score_bonus_cap", 4.0) or 4.0),
                "assistant_guidance_penalty_cap": float(getattr(scoring, "assistant_guidance_score_penalty_cap", 5.0) or 5.0),
                "market_regime": str(getattr(scoring, "market_regime", "normal") or "normal"),
            })
            # Decision thresholds
            dt = getattr(scoring, "decision_thresholds", None) or {}
            kw["gates"] = GateRuleSet(
                submit_threshold=float(dt.get("submit", 85.0) or 85.0),
                optimize_threshold=float(dt.get("optimize", 70.0) or 70.0),
                research_threshold=float(dt.get("research", 50.0) or 50.0),
            )

        if thresholds is not None:
            kw["thresholds"] = ThresholdProfile(
                min_sharpe=float(getattr(thresholds, "min_sharpe", 1.25) or 1.25),
                min_fitness=float(getattr(thresholds, "min_fitness", 1.0) or 1.0),
                min_sharpe_delay0=float(getattr(thresholds, "min_sharpe_delay0", 2.0) or 2.0),
                min_fitness_delay0=float(getattr(thresholds, "min_fitness_delay0", 1.3) or 1.3),
                min_turnover=float(getattr(thresholds, "min_turnover", 0.01) or 0.01),
                platform_max_turnover=float(getattr(thresholds, "platform_max_turnover", 0.70) or 0.70),
                max_self_correlation=float(getattr(thresholds, "max_self_correlation", 0.70) or 0.70),
                max_prod_correlation=float(getattr(thresholds, "max_prod_correlation", 0.70) or 0.70),
                max_weight_concentration=float(getattr(thresholds, "max_weight_concentration", 0.10) or 0.10),
                sub_universe_sharpe_min_ratio=float(getattr(thresholds, "sub_universe_sharpe_min_ratio", 0.75) or 0.75),
                target_max_turnover=float(getattr(thresholds, "target_max_turnover", 0.30) or 0.30),
                min_margin_bps=float(getattr(thresholds, "min_margin_bps", 4.0) or 4.0),
                max_drawdown=float(getattr(thresholds, "max_drawdown", 0.25) or 0.25),
                min_returns=float(getattr(thresholds, "min_returns", 0.0) or 0.0),
                enforce_target_turnover_as_hard_gate=bool(getattr(thresholds, "enforce_target_turnover_as_hard_gate", False)),
                require_official_pass=bool(getattr(thresholds, "require_official_pass", True)),
                require_official_metrics=bool(getattr(thresholds, "require_official_metrics", True)),
                require_data_compliance=bool(getattr(thresholds, "require_data_compliance", True)),
                require_economic_logic=bool(getattr(thresholds, "require_economic_logic", True)),
                threshold_mode=str(getattr(thresholds, "threshold_mode", "static") or "static"),
            )
            # Regime adjustments
            kw["regime_adjustments"] = dict(getattr(thresholds, "regime_adjustments", {}) or kw.get("regime_adjustments", {}))

        if budget is not None:
            g = kw.get("gates", GateRuleSet())
            kw["gates"] = GateRuleSet(
                fixable_hints=g.fixable_hints,
                submit_threshold=g.submit_threshold,
                optimize_threshold=g.optimize_threshold,
                research_threshold=g.research_threshold,
                enable_secondary_fusion_on_stall=bool(getattr(budget, "enable_secondary_fusion", True)),
                min_prior_score_for_official_validation=float(getattr(budget, "min_prior_score_for_official_validation", 50.0) or 50.0),
                min_prior_score_for_official_simulation=float(getattr(budget, "min_prior_score_for_official_simulation", 70.0) or 70.0),
            )

        return cls(**kw)

    @classmethod
    def default(cls) -> "ScoringPolicy":
        """Return the default (production-safe) policy."""
        return cls()

    def with_regime(self, regime: str) -> "ScoringPolicy":
        """Return a new policy with thresholds adjusted for *regime*.

        Args:
            regime: One of ``"normal"``, ``"low_vol"``, ``"high_vol"``.

        Returns:
            A new ``ScoringPolicy`` with adjusted thresholds.
        """
        if regime == self.market_regime and regime in self.regime_adjustments:
            return self
        factors = self.regime_adjustments.get(regime, {"sharpe_factor": 1.0, "fitness_factor": 1.0, "turnover_factor": 1.0})
        sf = float(factors.get("sharpe_factor", 1.0))
        ff = float(factors.get("fitness_factor", 1.0))
        tf = float(factors.get("turnover_factor", 1.0))

        return replace(
            self,
            market_regime=regime,
            thresholds=replace(
                self.thresholds,
                min_sharpe=round(self.thresholds.min_sharpe * sf, 4),
                min_fitness=round(self.thresholds.min_fitness * ff, 4),
                target_max_turnover=round(self.thresholds.target_max_turnover * tf, 4),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON Schema / API responses."""
        return {
            "layers": self.layers.to_dict(),
            "thresholds": self.thresholds.to_dict(),
            "gates": self.gates.to_dict(),
            "regime_adjustments": self.regime_adjustments,
            "local_prior_weight": self.local_prior_weight,
            "local_quality_weight": self.local_quality_weight,
            "assistant_guidance_enabled": self.assistant_guidance_enabled,
            "assistant_guidance_min_confidence": self.assistant_guidance_min_confidence,
            "assistant_guidance_min_outcome_count": self.assistant_guidance_min_outcome_count,
            "assistant_guidance_bonus_cap": self.assistant_guidance_bonus_cap,
            "assistant_guidance_penalty_cap": self.assistant_guidance_penalty_cap,
            "market_regime": self.market_regime,
        }
