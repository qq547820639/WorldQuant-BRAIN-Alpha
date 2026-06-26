"""Scoring helpers for ``AutoCalibrator``.

Extracted from the original ``auto_calibrator.py`` as a mixin so that the
prior-score / MAE computation helpers remain cohesive while keeping the
main calibrator module small.
"""
from __future__ import annotations

import re
from typing import Any

from brain_alpha_ops.research.scoring_params import DimensionParam, ScoringParams


class _ScoringMixin:
    """Provides prior-score and MAE computation helpers."""

    def _compute_prior_for_record(
        self, record: dict[str, Any], dim: DimensionParam, dim_name: str
    ) -> float:
        """Compute a parameterized prior score for one dimension in one record."""
        fields = set(record.get("field_set", []))
        operators = list(record.get("operator_set", []))
        expression = record.get("expression", "")
        hypothesis = record.get("hypothesis", "")
        family = record.get("family", "")

        windows = [int(v) for v in re.findall(r"\b\d+\b", expression)]
        median_window = sorted(windows)[len(windows) // 2] if windows else 0

        if dim_name == "structure":
            return max(dim.floor, dim.base_score - max(0, len(operators) - dim.penalty_threshold) * dim.penalty_per_unit)

        elif dim_name == "field_operator_support":
            score = dim.base_score + len(fields) * dim.bonus_per_unit + len(set(operators)) * 4
            return min(dim.cap, max(dim.floor, score))

        elif dim_name == "data_compliance":
            return dim.high_score if fields else dim.low_score

        elif dim_name == "horizon_turnover_proxy":
            if not median_window:
                return dim.score_no_data
            if dim.threshold_low <= median_window <= dim.threshold_high:
                return dim.score_in_range
            return dim.score_out_range

        elif dim_name == "risk_control_proxy":
            has_cs = any(op in operators for op in ("rank", "zscore", "scale", "group_rank", "group_zscore"))
            has_ts = any(op.startswith("ts_") for op in operators)
            has_rc = any(op in operators for op in ("winsorize", "zscore", "scale", "group_rank")) or "adv20" in fields
            conditions = sum([has_cs, has_ts, has_rc])
            if conditions >= 3:
                return dim.tier_3_score
            elif conditions >= 2:
                return dim.tier_2_score
            return dim.tier_1_score

        elif dim_name == "diversity":
            high_set = set(dim.high_value_set or [])
            return dim.high_score if family in high_set else dim.low_score

        elif dim_name == "explainability":
            return dim.score_in_range if len(expression) < dim.threshold_high else dim.score_out_range

        elif dim_name == "economic_logic":
            text = f"{hypothesis} {expression} {' '.join(fields)} {' '.join(operators)}".lower()
            concepts = {
                "momentum": ["momentum", "trend", "ts_delta", "ts_rank", "ts_mean", "moving_average", "breakout", "continuation"],
                "mean_reversion": ["reversal", "mean_revert", "zscore", "ts_zscore", "overbought", "oversold", "bounce", "revert"],
                "value": ["value", "cheap", "undervalue", "pe_ratio", "pb_ratio", "market_cap", "book", "dividend_yield", "earnings_yield"],
                "quality": ["quality", "profit", "margin", "roe", "roa", "stable", "fundamental", "balance_sheet"],
                "volatility": ["volatility", "vol", "ts_std", "std", "ivol", "beta", "risk", "variance", "uncertainty"],
                "liquidity": ["liquidity", "volume", "turn", "adv", "vwap", "bid", "spread", "depth", "market_impact"],
                "growth": ["growth", "earnings", "revenue", "sales_growth", "expansion", "accelerat"],
                "risk_management": ["winsorize", "truncation", "neutralize", "group_neutralize", "hedge", "sector_neutral", "risk_adjust"],
                "cross_sectional": ["cross_section", "rank", "group_rank", "sector", "industry", "subindustry", "relative", "peer"],
            }
            detected = sum(1 for kw_list in concepts.values() if any(kw in text for kw in kw_list))
            if detected == 0:
                if len(hypothesis) >= dim.fallback_length_threshold:
                    return dim.fallback_length_score
                return dim.fallback_insufficient_score
            if dim.concept_scores:
                return dim.concept_scores.get(detected, dim.concept_scores.get(max(dim.concept_scores.keys(), default=68), 68))
            return 68 if detected == 1 else (78 if detected == 2 else (85 if detected == 3 else 92))

        return 50.0  # Default score for unknown dimensions.

    def _compute_full_prior(self, params: ScoringParams, record: dict[str, Any]) -> float:
        """Compute the full prior_score as a weighted 8-dimension score."""
        total = 0.0
        total_weight = 0.0
        for dim_name, dim in params.dimensions.items():
            if not dim.enabled:
                continue
            dim_score = self._compute_prior_for_record(record, dim, dim_name)
            total += dim_score * dim.weight
            total_weight += dim.weight
        return total / max(total_weight, 0.01)

    def _compute_mae(
        self, dim_name: str, dim: DimensionParam,
        records: list[dict[str, Any]]
    ) -> float:
        """Compute MAE between one dimension's prior score and empirical score."""
        errors = []
        for record in records:
            prior = self._compute_prior_for_record(record, dim, dim_name)
            empirical = record.get("sharpe", 0) * 50
            empirical = min(100, max(0, empirical))
            errors.append(abs(prior - empirical))
        return sum(errors) / max(len(errors), 1)

    def _compute_overall_mae(
        self, params: ScoringParams, records: list[dict[str, Any]]
    ) -> float:
        """Compute MAE between full prior_score and empirical score."""
        errors = []
        for record in records:
            prior = self._compute_full_prior(params, record)
            empirical = min(100, max(0, record.get("sharpe", 0) * 50))
            errors.append(abs(prior - empirical))
        return sum(errors) / max(len(errors), 1)
