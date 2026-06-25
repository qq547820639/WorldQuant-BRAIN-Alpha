"""Utility helpers for Alpha quality diagnostics.

Pure helpers shared across the diagnosis, output-config, and reason-builder
sub-modules. Extracted from the original ``alpha_quality.py`` monolith.
"""

from __future__ import annotations

import math
from typing import Any

from brain_alpha_ops.config_models import OpsConfig, RunConfig
from brain_alpha_ops.research.expression_ast import profile_expression
from brain_alpha_ops.research.validated_generator import WINDOW_CONSTRAINTS


def _ops_from_config(run_config: RunConfig | OpsConfig) -> OpsConfig:
    return run_config.ops if isinstance(run_config, RunConfig) else run_config


def _reason(
    code: str,
    category: str,
    severity: str,
    message: str,
    *,
    field: str = "",
    value: Any = None,
    expected: str = "",
) -> dict[str, Any]:
    payload = {
        "code": code,
        "category": category,
        "severity": severity,
        "message": message,
    }
    if field:
        payload["field"] = field
    if value is not None:
        payload["value"] = _json_safe(value)
    if expected:
        payload["expected"] = expected
    return payload


def _has_only_submission_blockers(blocking: list[dict[str, Any]]) -> bool:
    if not blocking:
        return False
    categories = {row.get("category") for row in blocking}
    return categories <= {"official_evidence_missing"}


def _status_label(status: str) -> str:
    labels = {
        "submission_ready": "submission ready",
        "local_only_needs_official_evidence": "local candidate needs official evidence",
        "blocked": "blocked",
    }
    return labels.get(status, status)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metric_value(metrics: dict[str, Any], field: str) -> float | None:
    aliases = {
        "correlation": ("correlation", "self_correlation", "selfCorrelation"),
        "prod_correlation": ("prod_correlation", "prodCorrelation"),
        "weight_concentration": ("weight_concentration", "weightConcentration"),
    }
    for key in aliases.get(field, (field,)):
        if key in metrics:
            return _finite_number(metrics.get(key))
    return None


def _ratio(value: Any, *, bounded: bool = False) -> float:
    number = _finite_number(value)
    if number is None:
        return 0.0
    abs_number = abs(number)
    if abs_number >= 100.0 or (bounded and abs_number > 1.0):
        return number / 100.0
    return number


def _parentheses_balance_error(expression: str) -> str:
    depth = 0
    for ch in expression:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            return "Expression has an extra closing parenthesis"
    if depth > 0:
        return "Expression has an unclosed opening parenthesis"
    return ""


def _extract_bracketed(text: str, start: int) -> str | None:
    if start >= len(text) or text[start] != "(":
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start + 1:index]
    return None


def _split_args(args_str: str) -> list[str]:
    args: list[str] = []
    depth = 0
    current = ""
    for char in args_str:
        if char == "(":
            depth += 1
            current += char
        elif char == ")":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        args.append(current.strip())
    return args


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _expression_profile(expression: str) -> dict[str, Any]:
    profile = profile_expression(expression or "")
    return {
        "parsed": profile.parsed,
        "operators": list(profile.operators),
        "fields": list(profile.fields),
        "windows": list(profile.windows),
        "max_depth": profile.max_depth,
        "node_count": profile.node_count,
        "parse_error": profile.parse_error,
    }


def _numeric_bounds(run_config: RunConfig | OpsConfig, output_config: dict[str, Any]) -> dict[str, Any]:
    ops_config = _ops_from_config(run_config)
    thresholds = output_config.get("official_thresholds") if isinstance(output_config, dict) else {}
    thresholds = thresholds if isinstance(thresholds, dict) else {}
    return {
        "local_quality_score": "0..100",
        "scorecard_total_score": "0..100",
        "official_thresholds": thresholds,
        "window_constraints": _json_safe(WINDOW_CONSTRAINTS),
        "config_delay": list(sorted({0, 1})),
        "config_truncation": "0..1",
        "config_threshold_source": "config/run_config.json",
        "active_delay": getattr(ops_config.settings, "delay", None),
    }
