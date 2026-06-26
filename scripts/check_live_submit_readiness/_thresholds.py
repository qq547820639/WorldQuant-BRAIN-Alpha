"""Threshold loading and summary helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.config import ConfigValidationError, QualityThresholds, load_run_config


def _load_thresholds(config_path: str | Path) -> tuple[QualityThresholds, dict[str, str] | None]:
    try:
        return load_run_config(config_path).ops.thresholds, None
    except ConfigValidationError as exc:
        return QualityThresholds(), {
            "code": "readiness_config_error",
            "message": f"could not load official threshold config: {exc}",
        }


def _threshold_summary(thresholds: QualityThresholds) -> dict[str, Any]:
    return {
        "min_sharpe": thresholds.min_sharpe,
        "min_fitness": thresholds.min_fitness,
        "platform_max_turnover": thresholds.platform_max_turnover,
        "max_self_correlation": thresholds.max_self_correlation,
        "max_prod_correlation": thresholds.max_prod_correlation,
        "max_weight_concentration": thresholds.max_weight_concentration,
        "require_official_pass": thresholds.require_official_pass,
        "require_official_metrics": thresholds.require_official_metrics,
    }


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
