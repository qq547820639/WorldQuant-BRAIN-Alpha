"""Release decision orchestration for the release score gate.

Split from the former ``brain_alpha_ops/scoring/release_score_gate.py`` monolith
(deep-optimization-phase13). Combines the official snapshot, threshold policy,
and per-metric attribution builders into a single :class:`GateDecision`.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.scoring.release_score_gate._checks import (
    _cmp_optional_max,
    _cmp_required_max,
    _cmp_required_min,
    _official_pass_attr,
    _sub_universe_sharpe_attr,
    _threshold_trace,
)
from brain_alpha_ops.scoring.release_score_gate._models import (
    GateDecision,
    OfficialSnapshot,
    ThresholdPolicy,
)


def decide_release(official: OfficialSnapshot, policy: ThresholdPolicy) -> GateDecision:
    """Return a release decision by comparing official values only."""
    attrs = [
        _official_pass_attr(official, policy),
        _cmp_required_min(policy, "sharpe", official.sharpe, policy.min_sharpe, "ERROR", "official Sharpe below release threshold"),
        _cmp_required_min(policy, "fitness", official.fitness, policy.min_fitness, "ERROR", "official Fitness below release threshold"),
        _cmp_required_min(policy, "turnover_floor", official.turnover, policy.min_turnover, "WARN", "official Turnover below platform floor"),
        _cmp_required_max(policy, "turnover_cap", official.turnover, policy.max_turnover, "ERROR", "official Turnover above platform cap"),
        _cmp_optional_max("drawdown_cap", official.drawdown, policy.max_drawdown, "WARN", "official Drawdown above quality target"),
        _cmp_required_max(
            policy,
            "self_correlation_cap",
            official.self_correlation,
            policy.max_self_correlation,
            "ERROR",
            "official self-correlation above release cap",
        ),
        _cmp_required_max(
            policy,
            "prod_correlation_cap",
            official.prod_correlation,
            policy.max_prod_correlation,
            "ERROR",
            "official prod-correlation above release cap",
        ),
        _cmp_required_max(
            policy,
            "weight_concentration_cap",
            official.weight_concentration,
            policy.max_weight_concentration,
            "ERROR",
            "official weight concentration above release cap",
        ),
        _sub_universe_sharpe_attr(official, policy),
    ]
    hard_fail = any((not item.passed) and item.severity == "ERROR" for item in attrs)
    warn_only = (not hard_fail) and any(not item.passed for item in attrs)
    return GateDecision(
        status="FAIL" if hard_fail else ("WARN" if warn_only else "PASS"),
        pass_fail=not hard_fail,
        official_snapshot=asdict(official),
        attributions=tuple(asdict(item) for item in attrs),
        threshold_trace=_threshold_trace(policy, official),
    )


def evaluate_release_score(
    metrics: Mapping[str, Any] | None,
    thresholds: QualityThresholds | ThresholdPolicy,
    settings: Mapping[str, Any] | Any | None = None,
) -> GateDecision:
    effective_settings = settings if settings is not None else metrics
    policy = (
        thresholds
        if isinstance(thresholds, ThresholdPolicy)
        else ThresholdPolicy.from_thresholds(thresholds, settings=effective_settings)
    )
    return decide_release(OfficialSnapshot.from_metrics(metrics), policy)
