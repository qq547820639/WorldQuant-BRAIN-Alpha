"""Statistical helpers for ``calibration_engine``.

Internal utilities extracted from the original ``calibration_engine.py``;
kept package-private.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List


def _pearson_r(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    return cov / (sx * sy)


def _predict_linear(
    X: List[List[float]],
    coefs: List[Dict[str, Any]],
    weights: List[float],
) -> float:
    """Predict using linear combination of features and weights."""
    # X is a list of [rows], each row is a list of feature values per dimension
    predictions = []
    for row in X:
        pred = sum(feature_val * weight for feature_val, weight in zip(row, weights))
        predictions.append(pred)
    return sum(predictions) / len(predictions) if predictions else 0.0
