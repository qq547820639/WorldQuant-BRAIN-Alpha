"""Structured Alpha output configuration and quality diagnostics."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import math
import re
from typing import Any

from brain_alpha_ops.config_models import OpsConfig, RunConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.fallback_generation import high_turnover_generation_risk_reasons
from brain_alpha_ops.research.expression_ast import profile_expression
from brain_alpha_ops.research.validated_generator import (
    OPERATOR_SIGNATURES,
    WINDOW_CONSTRAINTS,
    get_active_safe_fields,
)


_REQUIRED_ALPHA_FIELDS = (
    "alpha_id",
    "expression",
    "family",
    "hypothesis",
    "data_fields",
    "operators",
)
_REQUIRED_SETTINGS_FIELDS = (
    "instrumentType",
    "region",
    "universe",
    "dataset",
    "delay",
    "decay",
    "neutralization",
    "truncation",
    "pasteurization",
    "unitHandling",
    "nanHandling",
    "language",
    "type",
)
_REQUIRED_OFFICIAL_METRICS = (
    "sharpe",
    "fitness",
    "turnover",
    "returns",
    "drawdown",
    "correlation",
)
_RESERVED_WORDS = {
    "if",
    "else",
    "and",
    "or",
    "not",
    "true",
    "false",
    "none",
}


def build_alpha_output_config(
    run_config: RunConfig | OpsConfig,
    *,
    dataset_id: str = "",
    generation_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the complete Alpha output parameter plan used by Web generation."""

    ops_config = _ops_from_config(run_config)
    settings = asdict(ops_config.settings)
    if dataset_id:
        settings["dataset"] = dataset_id
    thresholds = asdict(ops_config.thresholds)
    budget = asdict(ops_config.budget)
    scoring = asdict(ops_config.scoring)
    submission_policy = asdict(ops_config.submission_policy)
    generation_args = dict(generation_args or {})
    return {
        "schema_version": "alpha-output-config-v1",
        "local_only": bool(generation_args.get("local_only", True)),
        "official_api_called": bool(generation_args.get("official_api_called", False)),
        "allow_submit": bool(generation_args.get("allow_submit", False)),
        "alpha_type": settings.get("type", "REGULAR"),
        "dataset_id": settings.get("dataset", ""),
        "settings": _json_safe(settings),
        "platform_payload": _json_safe(ops_config.settings.to_platform_dict()),
        "generation": {
            "requested_count": generation_args.get("count", budget.get("max_candidates_per_cycle")),
            "top_n": generation_args.get("top_n", budget.get("retained_alpha_pool_size")),
            "use_research_memory": bool(generation_args.get("use_research_memory")),
            "min_success_rate": generation_args.get("min_success_rate"),
            "assistant_min_confidence": generation_args.get("assistant_min_confidence"),
            "official_validations_per_cycle": budget.get("max_official_validations_per_cycle"),
            "official_simulations_per_cycle": budget.get("max_official_simulations_per_cycle"),
            "official_concurrent_simulations": budget.get("max_official_concurrent_simulations"),
            "official_backtest_batch_size": budget.get("official_backtest_batch_size"),
            "mode": generation_args.get("mode", "local_candidate_generator"),
        },
        "local_gate": {
            "min_local_quality_score": budget.get("min_local_quality_score"),
            "min_local_quality_score_points": float(budget.get("min_local_quality_score", 0.0) or 0.0) * 10,
            "min_prior_score_for_official_validation": budget.get("min_prior_score_for_official_validation"),
            "min_prior_score_for_official_simulation": budget.get("min_prior_score_for_official_simulation"),
        },
        "official_thresholds": {
            "min_sharpe": thresholds.get("min_sharpe"),
            "min_sharpe_delay0": thresholds.get("min_sharpe_delay0"),
            "min_fitness": thresholds.get("min_fitness"),
            "min_fitness_delay0": thresholds.get("min_fitness_delay0"),
            "min_turnover": thresholds.get("min_turnover"),
            "platform_max_turnover": thresholds.get("platform_max_turnover"),
            "target_max_turnover": thresholds.get("target_max_turnover"),
            "max_self_correlation": thresholds.get("max_self_correlation"),
            "max_prod_correlation": thresholds.get("max_prod_correlation"),
            "max_weight_concentration": thresholds.get("max_weight_concentration"),
            "max_drawdown": thresholds.get("max_drawdown"),
            "min_returns": thresholds.get("min_returns"),
            "min_margin_bps": thresholds.get("min_margin_bps"),
            "require_official_pass": thresholds.get("require_official_pass"),
            "require_official_metrics": thresholds.get("require_official_metrics"),
        },
        "submission_policy": {
            "max_expression_similarity": submission_policy.get("max_expression_similarity"),
            "block_micro_variants": submission_policy.get("block_micro_variants"),
            "require_pre_submit_check_passed": submission_policy.get("require_pre_submit_check_passed"),
            "auto_submit": False,
        },
        "qualified_alpha_definition": {
            "local": [
                "required candidate fields are present",
                "FASTEXPR has balanced parentheses and valid known operator arity",
                "window and score values stay within configured bounds",
                "local quality score reaches the configured threshold",
            ],
            "submission": [
                "real official_alpha_id is present",
                "official simulation metrics are complete",
                "official pass_fail is PASS when required",
                "official metrics meet configured BRAIN thresholds",
                "decision_band is submit_candidate and gate.submission_ready is true",
                "pre-submit check and cloud similarity review remain current before real submit",
            ],
        },
    }


