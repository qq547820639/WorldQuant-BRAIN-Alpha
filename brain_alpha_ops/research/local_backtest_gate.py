"""Shared local backtest gate helpers for candidate prefilters."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.research.expression_ast import profile_expression


def append_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def blocked_local_gate(reasons: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "production-gate-v2.1",
        "submission_ready": False,
        "status": "LOCAL_PREFILTER_REJECTED",
        "failed_reasons": list(reasons),
    }


def local_backtest_support(
    candidate: Any,
    engine: Any,
    extract_fields: Callable[[str], list[Any] | set[Any] | tuple[Any, ...]],
    extract_operators: Callable[[str], list[Any] | set[Any] | tuple[Any, ...]],
) -> dict[str, Any]:
    profile = profile_expression(candidate.expression)
    declared_fields = getattr(candidate, "data_fields", None) or []
    parsed_fields = extract_fields(candidate.expression)
    fields = {
        str(field).lower()
        for field in [*declared_fields, *parsed_fields, *profile.fields]
        if str(field)
    }
    declared_operators = getattr(candidate, "operators", None) or []
    parsed_operators = extract_operators(candidate.expression)
    operators = {
        str(operator).lower()
        for operator in [*declared_operators, *parsed_operators, *profile.operators]
        if str(operator)
    }
    supported_fields = getattr(engine, "supported_fields", set())
    supported_operators = getattr(engine, "supported_operators", set())
    unsupported_fields = sorted(field for field in fields if field not in supported_fields)
    unsupported_operators = sorted(operator for operator in operators if operator not in supported_operators)
    reasons: list[str] = []
    if unsupported_fields:
        reasons.append("unsupported_fields=" + ",".join(unsupported_fields[:8]))
    if unsupported_operators:
        reasons.append("unsupported_operators=" + ",".join(unsupported_operators[:8]))
    return {
        "supported": not reasons,
        "fields": sorted(fields),
        "operators": sorted(operators),
        "unsupported_fields": unsupported_fields,
        "unsupported_operators": unsupported_operators,
        "reasons": reasons or ["supported"],
    }


def apply_local_backtest_gate(
    candidate: Any,
    *,
    engine: Any,
    cache_key: str,
    extract_fields: Callable[[str], list[Any] | set[Any] | tuple[Any, ...]],
    extract_operators: Callable[[str], list[Any] | set[Any] | tuple[Any, ...]],
    score_penalty: float = 8.0,
    reject_unsupported: bool = False,
    reject_failed_metrics: bool = True,
) -> dict[str, Any]:
    """Attach local backtest evidence and fail-close on rejected results."""

    local = dict(getattr(candidate, "local_quality", {}) or {})
    submission = dict(getattr(candidate, "submission", {}) or {})
    support = local_backtest_support(candidate, engine, extract_fields, extract_operators)
    local["local_backtest_support"] = support
    outcome: dict[str, Any] = {"support": support, "result": None, "evaluated": False}

    if not support["supported"]:
        warnings = list(local.get("warnings") or [])
        append_unique(warnings, "local_backtest_skipped:" + "; ".join(support["reasons"]))
        local["warnings"] = warnings
        if reject_unsupported:
            reasons = list(local.get("reasons") or [])
            for reason in support["reasons"]:
                append_unique(reasons, "local_backtest_unsupported:" + reason)
            local["passed"] = False
            local["reasons"] = reasons
            local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - score_penalty, 2))
        submission["local_backtest"] = {
            "ok": False,
            "skipped": True,
            "reasons": support["reasons"],
        }
        candidate.local_quality = local
        candidate.submission = submission
        return outcome

    result = dict(engine.evaluate(candidate.expression, cache_key=cache_key or "default"))
    outcome["result"] = result
    outcome["evaluated"] = True
    advisory = not reject_failed_metrics
    result["advisory"] = advisory
    result["blocking"] = not advisory
    submission["local_backtest"] = result
    local["local_backtest"] = {
        "ok": bool(result.get("ok")),
        "pass_local": bool(result.get("pass_local")),
        "advisory": advisory,
        "blocking": not advisory,
        "sharpe": result.get("sharpe"),
        "fitness": result.get("fitness"),
        "turnover": result.get("turnover"),
        "weight_concentration": result.get("weight_concentration"),
        "reasons": list(result.get("pass_reasons") or []),
    }

    if not result.get("ok"):
        reasons = list(local.get("reasons") or [])
        append_unique(
            reasons,
            "local_backtest_error:" + str(result.get("error") or result.get("error_type") or "unknown"),
        )
        local["passed"] = False
        local["reasons"] = reasons
    elif not result.get("pass_local"):
        failed_reasons = [
            str(reason)
            for reason in list(result.get("pass_reasons") or [])
            if "(FAIL)" in str(reason)
        ] or ["local backtest thresholds were not met"]
        warnings = list(local.get("warnings") or [])
        for reason in failed_reasons:
            append_unique(warnings, ("local_backtest_advisory:" if advisory else "local_backtest:") + reason)
        local["warnings"] = warnings
        if reject_failed_metrics:
            reasons = list(local.get("reasons") or [])
            for reason in failed_reasons:
                append_unique(reasons, "local_backtest_failed:" + reason)
            local["passed"] = False
            local["reasons"] = reasons
            local["score"] = max(0.0, round(float(local.get("score", 0.0) or 0.0) - score_penalty, 2))

    candidate.local_quality = local
    candidate.submission = submission
    return outcome
