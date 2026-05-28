"""Release scoring gate that preserves official BRAIN metric values."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from brain_alpha_ops.config import QualityThresholds


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
    pass_fail: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_metrics(cls, metrics: Mapping[str, Any] | None) -> "OfficialSnapshot":
        raw: Mapping[str, Any] = dict(metrics or {})
        return cls(
            sharpe=_num_or_zero(raw.get("sharpe")),
            fitness=_num_or_zero(raw.get("fitness")),
            turnover=_num_or_zero(raw.get("turnover")),
            returns=_num_or_zero(raw.get("returns")),
            drawdown=_num_or_zero(raw.get("drawdown")),
            margin=_num_or_zero(raw.get("margin")),
            self_correlation=_num_or_zero(raw.get("self_correlation", raw.get("correlation"))),
            prod_correlation=_num_or_zero(raw.get("prod_correlation", raw.get("correlation"))),
            weight_concentration=_num_or_zero(raw.get("weight_concentration")),
            sub_universe_sharpe=_num_or_zero(raw.get("sub_universe_sharpe")),
            pass_fail=_text(raw.get("pass_fail")),
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

    @classmethod
    def from_thresholds(cls, thresholds: QualityThresholds) -> "ThresholdPolicy":
        return cls(
            min_sharpe=float(thresholds.min_sharpe),
            min_fitness=float(thresholds.min_fitness),
            min_turnover=float(thresholds.min_turnover),
            max_turnover=float(thresholds.platform_max_turnover),
            max_drawdown=float(thresholds.max_drawdown),
            max_self_correlation=float(thresholds.max_self_correlation),
            max_prod_correlation=float(thresholds.max_prod_correlation),
            max_weight_concentration=float(thresholds.max_weight_concentration),
            sub_universe_sharpe_min_ratio=float(thresholds.sub_universe_sharpe_min_ratio),
            require_official_pass=bool(thresholds.require_official_pass),
            require_official_metrics=bool(thresholds.require_official_metrics),
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
    attributions: list[dict[str, Any]]
    schema_version: str = RELEASE_SCORE_GATE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_release(official: OfficialSnapshot, policy: ThresholdPolicy) -> GateDecision:
    """Return a release decision by comparing official values only."""
    attrs = [
        _official_pass_attr(official, policy),
        _cmp_min("sharpe", official.sharpe, policy.min_sharpe, "ERROR", "official Sharpe below release threshold"),
        _cmp_min("fitness", official.fitness, policy.min_fitness, "ERROR", "official Fitness below release threshold"),
        _cmp_min("turnover_floor", official.turnover, policy.min_turnover, "WARN", "official Turnover below platform floor"),
        _cmp_max("turnover_cap", official.turnover, policy.max_turnover, "ERROR", "official Turnover above platform cap"),
        _cmp_max("drawdown_cap", official.drawdown, policy.max_drawdown, "WARN", "official Drawdown above quality target"),
        _cmp_max(
            "self_correlation_cap",
            official.self_correlation,
            policy.max_self_correlation,
            "ERROR",
            "official self-correlation above release cap",
        ),
        _cmp_max(
            "prod_correlation_cap",
            official.prod_correlation,
            policy.max_prod_correlation,
            "ERROR",
            "official prod-correlation above release cap",
        ),
        _cmp_max(
            "weight_concentration_cap",
            official.weight_concentration,
            policy.max_weight_concentration,
            "ERROR",
            "official weight concentration above release cap",
        ),
    ]
    hard_fail = any((not item.passed) and item.severity == "ERROR" for item in attrs)
    warn_only = (not hard_fail) and any(not item.passed for item in attrs)
    return GateDecision(
        status="FAIL" if hard_fail else ("WARN" if warn_only else "PASS"),
        pass_fail=not hard_fail,
        official_snapshot=asdict(official),
        attributions=[asdict(item) for item in attrs],
    )


def evaluate_release_score(
    metrics: Mapping[str, Any] | None,
    thresholds: QualityThresholds | ThresholdPolicy,
) -> GateDecision:
    policy = thresholds if isinstance(thresholds, ThresholdPolicy) else ThresholdPolicy.from_thresholds(thresholds)
    return decide_release(OfficialSnapshot.from_metrics(metrics), policy)


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


def _cmp_min(
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
) -> ScoreAttribution:
    passed = actual is not None and actual >= expected
    return ScoreAttribution(name, passed, actual, expected, severity, reason)


def _cmp_max(
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
) -> ScoreAttribution:
    passed = actual is not None and actual <= expected
    return ScoreAttribution(name, passed, actual, expected, severity, reason)


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_or_zero(value: Any) -> float:
    parsed = _num(value)
    return 0.0 if parsed is None else parsed


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
