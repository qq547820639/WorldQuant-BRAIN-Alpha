"""Reason builders for missing-field, config, and expression format checks.

Extracted from the original ``alpha_quality.py`` monolith. These builders
populate the ``reasons`` list with diagnostic rows used by
``diagnose_alpha_candidate``.
"""

from __future__ import annotations

import re
from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import profile_expression
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)
from brain_alpha_ops.research.validated_generator import (
    OPERATOR_SIGNATURES,
    WINDOW_CONSTRAINTS,
    get_active_safe_fields,
)

from .constants import _REQUIRED_ALPHA_FIELDS, _REQUIRED_SETTINGS_FIELDS, _RESERVED_WORDS
from .utils import (
    _extract_bracketed,
    _is_missing,
    _parentheses_balance_error,
    _reason,
    _split_args,
)


def _add_missing_candidate_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    for field in _REQUIRED_ALPHA_FIELDS:
        value = getattr(candidate, field, None)
        if _is_missing(value):
            reasons.append(_reason(
                "missing_" + field,
                "missing",
                "blocking",
                f"Candidate is missing required field: {field}",
                field=field,
                expected="non-empty value",
            ))


def _add_missing_config_reasons(output_config: dict[str, Any], reasons: list[dict[str, Any]]) -> None:
    settings = output_config.get("settings") if isinstance(output_config, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    for field in _REQUIRED_SETTINGS_FIELDS:
        if _is_missing(settings.get(field)):
            reasons.append(_reason(
                "missing_config_" + field,
                "missing",
                "blocking",
                f"Alpha output configuration is missing {field}",
                field="settings." + field,
                expected="configured value",
            ))


def _add_expression_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    expression = str(candidate.expression or "")
    if not expression.strip():
        return
    balance_error = _parentheses_balance_error(expression)
    if balance_error:
        reasons.append(_reason(
            "expression_parentheses_unbalanced",
            "format_error",
            "blocking",
            balance_error,
            field="expression",
            value=expression,
            expected="balanced parentheses",
        ))
    profile = profile_expression(expression)
    safe_fields = {str(item).lower() for item in get_active_safe_fields()}
    candidate_fields = {str(item).lower() for item in (candidate.data_fields or [])}
    known_fields = safe_fields | candidate_fields
    tokens = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", expression))
    function_tokens = {match.group(1) for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression)}
    operators = set(OPERATOR_SIGNATURES)
    keyword_args = {match.group(1) for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=", expression)}
    field_like = tokens - function_tokens - operators - _RESERVED_WORDS - keyword_args
    unknown_fields = sorted(
        item for item in field_like
        if item.lower() not in known_fields and not item.isdigit()
    )
    if unknown_fields:
        reasons.append(_reason(
            "expression_unknown_fields",
            "format_error",
            "blocking",
            "Expression references fields that are not in the active safe-field set",
            field="expression",
            value=", ".join(unknown_fields[:8]),
            expected="official or candidate data field",
        ))
    for op in sorted(function_tokens):
        if op not in OPERATOR_SIGNATURES:
            reasons.append(_reason(
                "expression_unknown_operator_signature",
                "format_error",
                "warning",
                "Operator is not covered by local signature metadata",
                field="expression",
                value=op,
            expected="known BRAIN operator signature or manual official validation",
        ))
    _add_operator_signature_reasons(expression, reasons)
    _add_generation_risk_reasons(expression, reasons)
    if not profile.parsed and not balance_error:
        reasons.append(_reason(
            "expression_local_parse_warning",
            "format_error",
            "warning",
            "Local parser could not fully parse the expression",
            field="expression",
            value=profile.parse_error,
            expected="manual review or official expression validation",
        ))


def _add_generation_risk_reasons(expression: str, reasons: list[dict[str, Any]]) -> None:
    for risk in high_turnover_generation_risk_reasons(expression):
        match = re.match(r"direct_returns_delta_window=(\d+)$", str(risk))
        window = match.group(1) if match else ""
        reasons.append(_reason(
            "expression_high_turnover_generation_risk",
            "numeric_out_of_bounds",
            "blocking",
            "Expression shape is known to produce high turnover before official simulation",
            field="expression",
            value=("direct returns ts_delta window " + window).strip(),
            expected="use a smoother field or a lower-turnover transform before official backtest",
        ))


def _add_operator_signature_reasons(expression: str, reasons: list[dict[str, Any]]) -> None:
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression):
        op = match.group(1)
        signature = OPERATOR_SIGNATURES.get(op)
        if not signature:
            continue
        args_str = _extract_bracketed(expression, match.end() - 1)
        if args_str is None:
            reasons.append(_reason(
                "expression_operator_unmatched_parentheses",
                "format_error",
                "blocking",
                f"{op}() has unmatched parentheses",
                field="expression",
                value=op,
                expected="closed function call",
            ))
            continue
        args = _split_args(args_str)
        expected_count = len(signature.get("params") or [])
        if len(args) != expected_count:
            reasons.append(_reason(
                "expression_operator_arity_mismatch",
                "format_error",
                "blocking",
                f"{op}() expects {expected_count} args, got {len(args)}",
                field="expression",
                value=op,
                expected=str(expected_count) + " arguments",
            ))
            continue
        for index, param_type in enumerate(signature.get("params") or []):
            if param_type != "d":
                continue
            arg = args[index].strip()
            if not re.fullmatch(r"\d+", arg):
                reasons.append(_reason(
                    "expression_window_not_integer",
                    "format_error",
                    "blocking",
                    f"{op}() window parameter must be an integer",
                    field="expression",
                    value=arg,
                    expected="integer window",
                ))
                continue
            window = int(arg)
            constraints = WINDOW_CONSTRAINTS.get(op, {})
            minimum = int(constraints.get("min", 1))
            maximum = int(constraints.get("max", 252))
            if window < minimum or window > maximum:
                reasons.append(_reason(
                    "expression_window_out_of_bounds",
                    "numeric_out_of_bounds",
                    "blocking",
                    f"{op}() window is outside configured bounds",
                    field="expression",
                    value=window,
                    expected=f"{minimum}..{maximum}",
                ))