def diagnose_alpha_candidate(
    candidate: Candidate,
    *,
    run_config: RunConfig | OpsConfig,
    output_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify why a generated Alpha is or is not qualified."""

    ops_config = _ops_from_config(run_config)
    reasons: list[dict[str, Any]] = []
    output_config = output_config or build_alpha_output_config(
        ops_config,
        dataset_id=candidate.dataset_id or ops_config.settings.dataset,
    )
    _add_missing_candidate_reasons(candidate, reasons)
    _add_missing_config_reasons(output_config, reasons)
    _add_expression_reasons(candidate, reasons)
    _add_local_quality_reasons(candidate, reasons)
    _add_scorecard_reasons(candidate, reasons)
    _add_official_evidence_reasons(candidate, ops_config, reasons)
    _add_gate_reasons(candidate, reasons)

    blocking = [row for row in reasons if row.get("severity") == "blocking"]
    local_blocking_categories = {
        "missing",
        "format_error",
        "numeric_out_of_bounds",
        "local_quality_failed",
    }
    local_blocking = [
        row for row in blocking
        if row.get("category") in local_blocking_categories
    ]
    submission_ready = not blocking
    local_candidate_valid = not local_blocking
    categories = Counter(str(row.get("category") or "other") for row in reasons)
    status = "submission_ready" if submission_ready else (
        "local_only_needs_official_evidence"
        if local_candidate_valid and _has_only_submission_blockers(blocking)
        else "blocked"
    )
    return {
        "schema_version": "alpha-quality-diagnosis-v1",
        "qualified": submission_ready,
        "submission_ready": submission_ready,
        "local_candidate_valid": local_candidate_valid,
        "status": status,
        "status_label": _status_label(status),
        "primary_reason": blocking[0] if blocking else None,
        "blocking_reasons": [str(row.get("code")) for row in blocking],
        "warning_reasons": [str(row.get("code")) for row in reasons if row.get("severity") != "blocking"],
        "reason_counts": dict(Counter(str(row.get("code")) for row in reasons)),
        "category_counts": dict(categories),
        "reasons": reasons,
        "missing_fields": [
            str(row.get("field")) for row in reasons
            if row.get("category") == "missing" and row.get("field")
        ],
        "format_checks": _expression_profile(candidate.expression),
        "numeric_bounds": _numeric_bounds(run_config, output_config),
    }


def summarize_quality_diagnostics(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize generated-candidate quality diagnosis for the Web preview."""

    reason_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    qualified_count = 0
    local_valid_count = 0
    invalid_count = 0
    for row in candidates:
        diagnosis = row.get("quality_diagnosis") if isinstance(row, dict) else {}
        if not isinstance(diagnosis, dict):
            continue
        if diagnosis.get("qualified"):
            qualified_count += 1
        else:
            invalid_count += 1
        if diagnosis.get("local_candidate_valid"):
            local_valid_count += 1
        status_counts[str(diagnosis.get("status") or "unknown")] += 1
        for code, count in (diagnosis.get("reason_counts") or {}).items():
            reason_counts[str(code)] += int(count or 0)
        for category, count in (diagnosis.get("category_counts") or {}).items():
            category_counts[str(category)] += int(count or 0)
    return {
        "schema_version": "alpha-quality-summary-v1",
        "candidate_count": len(candidates),
        "qualified_count": qualified_count,
        "invalid_count": invalid_count,
        "local_valid_count": local_valid_count,
        "local_only_count": status_counts.get("local_only_needs_official_evidence", 0),
        "status_counts": dict(status_counts),
        "reason_counts": dict(reason_counts),
        "category_counts": dict(category_counts),
    }


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


def _add_local_quality_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    local_quality = candidate.local_quality if isinstance(candidate.local_quality, dict) else {}
    if not local_quality:
        reasons.append(_reason(
            "missing_local_quality",
            "missing",
            "blocking",
            "Local quality result is missing",
            field="local_quality",
            expected="local quality score and pass flag",
        ))
        return
    score = _finite_number(local_quality.get("score"))
    threshold = _finite_number(local_quality.get("threshold"))
    if score is None or score < 0 or score > 100:
        reasons.append(_reason(
            "local_quality_score_out_of_bounds",
            "numeric_out_of_bounds",
            "blocking",
            "Local quality score is not within 0..100",
            field="local_quality.score",
            value=local_quality.get("score"),
            expected="0..100",
        ))
    if threshold is None or threshold < 0 or threshold > 100:
        reasons.append(_reason(
            "local_quality_threshold_out_of_bounds",
            "numeric_out_of_bounds",
            "blocking",
            "Local quality threshold is not within 0..100",
            field="local_quality.threshold",
            value=local_quality.get("threshold"),
            expected="0..100",
        ))
    if local_quality.get("passed") is False:
        reasons.append(_reason(
            "local_quality_failed",
            "local_quality_failed",
            "blocking",
            "Local quality prefilter did not pass",
            field="local_quality.passed",
            value=False,
            expected=True,
        ))
    local_backtest = local_quality.get("local_backtest")
    if isinstance(local_backtest, dict) and local_backtest.get("pass_local") is False:
        failed_reasons = [
            str(reason)
            for reason in local_backtest.get("reasons", [])
            if str(reason)
        ]
        if local_backtest.get("advisory") is True:
            reason = _reason(
                "local_backtest_advisory_failed",
                "local_quality_advisory",
                "warning",
                "Exploratory local backtest did not meet synthetic thresholds",
                field="local_quality.local_backtest.pass_local",
                value=False,
                expected="official BRAIN simulation remains the source of truth",
            )
            if failed_reasons:
                reason["details"] = failed_reasons[:5]
            reasons.append(reason)
            return
        reason = _reason(
            "local_backtest_failed",
            "local_quality_failed",
            "blocking",
            "Local backtest did not meet submission thresholds",
            field="local_quality.local_backtest.pass_local",
            value=False,
            expected=True,
        )
        if failed_reasons:
            reason["details"] = failed_reasons[:5]
        reasons.append(reason)


def _add_scorecard_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    scorecard = candidate.scorecard if isinstance(candidate.scorecard, dict) else {}
    if not scorecard:
        reasons.append(_reason(
            "missing_scorecard",
            "missing",
            "blocking",
            "Scorecard is missing",
            field="scorecard",
            expected="scorecard with decision_band",
        ))
        return
    for field in ("total_score", "local_rank_score"):
        if field not in scorecard:
            continue
        value = _finite_number(scorecard.get(field))
        if value is None or value < 0 or value > 100:
            reasons.append(_reason(
                "scorecard_" + field + "_out_of_bounds",
                "numeric_out_of_bounds",
                "blocking",
                f"Scorecard {field} is not within 0..100",
                field="scorecard." + field,
                value=scorecard.get(field),
                expected="0..100",
            ))
    if scorecard.get("decision_band") != "submit_candidate":
        reasons.append(_reason(
            "decision_band_not_submit_candidate",
            "quality_gate_failed",
            "blocking",
            "Scorecard decision band is not submit_candidate",
            field="scorecard.decision_band",
            value=scorecard.get("decision_band"),
            expected="submit_candidate",
        ))


def _add_official_evidence_reasons(
    candidate: Candidate,
    run_config: RunConfig | OpsConfig,
    reasons: list[dict[str, Any]],
) -> None:
    ops_config = _ops_from_config(run_config)
    if not str(candidate.official_alpha_id or "").strip():
        reasons.append(_reason(
            "missing_official_alpha_id",
            "official_evidence_missing",
            "blocking",
            "Candidate has no real official Alpha ID",
            field="official_alpha_id",
            expected="official Alpha ID from BRAIN simulation",
        ))
    metrics = candidate.official_metrics if isinstance(candidate.official_metrics, dict) else {}
    if not metrics:
        reasons.append(_reason(
            "missing_official_metrics",
            "official_evidence_missing",
            "blocking",
            "Official simulation metrics are missing",
            field="official_metrics",
            expected="complete official simulation metrics",
        ))
        return
    missing_metric_fields = [
        field for field in _REQUIRED_OFFICIAL_METRICS
        if _metric_value(metrics, field) is None
    ]
    if missing_metric_fields:
        reasons.append(_reason(
            "missing_official_metric_fields",
            "official_evidence_missing",
            "blocking",
            "Official simulation metrics are incomplete",
            field="official_metrics",
            value=", ".join(missing_metric_fields),
            expected=", ".join(_REQUIRED_OFFICIAL_METRICS),
        ))
    thresholds = ops_config.thresholds
    settings = ops_config.settings
    delay = int(getattr(settings, "delay", 1) or 1)
    min_sharpe = thresholds.min_sharpe_delay0 if delay == 0 else thresholds.min_sharpe
    min_fitness = thresholds.min_fitness_delay0 if delay == 0 else thresholds.min_fitness
    _add_metric_bound(reasons, metrics, "sharpe", ">=", min_sharpe, "official_sharpe_below_threshold")
    _add_metric_bound(reasons, metrics, "fitness", ">=", min_fitness, "official_fitness_below_threshold")
    _add_metric_bound(reasons, metrics, "turnover", ">=", thresholds.min_turnover, "official_turnover_below_threshold")
    _add_metric_bound(reasons, metrics, "turnover", "<=", thresholds.platform_max_turnover, "official_turnover_above_threshold")
    _add_metric_bound(reasons, metrics, "returns", ">=", thresholds.min_returns, "official_returns_below_threshold")
    _add_metric_bound(reasons, metrics, "drawdown", "<=", thresholds.max_drawdown, "official_drawdown_above_threshold", ratio=True, absolute=True)
    _add_metric_bound(reasons, metrics, "correlation", "<=", thresholds.max_self_correlation, "official_self_correlation_above_threshold", ratio=True, absolute=True)
    _add_metric_bound(reasons, metrics, "prod_correlation", "<=", thresholds.max_prod_correlation, "official_prod_correlation_above_threshold", ratio=True, absolute=True)
    _add_metric_bound(reasons, metrics, "weight_concentration", "<=", thresholds.max_weight_concentration, "official_weight_concentration_above_threshold", ratio=True)
    if getattr(thresholds, "require_official_pass", True):
        pass_fail = str(metrics.get("pass_fail") or metrics.get("passFail") or "").upper()
        if pass_fail != "PASS":
            reasons.append(_reason(
                "official_pass_fail_not_pass",
                "quality_gate_failed",
                "blocking",
                "Official pass/fail result is not PASS",
                field="official_metrics.pass_fail",
                value=pass_fail or None,
                expected="PASS",
            ))


def _add_gate_reasons(candidate: Candidate, reasons: list[dict[str, Any]]) -> None:
    gate = candidate.gate if isinstance(candidate.gate, dict) else {}
    if gate and gate.get("submission_ready") is False:
        reasons.append(_reason(
            "gate_not_submission_ready",
            "quality_gate_failed",
            "blocking",
            "Production gate does not mark the Alpha as submission_ready",
            field="gate.submission_ready",
            value=False,
            expected=True,
        ))


def _add_metric_bound(
    reasons: list[dict[str, Any]],
    metrics: dict[str, Any],
    field: str,
    direction: str,
    target: float,
    code: str,
    *,
    ratio: bool = False,
    absolute: bool = False,
) -> None:
    value = _metric_value(metrics, field)
    if value is None:
        return
    actual = _ratio(value, bounded=ratio)
    if absolute:
        actual = abs(actual)
    passed = actual >= target if direction == ">=" else actual <= target
    if not passed:
        reasons.append(_reason(
            code,
            "numeric_out_of_bounds",
            "blocking",
            f"Official metric {field} is outside the configured threshold",
            field="official_metrics." + field,
            value=round(actual, 6),
            expected=direction + " " + str(target),
        ))


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
