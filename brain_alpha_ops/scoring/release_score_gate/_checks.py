"""Attribution builders and threshold tracing for the release score gate.

Split from the former ``brain_alpha_ops/scoring/release_score_gate.py`` monolith
(deep-optimization-phase13). Each builder returns a :class:`ScoreAttribution`
describing how an official metric compares against the release policy, plus the
threshold-trace helper that records the resolved inputs for explainability.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.scoring._score_comparisons import (
    max_check,
    min_check,
    sub_universe_sharpe_formula,
)
from brain_alpha_ops.scoring.release_score_gate._models import (
    OfficialSnapshot,
    ScoreAttribution,
    ThresholdPolicy,
)


def _official_pass_attr(official: OfficialSnapshot, policy: ThresholdPolicy) -> ScoreAttribution:
    actual = (official.pass_fail or "").upper() or None
    if not policy.require_official_pass:
        return ScoreAttribution("official_pass_fail", True, actual, "PASS", "INFO", "official pass/fail not required")
    passed = actual == "PASS"
    return ScoreAttribution(
        "official_pass_fail",
        passed,
        actual,
        "PASS",
        "ERROR",
        "official Alpha Check pass_fail must be PASS",
    )


# _cmp_min: imported from _score_comparisons


def _cmp_required_min(
    policy: ThresholdPolicy,
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
) -> ScoreAttribution:
    if actual is None and not policy.require_official_metrics:
        return ScoreAttribution(name, True, actual, expected, "INFO", f"{reason}; metric not required")
    result = min_check(name, actual, expected, severity, reason, pass_fail=True)
    return ScoreAttribution(**result)


# _cmp_max: imported from _score_comparisons


def _cmp_required_max(
    policy: ThresholdPolicy,
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
) -> ScoreAttribution:
    if actual is None and not policy.require_official_metrics:
        return ScoreAttribution(name, True, actual, expected, "INFO", f"{reason}; metric not required")
    result = max_check(name, actual, expected, severity, reason, pass_fail=True)
    return ScoreAttribution(**result)


def _cmp_optional_max(
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
) -> ScoreAttribution:
    if actual is None:
        return ScoreAttribution(name, True, actual, expected, "INFO", f"{reason}; metric not provided")
    result = max_check(name, actual, expected, severity, reason, pass_fail=True)
    return ScoreAttribution(**result)


def _sub_universe_sharpe_attr(official: OfficialSnapshot, policy: ThresholdPolicy) -> ScoreAttribution:
    expected = _sub_universe_sharpe_threshold(official, policy)
    if (official.sub_universe_sharpe is None or expected is None) and not policy.require_official_metrics:
        return ScoreAttribution(
            "sub_universe_sharpe",
            True,
            official.sub_universe_sharpe,
            expected,
            "INFO",
            "official sub-universe Sharpe metric not required",
        )
    if expected is None:
        missing = _missing_sub_universe_threshold_inputs(official)
        return ScoreAttribution(
            "sub_universe_sharpe",
            False,
            official.sub_universe_sharpe,
            None,
            "ERROR",
            "official sub-universe Sharpe threshold cannot be traced without " + ", ".join(missing),
        )
    passed = (
        official.sub_universe_sharpe is not None
        and expected is not None
        and official.sub_universe_sharpe >= expected
    )
    return ScoreAttribution(
        "sub_universe_sharpe",
        passed,
        official.sub_universe_sharpe,
        expected,
        "ERROR",
        "official sub-universe Sharpe below BRAIN LOW_SUB_UNIVERSE_SHARPE threshold",
    )


def _sub_universe_sharpe_threshold(official: OfficialSnapshot, policy: ThresholdPolicy) -> float | None:
    return sub_universe_sharpe_formula(
        official.sharpe,
        official.sub_universe_size,
        official.alpha_size,
        policy.sub_universe_sharpe_min_ratio,
    )


def _missing_sub_universe_threshold_inputs(official: OfficialSnapshot) -> list[str]:
    missing: list[str] = []
    if official.sharpe is None:
        missing.append("sharpe")
    if official.sub_universe_sharpe is None:
        missing.append("sub_universe_sharpe/subUniverseSharpe")
    if official.sub_universe_size is None or official.sub_universe_size <= 0:
        missing.append("subUniverseSize")
    if official.alpha_size is None or official.alpha_size <= 0:
        missing.append("alphaSize")
    return missing or ["official size evidence"]


def _threshold_trace(policy: ThresholdPolicy, official: OfficialSnapshot) -> dict[str, Any]:
    sub_threshold = _sub_universe_sharpe_threshold(official, policy)
    size_factor = None
    if (
        official.sub_universe_size is not None
        and official.sub_universe_size > 0
        and official.alpha_size is not None
        and official.alpha_size > 0
    ):
        size_factor = round((official.sub_universe_size / official.alpha_size) ** 0.5, 8)
    return {
        "delay": policy.delay,
        "delay_source": policy.delay_source,
        "sharpe_threshold_key": policy.min_sharpe_source,
        "fitness_threshold_key": policy.min_fitness_source,
        "min_sharpe_used": policy.min_sharpe,
        "min_fitness_used": policy.min_fitness,
        "sub_universe_sharpe_formula": "sub_universe_sharpe >= sub_universe_sharpe_min_ratio * sqrt(subUniverseSize / alphaSize) * sharpe",
        "sub_universe_sharpe_min_ratio": policy.sub_universe_sharpe_min_ratio,
        "sub_universe_sharpe_inputs": {
            "sharpe": official.sharpe,
            "subUniverseSharpe": official.sub_universe_sharpe,
            "subUniverseSize": official.sub_universe_size,
            "alphaSize": official.alpha_size,
            "size_factor": size_factor,
            "expected": sub_threshold,
        },
    }
