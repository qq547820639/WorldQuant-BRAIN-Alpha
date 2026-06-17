"""Small validation helpers used by configuration loading."""

from __future__ import annotations

import math
from typing import Any
from urllib.parse import urlparse


def validate_decision_thresholds(errors: list[str], decision_thresholds: Any) -> None:
    if not isinstance(decision_thresholds, dict):
        errors.append("ops.scoring.decision_thresholds must be an object")
        return
    values = [decision_thresholds.get(key) for key in ("submit", "optimize", "research")]
    for key, value in zip(("submit", "optimize", "research"), values):
        require_float_range(errors, f"ops.scoring.decision_thresholds.{key}", value, min_value=0.0, max_value=100.0)
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        if not (values[0] >= values[1] >= values[2]):
            errors.append("ops.scoring.decision_thresholds must satisfy submit >= optimize >= research")


def validate_http_url(errors: list[str], name: str, value: Any, *, require_https: bool = False) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{name} must be a non-empty URL")
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{name} must be an http(s) URL")
        return
    if require_https and parsed.scheme != "https":
        errors.append(f"{name} must use https in production")


def require_api_path(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.startswith("/"):
        errors.append(f"{name} must start with '/'")


def require_str(errors: list[str], name: str, value: Any, *, allow_empty: bool = True) -> None:
    if not isinstance(value, str):
        errors.append(f"{name} must be a string")
        return
    if not allow_empty and not value.strip():
        errors.append(f"{name} must not be empty")


def require_string_list(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, list):
        errors.append(f"{name} must be a list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{name}[{index}] must be a non-empty string")


def require_bool(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, bool):
        errors.append(f"{name} must be a boolean")


def require_int_range(
    errors: list[str],
    name: str,
    value: Any,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{name} must be an integer")
        return
    if min_value is not None and value < min_value:
        errors.append(f"{name} must be >= {min_value}")
    if max_value is not None and value > max_value:
        errors.append(f"{name} must be <= {max_value}")


def require_float(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        errors.append(f"{name} must be a finite number")


def require_float_range(
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
    if not math.isfinite(numeric):
        errors.append(f"{name} must be finite")
        return
    if min_value is not None and numeric < min_value:
        errors.append(f"{name} must be >= {min_value}")
    if max_value is not None and numeric > max_value:
        errors.append(f"{name} must be <= {max_value}")


def require_enum(errors: list[str], name: str, value: Any, allowed: set[Any]) -> None:
    if isinstance(value, bool):
        errors.append(f"{name} must be one of {sorted(allowed)}")
        return
    if value not in allowed:
        errors.append(f"{name} must be one of {sorted(allowed)}")


def validate_generation_mode_ratio(errors: list[str], value: Any) -> None:
    name = "ops.budget.generation_mode_ratio"
    if not isinstance(value, str):
        errors.append(f"{name} must be a string like '70/20/10'")
        return
    parts = value.split("/")
    if len(parts) != 3:
        errors.append(f"{name} must contain three slash-separated non-negative numbers")
        return
    total = 0.0
    for part in parts:
        try:
            numeric = float(part)
        except (TypeError, ValueError):
            errors.append(f"{name} must contain only numbers")
            return
        if not math.isfinite(numeric) or numeric < 0:
            errors.append(f"{name} values must be finite and >= 0")
            return
        total += numeric
    if total <= 0:
        errors.append(f"{name} must have a positive total")


def validate_weight_group(errors: list[str], group_name: str, weights: dict[str, Any]) -> None:
    total = 0.0
    valid = True
    for field_name, value in weights.items():
        before = len(errors)
        require_float_range(errors, f"{group_name}.{field_name}", value, min_value=0.0)
        if len(errors) != before:
            valid = False
            continue
        total += float(value)
    if valid and total <= 0:
        errors.append(f"{group_name} must have a positive total weight")
    elif valid and abs(total - 1.0) > 1e-6:
        errors.append(f"{group_name} weights should sum to 1.0 (got {total:.4f})")


def validate_regime_adjustments(errors: list[str], value: Any, allowed_regimes: set[Any]) -> None:
    if not isinstance(value, dict):
        errors.append("ops.thresholds.regime_adjustments must be an object")
        return
    for regime, adjustments in value.items():
        if regime not in allowed_regimes:
            errors.append(f"ops.thresholds.regime_adjustments has unsupported regime: {regime}")
            continue
        if not isinstance(adjustments, dict):
            errors.append(f"ops.thresholds.regime_adjustments.{regime} must be an object")
            continue
        for factor_name in ("sharpe_factor", "fitness_factor", "turnover_factor"):
            if factor_name in adjustments:
                require_float_range(
                    errors,
                    f"ops.thresholds.regime_adjustments.{regime}.{factor_name}",
                    adjustments[factor_name],
                    min_value=0.0,
                )
