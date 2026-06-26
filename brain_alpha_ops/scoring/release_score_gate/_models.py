"""Data models for the release score gate.

Split from the former ``brain_alpha_ops/scoring/release_score_gate.py`` monolith
(deep-optimization-phase13). Holds the frozen dataclasses that capture the
official BRAIN snapshot, the resolved threshold policy, and the gate decision
payload, plus the schema version constant.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.scoring._score_comparisons import is_finite_float, safe_text
from brain_alpha_ops.scoring.release_score_gate._helpers import (
    _metric,
    _metric_with_check_fallback,
    _settings_delay_with_source,
)

RELEASE_SCORE_GATE_SCHEMA = "release_score_gate.v1"


@dataclass(frozen=True)
class OfficialSnapshot:
    sharpe: float | None
    fitness: float | None
    turnover: float | None
    returns: float | None
    drawdown: float | None
    margin: float | None
    self_correlation: float | None
    prod_correlation: float | None
    weight_concentration: float | None
    sub_universe_sharpe: float | None = None
    sub_universe_size: float | None = None
    alpha_size: float | None = None
    pass_fail: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_metrics(cls, metrics: Mapping[str, Any] | None) -> "OfficialSnapshot":
        raw: Mapping[str, Any] = dict(metrics or {})
        return cls(
            sharpe=is_finite_float(raw.get("sharpe")),
            fitness=is_finite_float(raw.get("fitness")),
            turnover=is_finite_float(raw.get("turnover")),
            returns=is_finite_float(raw.get("returns")),
            drawdown=is_finite_float(raw.get("drawdown")),
            margin=is_finite_float(raw.get("margin")),
            self_correlation=is_finite_float(raw.get("self_correlation")),
            prod_correlation=is_finite_float(raw.get("prod_correlation")),
            weight_concentration=is_finite_float(raw.get("weight_concentration")),
            sub_universe_sharpe=_metric_with_check_fallback(
                raw,
                "LOW_SUB_UNIVERSE_SHARPE",
                "sub_universe_sharpe",
                "subUniverseSharpe",
            ),
            sub_universe_size=_metric(raw, "subUniverseSize", "sub_universe_size", "sub_size"),
            alpha_size=_metric(raw, "alphaSize", "alpha_size"),
            pass_fail=safe_text(raw.get("pass_fail")),
            raw=raw,
        )


@dataclass(frozen=True)
class ThresholdPolicy:
    min_sharpe: float
    min_fitness: float
    min_turnover: float
    max_turnover: float
    max_drawdown: float
    max_self_correlation: float
    max_prod_correlation: float
    max_weight_concentration: float
    sub_universe_sharpe_min_ratio: float
    require_official_pass: bool = True
    require_official_metrics: bool = True
    delay: int = 1
    delay_source: str = "default_delay_1"
    min_sharpe_source: str = "min_sharpe"
    min_fitness_source: str = "min_fitness"

    @classmethod
    def from_thresholds(cls, thresholds: QualityThresholds, settings: Mapping[str, Any] | Any | None = None) -> "ThresholdPolicy":
        delay, delay_source = _settings_delay_with_source(settings)
        return cls(
            min_sharpe=float(thresholds.min_sharpe_delay0 if delay == 0 else thresholds.min_sharpe),
            min_fitness=float(thresholds.min_fitness_delay0 if delay == 0 else thresholds.min_fitness),
            min_turnover=float(thresholds.min_turnover),
            max_turnover=float(thresholds.platform_max_turnover),
            max_drawdown=float(thresholds.max_drawdown),
            max_self_correlation=float(thresholds.max_self_correlation),
            max_prod_correlation=float(thresholds.max_prod_correlation),
            max_weight_concentration=float(thresholds.max_weight_concentration),
            sub_universe_sharpe_min_ratio=float(thresholds.sub_universe_sharpe_min_ratio),
            require_official_pass=bool(thresholds.require_official_pass),
            require_official_metrics=bool(thresholds.require_official_metrics),
            delay=delay,
            delay_source=delay_source,
            min_sharpe_source="min_sharpe_delay0" if delay == 0 else "min_sharpe",
            min_fitness_source="min_fitness_delay0" if delay == 0 else "min_fitness",
        )


@dataclass(frozen=True)
class ScoreAttribution:
    name: str
    passed: bool
    actual: float | str | None
    expected: float | str | None
    severity: str
    reason: str


@dataclass(frozen=True)
class GateDecision:
    status: str
    pass_fail: bool
    official_snapshot: dict[str, Any]
    attributions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    threshold_trace: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RELEASE_SCORE_GATE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
