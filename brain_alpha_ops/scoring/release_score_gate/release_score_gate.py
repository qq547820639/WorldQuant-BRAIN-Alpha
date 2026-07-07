"""Release scoring gate that preserves official BRAIN metric values.

Consolidates the former ``_models`` / ``_helpers`` / ``_checks`` / ``_decision``
submodules into a single file. Pure physical merge; no logic changes.

Split from the former ``brain_alpha_ops/scoring/release_score_gate.py`` monolith
(deep-optimization-phase13). Public API and any private symbols referenced by
tests are re-exported via ``__init__`` so existing imports of
``brain_alpha_ops.scoring.release_score_gate`` continue to resolve.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.scoring._score_comparisons import (
    is_finite_float,
    max_check,
    min_check,
    safe_text,
    sub_universe_sharpe_formula,
)


# --------------------------------------------------------------------------- #
# Former _helpers.py
# --------------------------------------------------------------------------- #
def _metric(metrics: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = is_finite_float(metrics.get(key))
        if value is not None:
            return value
    return None


def _metric_with_check_fallback(metrics: Mapping[str, Any], check_name: str, *keys: str) -> float | None:
    value = _metric(metrics, *keys)
    check_value = _brain_check_value(metrics, check_name)
    if check_value is not None and (value is None or (value == 0.0 and check_value != 0.0)):
        return check_value
    return value


def _brain_check_value(metrics: Mapping[str, Any], check_name: str) -> float | None:
    checks = metrics.get("brain_checks")
    if not isinstance(checks, Mapping):
        return None
    check = checks.get(check_name)
    if not isinstance(check, Mapping):
        return None
    return is_finite_float(check.get("value"))


# _num: use is_finite_float from _score_comparisons


# _text: use safe_text from _score_comparisons


def _settings_delay(settings: Mapping[str, Any] | Any | None) -> int:
    delay, _source = _settings_delay_with_source(settings)
    return delay


def _settings_delay_with_source(settings: Mapping[str, Any] | Any | None) -> tuple[int, str]:
    for source, value in _iter_delay_values(settings):
        try:
            delay = int(value)
        except (TypeError, ValueError):
            continue
        return (0 if delay == 0 else 1), source
    return 1, "default_delay_1"


def _iter_delay_values(value: Mapping[str, Any] | Any | None, source: str = "settings"):
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, Mapping):
        for key in ("delay", "data_delay"):
            if key in value:
                yield f"{source}.{key}", value.get(key)
        for key in ("settings", "brain_settings", "simulation_settings"):
            if key in value:
                yield from _iter_delay_values(value.get(key), f"{source}.{key}")
        return
    for attr in ("delay", "data_delay"):
        if hasattr(value, attr):
            yield f"{source}.{attr}", getattr(value, attr)


# --------------------------------------------------------------------------- #
# Former _models.py
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Former _checks.py
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Former _decision.py
# --------------------------------------------------------------------------- #
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
    # F-051: when settings is not supplied, fall back to an empty mapping — NOT
    # to ``metrics``. The previous ``else metrics`` handed the metrics dict
    # (sharpe/returns/fitness ...) to from_thresholds, which then scanned it
    # for "delay"/"data_delay" keys and could misread metric values as the
    # simulation delay, producing wrong sharpe/fitness thresholds. An empty
    # mapping makes _settings_delay_with_source fall through to its safe
    # default (delay=1, "default_delay_1").
    effective_settings = settings if settings is not None else {}
    policy = (
        thresholds
        if isinstance(thresholds, ThresholdPolicy)
        else ThresholdPolicy.from_thresholds(thresholds, settings=effective_settings)
    )
    return decide_release(OfficialSnapshot.from_metrics(metrics), policy)
