"""Small validation helpers used by configuration loading."""

from __future__ import annotations

from typing import Any


def validate_decision_thresholds(errors: list[str], decision_thresholds: Any) -> None:
    if not isinstance(decision_thresholds, dict):
        errors.append("ops.scoring.decision_thresholds must be an object")
        return
    values = [decision_thresholds.get(key) for key in ("submit", "optimize", "research")]
    for key, value in zip(("submit", "optimize", "research"), values):
        _require_float_range(errors, f"ops.scoring.decision_thresholds.{key}", value, min_value=0.0, max_value=100.0)
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        if not (values[0] >= values[1] >= values[2]):
            errors.append("ops.scoring.decision_thresholds must satisfy submit >= optimize >= research")


def _require_float_range(
    errors: list[str],
    name: str,
    value: Any,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{name} must be a number")
        return
    numeric = float(value)
    if min_value is not None and numeric < min_value:
        errors.append(f"{name} must be >= {min_value}")
    if max_value is not None and numeric > max_value:
        errors.append(f"{name} must be <= {max_value}")
