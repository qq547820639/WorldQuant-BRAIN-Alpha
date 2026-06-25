"""Reason builders for local-quality, scorecard, official-evidence, and gate checks.

Extracted from the original ``alpha_quality.py`` monolith.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.config_models import OpsConfig, RunConfig
from brain_alpha_ops.models import Candidate

from .constants import _REQUIRED_OFFICIAL_METRICS
from .utils import (
    _finite_number,
    _metric_value,
    _ops_from_config,
    _ratio,
    _reason,
)


def _add_local_quality_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    local_quality = candidate.local_quality if isinstance(candidate.local_quality, dict) else {}
    if not local_quality:
        reasons.append(_reason(
            "missing_local_quality",
            "missing",
            "blocking",
            "Local quality result is missing",
            field="local_quality",
            expected="local quality score and pass flag",
        ))
        return
    score = _finite_number(local_quality.get("score"))
    threshold = _finite_number(local_quality.get("threshold"))
    if score is None or score < 0 or score > 100:
        reasons.append(_reason(
            "local_quality_score_out_of_bounds",
            "numeric_out_of_bounds",
            "blocking",
            "Local quality score is not within 0..100",
            field="local_quality.score",
            value=local_quality.get("score"),
            expected="0..100",
        ))
    if threshold is None or threshold < 0 or threshold > 100:
        reasons.append(_reason(
            "local_quality_threshold_out_of_bounds",
            "numeric_out_of_bounds",
            "blocking",
            "Local quality threshold is not within 0..100",
            field="local_quality.threshold",
            value=local_quality.get("threshold"),
            expected="0..100",
        ))
    if local_quality.get("passed") is False:
        reasons.append(_reason(
            "local_quality_failed",
            "local_quality_failed",
            "blocking",
            "Local quality prefilter did not pass",
            field="local_quality.passed",
            value=False,
            expected=True,
        ))
    local_backtest = local_quality.get("local_backtest")
    if isinstance(local_backtest, dict) and local_backtest.get("pass_local") is False:
        failed_reasons = [
            str(reason)
            for reason in local_backtest.get("reasons", [])
            if str(reason)
        ]
        if local_backtest.get("advisory") is True:
            reason = _reason(
                "local_backtest_advisory_failed",
                "local_quality_advisory",
                "warning",
                "Exploratory local backtest did not meet synthetic thresholds",
                field="local_quality.local_backtest.pass_local",
                value=False,
                expected="official BRAIN simulation remains the source of truth",
            )
            if failed_reasons:
                reason["details"] = failed_reasons[:5]
            reasons.append(reason)
            return
        reason = _reason(
            "local_backtest_failed",
            "local_quality_failed",
            "blocking",
            "Local backtest did not meet submission thresholds",
            field="local_quality.local_backtest.pass_local",
            value=False,
            expected=True,
        )
        if failed_reasons:
            reason["details"] = failed_reasons[:5]
        reasons.append(reason)


def _add_scorecard_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    scorecard = candidate.scorecard if isinstance(candidate.scorecard, dict) else {}
    if not scorecard:
        reasons.append(_reason(
            "missing_scorecard",
            "missing",
            "blocking",
            "Scorecard is missing",
            field="scorecard",
            expected="scorecard with decision_band",
        ))
        return
    for field in ("total_score", "local_rank_score"):
        if field not in scorecard:
            continue
        value = _finite_number(scorecard.get(field))
        if value is None or value < 0 or value > 100:
            reasons.append(_reason(
                "scorecard_" + field + "_out_of_bounds",
                "numeric_out_of_bounds",
                "blocking",
                f"Scorecard {field} is not within 0..100",
                field="scorecard." + field,
                value=scorecard.get(field),
                expected="0..100",
            ))
    if scorecard.get("decision_band") != "submit_candidate":
        reasons.append(_reason(
            "decision_band_not_submit_candidate",
            "quality_gate_failed",
            "blocking",
            "Scorecard decision band is not submit_candidate",
            field="scorecard.decision_band",
            value=scorecard.get("decision_band"),
            expected="submit_candidate",
        ))


def _add_official_evidence_reasons(
    candidate: Candidate,
    run_config: RunConfig | OpsConfig,
    reasons: list[dict[str, Any]],
) -> None:
    ops_config = _ops_from_config(run_config)
    if not str(candidate.official_alpha_id or "").strip():
        reasons.append(_reason(
            "missing_official_alpha_id",
            "official_evidence_missing",
            "blocking",
            "Candidate has no real official Alpha ID",
            field="official_alpha_id",
            expected="official Alpha ID from BRAIN simulation",
        ))
    metrics = candidate.official_metrics if isinstance(candidate.official_metrics, dict) else {}
    if not metrics:
        reasons.append(_reason(
            "missing_official_metrics",
            "official_evidence_missing",
            "blocking",
            "Official simulation metrics are missing",
            field="official_metrics",
            expected="complete official simulation metrics",
        ))
        return
    missing_metric_fields = [
        field for field in _REQUIRED_OFFICIAL_METRICS
        if _metric_value(metrics, field) is None
    ]
    if missing_metric_fields:
        reasons.append(_reason(
            "missing_official_metric_fields",
            "official_evidence_missing",
            "blocking",
            "Official simulation metrics are incomplete",
            field="official_metrics",
            value=", ".join(missing_metric_fields),
            expected=", ".join(_REQUIRED_OFFICIAL_METRICS),
        ))
    thresholds = ops_config.thresholds
    settings = ops_config.settings
    delay = int(getattr(settings, "delay", 1) or 1)
    min_sharpe = thresholds.min_sharpe_delay0 if delay == 0 else thresholds.min_sharpe
    min_fitness = thresholds.min_fitness_delay0 if delay == 0 else thresholds.min_fitness
    _add_metric_bound(reasons, metrics, "sharpe", ">=", min_sharpe, "official_sharpe_below_threshold")
    _add_metric_bound(reasons, metrics, "fitness", ">=", min_fitness, "official_fitness_below_threshold")
    _add_metric_bound(reasons, metrics, "turnover", ">=", thresholds.min_turnover, "official_turnover_below_threshold")
    _add_metric_bound(reasons, metrics, "turnover", "<=", thresholds.platform_max_turnover, "official_turnover_above_threshold")
    _add_metric_bound(reasons, metrics, "returns", ">=", thresholds.min_returns, "official_returns_below_threshold")
    _add_metric_bound(reasons, metrics, "drawdown", "<=", thresholds.max_drawdown, "official_drawdown_above_threshold", ratio=True, absolute=True)
    _add_metric_bound(reasons, metrics, "correlation", "<=", thresholds.max_self_correlation, "official_self_correlation_above_threshold", ratio=True, absolute=True)
    _add_metric_bound(reasons, metrics, "prod_correlation", "<=", thresholds.max_prod_correlation, "official_prod_correlation_above_threshold", ratio=True, absolute=True)
    _add_metric_bound(reasons, metrics, "weight_concentration", "<=", thresholds.max_weight_concentration, "official_weight_concentration_above_threshold", ratio=True)
    if getattr(thresholds, "require_official_pass", True):
        pass_fail = str(metrics.get("pass_fail") or metrics.get("passFail") or "").upper()
        if pass_fail != "PASS":
            reasons.append(_reason(
                "official_pass_fail_not_pass",
                "quality_gate_failed",
                "blocking",
                "Official pass/fail result is not PASS",
                field="official_metrics.pass_fail",
                value=pass_fail or None,
                expected="PASS",
            ))


def _add_gate_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    gate = candidate.gate if isinstance(candidate.gate, dict) else {}
    if gate and gate.get("submission_ready") is False:
        reasons.append(_reason(
            "gate_not_submission_ready",
            "quality_gate_failed",
            "blocking",
            "Production gate does not mark the Alpha as submission_ready",
            field="gate.submission_ready",
            value=False,
            expected=True,
        ))


def _add_metric_bound(
    reasons: list[dict[str, Any]],
    metrics: dict[str, Any],
    field: str,
    direction: str,
    target: float,
    code: str,
    *,
    ratio: bool = False,
    absolute: bool = False,
) -> None:
    value = _metric_value(metrics, field)
    if value is None:
        return
    actual = _ratio(value, bounded=ratio)
    if absolute:
        actual = abs(actual)
    passed = actual >= target if direction == ">=" else actual <= target
    if not passed:
        reasons.append(_reason(
            code,
            "numeric_out_of_bounds",
            "blocking",
            f"Official metric {field} is outside the configured threshold",
            field="official_metrics." + field,
            value=round(actual, 6),
            expected=direction + " " + str(target),
        ))
