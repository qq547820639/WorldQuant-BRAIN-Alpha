"""Semantic FASTEXPR validation engine.

This layer keeps the lightweight parser in ``expression_ast`` as the source of
truth and adds policy-oriented validation reports for generation, LLM review,
and submission gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from brain_alpha_ops.research.expression_ast import ExpressionProfile, profile_expression


EXPRESSION_ENGINE_SCHEMA_VERSION = "expression-engine-report.v1"
DEFAULT_MAX_DEPTH = 12
DEFAULT_MAX_NODE_COUNT = 80
DEFAULT_MAX_WINDOW = 512
DEFAULT_MAX_EXPRESSION_LENGTH = 512


@dataclass(frozen=True)
class ExpressionValidationIssue:
    code: str
    severity: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


@dataclass(frozen=True)
class ExpressionValidationReport:
    expression: str
    mode: str
    parsed: bool
    valid: bool
    blocked: bool
    complexity_score: float
    semantic_tags: tuple[str, ...]
    profile: ExpressionProfile
    issues: tuple[ExpressionValidationIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXPRESSION_ENGINE_SCHEMA_VERSION,
            "expression": self.expression,
            "mode": self.mode,
            "parsed": self.parsed,
            "valid": self.valid,
            "blocked": self.blocked,
            "complexity_score": self.complexity_score,
            "semantic_tags": list(self.semantic_tags),
            "canonical": self.profile.canonical,
            "fingerprint": self.profile.fingerprint,
            "operators": list(self.profile.operators),
            "fields": list(self.profile.fields),
            "windows": list(self.profile.windows),
            "max_depth": self.profile.max_depth,
            "node_count": self.profile.node_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class ExpressionEngine:
    """Validate FASTEXPR syntax, operator/field scope, and complexity."""

    def __init__(
        self,
        *,
        allowed_fields: Iterable[str] | None = None,
        allowed_operators: Iterable[str] | None = None,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_node_count: int = DEFAULT_MAX_NODE_COUNT,
        max_window: int = DEFAULT_MAX_WINDOW,
        max_expression_length: int = DEFAULT_MAX_EXPRESSION_LENGTH,
    ) -> None:
        self.allowed_fields = _normalized_set(allowed_fields)
        self.allowed_operators = _normalized_set(allowed_operators)
        self.max_depth = max(1, int(max_depth or DEFAULT_MAX_DEPTH))
        self.max_node_count = max(1, int(max_node_count or DEFAULT_MAX_NODE_COUNT))
        self.max_window = max(1, int(max_window or DEFAULT_MAX_WINDOW))
        self.max_expression_length = max(1, int(max_expression_length or DEFAULT_MAX_EXPRESSION_LENGTH))

    def validate(self, expression: str, *, mode: str = "wq") -> ExpressionValidationReport:
        active_mode = str(mode or "wq").strip().lower()
        profile = profile_expression(expression)
        issues: list[ExpressionValidationIssue] = []

        if not profile.parsed:
            issues.append(_issue("parse_error", "ERROR", profile.parse_error or "expression could not be parsed"))

        if len(profile.expression) > self.max_expression_length:
            issues.append(
                _issue(
                    "expression_too_long",
                    "ERROR",
                    f"expression length exceeds {self.max_expression_length}",
                    actual=len(profile.expression),
                    limit=self.max_expression_length,
                )
            )
        if profile.max_depth > self.max_depth:
            issues.append(
                _issue(
                    "max_depth_exceeded",
                    "ERROR",
                    f"expression depth exceeds {self.max_depth}",
                    actual=profile.max_depth,
                    limit=self.max_depth,
                )
            )
        if profile.node_count > self.max_node_count:
            issues.append(
                _issue(
                    "node_count_exceeded",
                    "ERROR",
                    f"expression node count exceeds {self.max_node_count}",
                    actual=profile.node_count,
                    limit=self.max_node_count,
                )
            )

        unknown_fields = sorted(field for field in profile.fields if self.allowed_fields and field not in self.allowed_fields and not _is_group_key(field))
        if unknown_fields:
            issues.append(_issue("unknown_fields", "ERROR", "expression uses fields outside the official context", values=unknown_fields[:20]))

        unknown_operators = sorted(operator for operator in profile.operators if self.allowed_operators and operator not in self.allowed_operators)
        if unknown_operators:
            issues.append(_issue("unknown_operators", "ERROR", "expression uses unsupported operators", values=unknown_operators[:20]))

        long_windows = [window for window in profile.windows if window > self.max_window]
        if long_windows:
            issues.append(_issue("window_too_long", "WARNING", f"lookback window exceeds {self.max_window}", values=long_windows[:20]))

        tags = semantic_tags(profile)
        if active_mode == "wq":
            issues.extend(_wq_semantic_issues(profile, tags))
        elif active_mode == "local":
            issues.extend(_local_semantic_issues(profile))
        else:
            issues.append(_issue("unknown_mode", "WARNING", f"unknown validation mode: {active_mode}"))

        blocked = any(issue.severity == "ERROR" for issue in issues)
        return ExpressionValidationReport(
            expression=profile.expression,
            mode=active_mode,
            parsed=profile.parsed,
            valid=profile.parsed and not blocked,
            blocked=blocked,
            complexity_score=complexity_score(profile),
            semantic_tags=tuple(tags),
            profile=profile,
            issues=tuple(issues),
        )


def validate_expression(
    expression: str,
    *,
    allowed_fields: Iterable[str] | None = None,
    allowed_operators: Iterable[str] | None = None,
    mode: str = "wq",
) -> dict[str, Any]:
    return ExpressionEngine(
        allowed_fields=allowed_fields,
        allowed_operators=allowed_operators,
    ).validate(expression, mode=mode).to_dict()


def semantic_tags(profile: ExpressionProfile) -> list[str]:
    operators = set(profile.operators)
    tags: list[str] = []
    if any(operator.startswith("ts_") for operator in operators):
        tags.append("time_series")
    if operators & {"rank", "zscore", "scale", "group_rank", "group_zscore"}:
        tags.append("cross_sectional")
    if operators & {"group_rank", "group_zscore", "group_neutralize", "regression_neut"}:
        tags.append("group_aware")
    if operators & {"winsorize", "truncate", "scale", "group_neutralize"}:
        tags.append("risk_control")
    if any(window <= 7 for window in profile.windows):
        tags.append("short_horizon")
    if any(8 <= window <= 60 for window in profile.windows):
        tags.append("medium_horizon")
    if any(window > 60 for window in profile.windows):
        tags.append("long_horizon")
    return list(dict.fromkeys(tags))


def complexity_score(profile: ExpressionProfile) -> float:
    raw = (
        profile.node_count * 1.0
        + profile.max_depth * 4.0
        + len(profile.operators) * 2.0
        + len(profile.fields) * 1.5
        + len(profile.windows) * 0.75
    )
    return round(min(100.0, raw), 2)


def _wq_semantic_issues(profile: ExpressionProfile, tags: list[str]) -> list[ExpressionValidationIssue]:
    issues: list[ExpressionValidationIssue] = []
    if profile.parsed and not profile.operators:
        issues.append(_issue("missing_operator", "ERROR", "WQ expression should include at least one operator"))
    if "cross_sectional" not in tags and "time_series" not in tags:
        issues.append(_issue("weak_semantics", "WARNING", "expression has no clear time-series or cross-sectional transform"))
    if len(profile.fields) > 8:
        issues.append(_issue("too_many_fields", "WARNING", "expression uses many fields and may overfit", actual=len(profile.fields), limit=8))
    return issues


def _local_semantic_issues(profile: ExpressionProfile) -> list[ExpressionValidationIssue]:
    if not profile.expression.strip():
        return [_issue("empty_expression", "ERROR", "expression is empty")]
    return []


def _issue(code: str, severity: str, message: str, **detail: Any) -> ExpressionValidationIssue:
    return ExpressionValidationIssue(code=code, severity=severity, message=message, detail={key: value for key, value in detail.items() if value not in (None, "")})


def _normalized_set(values: Iterable[str] | None) -> set[str]:
    return {str(value).strip().lower() for value in values or [] if str(value).strip()}


def _is_group_key(value: str) -> bool:
    return value in {"market", "sector", "industry", "subindustry", "country", "exchange"}
