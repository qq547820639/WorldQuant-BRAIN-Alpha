"""Metric extraction and settings delay helpers for the release score gate.

Split from the former ``brain_alpha_ops/scoring/release_score_gate.py`` monolith
(deep-optimization-phase13). Pure helper functions for reading numeric metrics
from BRAIN API payloads and resolving the effective simulation delay.
"""
from __future__ import annotations

from typing import Any, Mapping

from brain_alpha_ops.scoring._score_comparisons import is_finite_float


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
