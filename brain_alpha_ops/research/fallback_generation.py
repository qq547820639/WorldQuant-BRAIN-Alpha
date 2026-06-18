"""Fallback expression helpers for hypothesis-driven generation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from brain_alpha_ops.research.expression_ast import (
    expression_key,
    expression_similarity,
)
from brain_alpha_ops.research.generator_metadata import (
    expression_windows_within_constraints,
)

DEFAULT_WINDOWS = (3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252)
DUPLICATE_SIMILARITY_THRESHOLD = 0.90
_DIRECT_RETURNS_DELTA_PATTERN = re.compile(
    r"\bts_delta\s*\(\s*returns\s*,\s*(\d+)\b",
    flags=re.IGNORECASE,
)

_FALLBACK_TEMPLATES = (
    ("rank(ts_delta({f1}, {w}))", {"rank", "ts_delta"}, "momentum"),
    ("rank(ts_rank({f1}, {w}))", {"rank", "ts_rank"}, "momentum"),
    ("rank(ts_mean({f1}, {w}))", {"rank", "ts_mean"}, "liquidity"),
    ("rank(zscore({f1}))", {"rank", "zscore"}, "quality"),
    ("rank(-{f1})", {"rank"}, "reversal"),
    ("rank(ts_corr({f1}, {f2}, {w}))", {"rank", "ts_corr"}, "hybrid"),
)


def normalize_operator_aliases(expression: str) -> str:
    replacements = {
        "ts_std": "ts_std_dev",
        "ts_argmax": "ts_arg_max",
        "ts_argmin": "ts_arg_min",
        "ts_cov": "ts_covariance",
    }
    normalized = expression
    for old, new in replacements.items():
        normalized = re.sub(rf"\b{old}\s*\(", f"{new}(", normalized)
    return normalized


@dataclass(frozen=True)
class BareFallbackSpec:
    expression: str
    family: str
    data_fields: list[str]
    next_cursor: int


def build_bare_fallback_spec(
    *,
    fields: list[str],
    operators: set[str],
    windows: list[int] | tuple[int, ...],
    cursor: int,
) -> BareFallbackSpec:
    usable_templates = [
        row
        for row in _FALLBACK_TEMPLATES
        if not operators or row[1].issubset(operators)
    ] or [_FALLBACK_TEMPLATES[0]]
    safe_fields = fields or ["returns"]
    safe_windows = list(windows or DEFAULT_WINDOWS)
    template_count = len(usable_templates)
    field_count = len(safe_fields)
    expression = ""
    template = usable_templates[cursor % template_count][0]
    family = usable_templates[cursor % template_count][2]
    f1 = safe_fields[0]
    f2 = safe_fields[0]
    window_index = 0
    for offset in range(max(1, template_count * field_count * len(safe_windows))):
        position = cursor + offset
        template, _required_ops, family = usable_templates[position % template_count]
        field_index = (position // template_count) % field_count
        f1 = safe_fields[field_index]
        f2 = safe_fields[(field_index + 1) % field_count] if field_count > 1 else f1
        window_index = (position // max(1, template_count * field_count)) % len(safe_windows)
        expression = template.replace("{f1}", f1).replace("{f2}", f2).replace("{w}", str(safe_windows[window_index]))
        if (
            expression_windows_within_constraints(expression)
            and not is_high_turnover_generation_risk(expression)
        ):
            break
    data_fields = [f1] if f1 == f2 or "{f2}" not in template else [f1, f2]
    return BareFallbackSpec(
        expression=expression,
        family=family,
        data_fields=data_fields,
        next_cursor=cursor + 1,
    )


def high_turnover_generation_risk_reasons(expression: str) -> list[str]:
    """Return generation-only risk reasons for known high-turnover structures."""
    reasons: list[str] = []
    text = str(expression or "")
    for match in _DIRECT_RETURNS_DELTA_PATTERN.finditer(text):
        try:
            window = int(match.group(1))
        except (TypeError, ValueError):
            continue
        reasons.append(f"direct_returns_delta_window={window}")
    return reasons


def is_high_turnover_generation_risk(expression: str) -> bool:
    """Reject known high-turnover generation shapes before local/official gates."""
    return bool(high_turnover_generation_risk_reasons(expression))


def is_generated_duplicate(expression: str, seen_keys: set[str], seen_expressions: list[str]) -> bool:
    key = expression_key(expression)
    if key in seen_keys:
        return True
    return any(
        expression_similarity(expression, seen) >= DUPLICATE_SIMILARITY_THRESHOLD
        for seen in seen_expressions
    )
