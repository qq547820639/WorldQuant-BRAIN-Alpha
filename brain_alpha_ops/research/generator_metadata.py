"""Official metadata helpers for candidate generation."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from brain_alpha_ops.research.expression_ast import ordered_operators
from brain_alpha_ops.research.validated_generator import (
    OPERATOR_SIGNATURES,
    WINDOW_CONSTRAINTS,
)

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader

logger = logging.getLogger("brain_alpha_ops.research.generator")

DEFAULT_WINDOWS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]
DEFAULT_WINSOR_STD = [3, 4, 5, 6]
OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES: dict[str, list[str]] = {
    "ranking": ["ts_rank", "rank", "group_rank"],
    "standardization": ["zscore", "scale", "group_zscore", "normalize"],
    "moving_average": ["ts_mean", "ts_sum", "ts_product"],
    "difference": ["ts_delta", "ts_av_diff", "ts_delay"],
    "volatility": ["ts_std_dev"],
    "correlation": ["ts_corr", "ts_covariance"],
    "winsorization": ["winsorize"],
    "decay": ["ts_decay_linear"],
}


def _get_default_windows() -> list[int]:
    """Return a copy of the built-in fallback windows."""
    return list(DEFAULT_WINDOWS)


def _get_default_winsor_stds() -> list[int]:
    """Return a copy of the built-in fallback winsorize std values."""
    return list(DEFAULT_WINSOR_STD)


def expression_windows_within_constraints(expression: str) -> bool:
    """Return whether all known window arguments satisfy local gate constraints."""

    return not generation_window_constraint_violations(expression)


def generation_window_constraint_violations(expression: str) -> list[dict[str, int | str]]:
    """Return operator-specific window violations for generated expressions.

    The generator may still use long windows where the operator allows them
    (for example ``ts_rank`` or ``ts_mean``).  This guard only rejects windows
    that the current quality gate would later mark as out of bounds for the
    concrete operator receiving the argument.
    """

    text = str(expression or "")
    violations: list[dict[str, int | str]] = []
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", text):
        op = _window_constraint_operator_name(match.group(1))
        signature = OPERATOR_SIGNATURES.get(op)
        if not signature:
            continue
        args = _extract_call_args(text, match.end() - 1)
        if args is None:
            violations.append({"operator": op, "window": "unmatched", "min": 0, "max": 0})
            continue
        parts = _split_top_level_args(args)
        for index, param_type in enumerate(signature.get("params") or []):
            if param_type != "d":
                continue
            if index >= len(parts):
                violations.append({"operator": op, "window": "missing", "min": 0, "max": 0})
                continue
            raw_window = parts[index].strip()
            if not re.fullmatch(r"\d+", raw_window):
                violations.append({"operator": op, "window": raw_window, "min": 0, "max": 0})
                continue
            window = int(raw_window)
            bounds = WINDOW_CONSTRAINTS.get(op, {})
            minimum = int(bounds.get("min", 1))
            maximum = int(bounds.get("max", 252))
            if window < minimum or window > maximum:
                violations.append({"operator": op, "window": window, "min": minimum, "max": maximum})
    return violations


def _window_constraint_operator_name(name: str) -> str:
    aliases = {
        "ts_covariance": "ts_cov",
    }
    return aliases.get(str(name or "").lower(), str(name or "").lower())


def _extract_call_args(expression: str, open_paren_index: int) -> str | None:
    depth = 0
    for index in range(open_paren_index, len(expression)):
        char = expression[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return expression[open_paren_index + 1:index]
            if depth < 0:
                return None
    return None


def _split_top_level_args(args: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(args):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(args[start:index].strip())
            start = index + 1
    tail = args[start:].strip()
    if tail or args:
        parts.append(tail)
    return parts


def _load_operators_windows(loader: "OfficialDataLoader | None" = None) -> tuple[list[int], list[int]]:
    """Derive generation knobs from official operator metadata when available."""
    try:
        if loader is None:
            from brain_alpha_ops.data import OfficialDataLoader

            loader = OfficialDataLoader.instance()
        operators = loader.get_operators()
    except Exception:
        logger.warning("operator metadata unavailable; using default generation windows", exc_info=True)
        return _get_default_windows(), _get_default_winsor_stds()

    windows: set[int] = set()
    winsor_stds: set[int] = set()
    for op in operators or []:
        name = _operator_attr(op, "name").lower()
        category = _operator_attr(op, "category").lower()
        definition = _operator_attr(op, "definition")
        description = _operator_attr(op, "description")
        text = f"{definition} {description}"
        if name.startswith("ts_") or "time series" in category:
            windows.update(_parameter_defaults(op, {"window", "lookback", "d"}))
            if re.search(r"\b(d|lookback)\b", definition):
                windows.update(_get_default_windows())
        if name in {"winsorize", "group_backfill"} or "winsor" in text.lower():
            winsor_stds.update(_parameter_defaults(op, {"std", "standard_deviation"}))
            winsor_stds.update(
                int(float(value))
                for value in re.findall(r"\bstd\s*=\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
            )

    return (
        sorted(w for w in windows if w > 0) or _get_default_windows(),
        sorted(w for w in winsor_stds if w > 0) or _get_default_winsor_stds(),
    )


def _operator_attr(operator: object, name: str) -> str:
    if isinstance(operator, dict):
        value = operator.get(name, "")
        if not value and isinstance(operator.get("raw"), dict):
            value = operator["raw"].get(name, "")
        return str(value or "")
    return str(getattr(operator, name, "") or "")


def _parameter_defaults(operator: object, names: set[str]) -> set[int]:
    if not isinstance(operator, dict):
        return set()
    values: set[int] = set()
    params = operator.get("parameters")
    if not isinstance(params, list) and isinstance(operator.get("raw"), dict):
        params = operator["raw"].get("parameters")
    if not isinstance(params, list):
        return values
    for param in params:
        if not isinstance(param, dict):
            continue
        param_name = str(param.get("name") or param.get("type") or "").lower()
        if param_name not in names:
            continue
        for key in ("default", "value"):
            value = param.get(key)
            if isinstance(value, (int, float)) and value > 0:
                values.add(int(value))
        choices = param.get("choices") or param.get("values")
        if isinstance(choices, list):
            for value in choices:
                if isinstance(value, (int, float)) and value > 0:
                    values.add(int(value))
    return values


def _load_official_operator_names(loader: "OfficialDataLoader | None" = None) -> set[str]:
    """Return operator names from the current official snapshot, or empty on failure."""
    try:
        if loader is None:
            from brain_alpha_ops.data import OfficialDataLoader

            loader = OfficialDataLoader.instance()
        return {
            _operator_attr(operator, "name").lower()
            for operator in loader.get_operators()
            if _operator_attr(operator, "name")
        }
    except Exception:
        logger.warning("official operator metadata unavailable; generation fails closed", exc_info=True)
        return set()


def _expression_operators_are_official(expression: str, official_operators: set[str]) -> bool:
    if not official_operators:
        return False
    return {operator.lower() for operator in ordered_operators(expression)} <= official_operators
