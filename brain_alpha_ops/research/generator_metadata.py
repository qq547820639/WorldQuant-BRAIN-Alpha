"""Official metadata helpers for candidate generation."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from brain_alpha_ops.research.expression_ast import ordered_operators

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
