from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANTI_OVERFIT_SCHEMA_VERSION = "anti_overfit_report.v1"

_IC_STABILITY_WINDOW_MIN = 20
_REGIME_MIN_SAMPLES = 30
_PLACEBO_TRIALS = 50
_DEFAULT_HALF_LIFE_WINDOW = 60
_MIN_CANDIDATE_SERIES = 60

SIMILARITY_THRESHOLD = 0.95
PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD = 0.05
DUPLICATE_SUBMISSION_WINDOW_DAYS = 7
HIGH_FREQUENCY_RETRY_THRESHOLD = 3


@dataclass
class AntiOverfitResult:
    """Structured result from the anti-overfitting validation suite."""

    passed: bool = False
    overall_score: float = 0.0

    ic_mean: float = 0.0
    ic_std: float = 0.0
    ic_stability_score: float = 0.0
    ic_monthly_means: list[float] = field(default_factory=list)

    bull_sharpe: float | None = None
    bear_sharpe: float | None = None
    sideways_sharpe: float | None = None
    regime_stability_score: float = 0.0

    placebo_p_value: float = 1.0
    placebo_score: float = 0.0

    half_life_days: float = 0.0
    half_life_score: float = 0.0

    dsr_score: float = 0.0
    trial_count: int = 0

    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    min_ic_mean: float = 0.02
    max_ic_std: float = 0.08
    min_half_life_days: float = 5.0
    placebo_alpha: float = 0.05

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "overall_score": self.overall_score,
            "ic_stability": {
                "ic_mean": self.ic_mean,
                "ic_std": self.ic_std,
                "score": self.ic_stability_score,
                "monthly_means": self.ic_monthly_means,
            },
            "regime_stress": {
                "bull_sharpe": self.bull_sharpe,
                "bear_sharpe": self.bear_sharpe,
                "sideways_sharpe": self.sideways_sharpe,
                "score": self.regime_stability_score,
            },
            "placebo": {
                "p_value": self.placebo_p_value,
                "score": self.placebo_score,
            },
            "half_life": {
                "days": self.half_life_days,
                "score": self.half_life_score,
            },
            "dsr": {
                "score": self.dsr_score,
                "trial_count": self.trial_count,
            },
            "warnings": self.warnings,
            "thresholds": {
                "min_ic_mean": self.min_ic_mean,
                "max_ic_std": self.max_ic_std,
                "min_half_life_days": self.min_half_life_days,
                "placebo_alpha": self.placebo_alpha,
            },
        }


@dataclass
class ComplianceGuardrailResult:
    """Result from compliance guardrail checks."""

    similarity_block: bool = False
    similarity_score: float = 0.0
    similarity_details: str = ""

    parameter_tweak_flag: bool = False
    parameter_tweak_details: str = ""

    duplicate_block: bool = False
    duplicate_details: str = ""

    high_frequency_block: bool = False
    high_frequency_failure_count: int = 0
    high_frequency_details: str = ""

    overall_blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "similarity": {
                "blocked": self.similarity_block,
                "score": self.similarity_score,
                "details": self.similarity_details,
            },
            "parameter_tweak": {
                "flagged": self.parameter_tweak_flag,
                "details": self.parameter_tweak_details,
            },
            "duplicate_submission": {
                "blocked": self.duplicate_block,
                "details": self.duplicate_details,
            },
            "high_frequency_retry": {
                "blocked": self.high_frequency_block,
                "failure_count": self.high_frequency_failure_count,
                "details": self.high_frequency_details,
            },
            "overall_blocked": self.overall_blocked,
            "block_reasons": self.block_reasons,
        }
