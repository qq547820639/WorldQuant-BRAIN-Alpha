"""Scientific scoring layer for BRAIN Alpha Ops."""

from brain_alpha_ops.scoring.anti_overfit import (
    AntiOverfitResult,
    compute_ic_stability,
    compute_placebo_test,
    compute_regime_stress,
    estimate_half_life,
    run_anti_overfit_suite,
)
from brain_alpha_ops.scoring.history import ScoreHistoryDB
from brain_alpha_ops.scoring.release_score_gate import (
    GateDecision,
    OfficialSnapshot,
    ScoreAttribution,
    ThresholdPolicy,
    decide_release,
    evaluate_release_score,
)

__all__ = [
    "GateDecision",
    "OfficialSnapshot",
    "ScoreAttribution",
    "ThresholdPolicy",
    "ScoreHistoryDB",
    "AntiOverfitResult",
    "run_anti_overfit_suite",
    "compute_ic_stability",
    "compute_regime_stress",
    "compute_placebo_test",
    "estimate_half_life",
    "decide_release",
    "evaluate_release_score",
]
