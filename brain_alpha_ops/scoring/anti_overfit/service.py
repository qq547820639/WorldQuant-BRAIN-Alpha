from __future__ import annotations

import logging
from typing import Any

from .models import (
    ANTI_OVERFIT_SCHEMA_VERSION,
    _MIN_CANDIDATE_SERIES,
)
from .checks import (
    _attach_submission_report,
    _candidate_metrics,
    _candidate_report,
    _candidate_value,
    _number_series,
)
from .suite import run_anti_overfit_suite

logger = logging.getLogger(__name__)


class AntiOverfitService:
    """Canonical candidate-level anti-overfit report service.

    The production submission gate consumes this report.  Missing or short
    official robustness series fail closed so a candidate cannot become
    submission-ready merely because evidence is absent.
    """

    def evaluate(self, candidate: dict[str, Any] | Any) -> dict[str, Any]:
        metrics = _candidate_metrics(candidate)
        factor_values = _number_series(
            metrics.get("factor_values")
            or metrics.get("factor_values_series")
            or metrics.get("ic_series")
            or metrics.get("rank_ic_series")
            or _candidate_value(candidate, "ic_series")
            or _candidate_value(candidate, "rank_ic_series")
        )
        # F-001/F-002: fallback chain must keep returns/IC semantics strict.
        # returns/forward_returns never fall back to ic_series/rank_ic_series
        # (IC is a factor-quality metric, not a return). Missing returns →
        # sample_size collapses → insufficient_data (fail-closed), never pass.
        returns = _number_series(
            metrics.get("returns")
            or metrics.get("returns_series")
            or metrics.get("forward_returns")
            or metrics.get("forward_returns_series")
            or _candidate_value(candidate, "returns")
            or _candidate_value(candidate, "returns_series")
        )
        forward_returns = _number_series(
            metrics.get("forward_returns")
            or metrics.get("forward_returns_series")
            or _candidate_value(candidate, "forward_returns")
            or returns
        )

        sample_size = min(len(factor_values), len(returns), len(forward_returns))
        if sample_size < _MIN_CANDIDATE_SERIES:
            report = _candidate_report(
                ok=False,
                passed=False,
                recommendation="insufficient_data",
                score=0.0,
                sample_size=sample_size,
                data_source="official_metrics",
                reason=(
                    "anti-overfit requires at least "
                    f"{_MIN_CANDIDATE_SERIES} official robustness samples"
                ),
            )
            _attach_submission_report(candidate, "anti_overfit_report", report)
            return report

        try:
            result = run_anti_overfit_suite(
                factor_values[:sample_size],
                returns[:sample_size],
                forward_returns=forward_returns[:sample_size],
            )
        except (TypeError, ValueError, OverflowError) as exc:
            report = _candidate_report(
                ok=False,
                passed=False,
                recommendation="block",
                score=0.0,
                sample_size=sample_size,
                data_source="official_metrics",
                reason=f"anti-overfit suite failed: {exc.__class__.__name__}",
            )
            _attach_submission_report(candidate, "anti_overfit_report", report)
            return report

        payload = result.to_dict()
        passed = bool(result.passed)
        recommendation = (
            "pass"
            if passed
            else ("caution" if result.overall_score >= 50.0 else "block")
        )
        report = {
            "ok": True,
            "schema_version": ANTI_OVERFIT_SCHEMA_VERSION,
            "passed": passed,
            "score": round(float(result.overall_score), 4),
            "recommendation": recommendation,
            "sample_size": sample_size,
            "data_source": "official_metrics",
            "suite": payload,
            "warnings": list(result.warnings),
        }
        if not passed:
            report["reason"] = "statistical_robustness_below_threshold"
        _attach_submission_report(candidate, "anti_overfit_report", report)
        return report


def evaluate_candidate(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    return AntiOverfitService().evaluate(candidate)
