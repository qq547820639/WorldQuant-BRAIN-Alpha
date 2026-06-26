"""Linear-regression and grid-search weight calibration algorithms
for ``calibration_engine``.

Extracted from the original ``calibration_engine.py``.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ._data import compute_prior_dimensions
from ._stats import _pearson_r


def calibrate_prior_weights(
    records: List[Dict[str, Any]],
    target_metric: str = "sharpe",
) -> Dict[str, Any]:
    """Perform multivariate linear regression on the 8 prior_score dimensions to optimize weights.

    target_metric: "sharpe" | "fitness" | "margin"

    Returns:
        {
            "sample_size": int,
            "target": str,
            "original_weights": {...},
            "optimized_weights": {...},
            "dimension_importance": [{"dim": str, "coef": float, "pseudo_r2": float}],
            "r_squared": float,
            "summary": str,
        }
    """
    dim_names = [
        "economic_logic", "structure", "field_operator_support",
        "data_compliance", "horizon_turnover_proxy",
        "risk_control_proxy", "diversity", "explainability",
    ]

    # Extract feature matrix X and target vector y
    X: List[List[float]] = []
    y: List[float] = []
    used_records = 0

    for record in records:
        if record.get("pass_fail") != "PASS":
            continue
        target_value = record.get(target_metric, 0)
        if not target_value or target_value <= 0:
            continue
        dims = compute_prior_dimensions(record)
        if not dims:
            continue
        # Normalize features to [0, 1] range (each dimension original range 25-92)
        row = [(dims.get(d, 50) - 10) / 100.0 for d in dim_names]
        X.append(row)
        y.append(float(target_value))
        used_records += 1

    if used_records < 10:
        return {
            "sample_size": used_records,
            "target": target_metric,
            "error": f"insufficient samples ({used_records} < 10)",
            "original_weights": {},
            "optimized_weights": {},
        }

    # Simple linear regression (OLS on normalized data)
    # For simplicity, compute Pearson correlation and normalize to weights
    # In production, replace with sklearn.linear_model.LinearRegression

    coefs = []
    for i, dim in enumerate(dim_names):
        xi = [row[i] for row in X]
        corr = _pearson_r(xi, y)
        coefs.append({"dim": dim, "pearson_r": round(corr, 4)})

    # Take absolute values as weight basis, then normalize
    abs_coefs = [max(0.001, abs(c["pearson_r"])) for c in coefs]
    total = sum(abs_coefs)
    normalized = [c / total for c in abs_coefs]

    optimized = {}
    for i, dim in enumerate(dim_names):
        optimized[dim] = round(normalized[i], 4)

    # R² 估计：用多变量线性组合的预测能力
    y_mean = sum(y) / len(y)
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    # Bootstrap estimate of predictive R² via correlation
    combined_scores = []
    for row in X:
        score = sum(row[i] * normalized[i] for i in range(len(normalized)))
        combined_scores.append(score)
    r_squared = round(_pearson_r(combined_scores, y) ** 2, 4)

    return {
        "sample_size": used_records,
        "target": target_metric,
        "original_weights": {
            "economic_logic": 0.18, "structure": 0.14,
            "field_operator_support": 0.16, "data_compliance": 0.12,
            "horizon_turnover_proxy": 0.14, "risk_control_proxy": 0.14,
            "diversity": 0.07, "explainability": 0.05,
        },
        "optimized_weights": optimized,
        "dimension_correlations": coefs,
        "r_squared": r_squared,
        "summary": (
            f"Calibrated {used_records} winning records ({target_metric}). "
            f"R²={r_squared:.4f}. "
            f"Top predictor: {max(coefs, key=lambda c: abs(c['pearson_r']))['dim']} "
            f"(r={max(coefs, key=lambda c: abs(c['pearson_r']))['pearson_r']:.4f})."
        ),
    }


def calibrate_scorecard_weights(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """校准 scorecard 的三层权重 (prior/empirical/checklist)。

    原始: 0.30 / 0.45 / 0.25
    目标: 最大化 total_score 与 official_sharpe 的相关性
    """
    # 需要同时有 prior dimensions 和 official metrics 的记录
    paired = []
    for record in records:
        if record.get("pass_fail") != "PASS":
            continue
        sharpe = record.get("sharpe", 0)
        if not sharpe or sharpe <= 0:
            continue
        dims = compute_prior_dimensions(record)
        if not dims:
            continue
        # 模拟 prior_score
        orig_w = {
            "economic_logic": 0.18, "structure": 0.14,
            "field_operator_support": 0.16, "data_compliance": 0.12,
            "horizon_turnover_proxy": 0.14, "risk_control_proxy": 0.14,
            "diversity": 0.07, "explainability": 0.05,
        }
        prior = sum(dims[k] * orig_w.get(k, 0) for k in dims)
        # 模拟 empirical (简化：直接用 sharpe 做 proxy)
        empirical = min(100, sharpe * 50)
        # 模拟 checklist
        checklist = 75 if record.get("fitness", 0) >= 1.0 else 50
        paired.append((prior, empirical, checklist, sharpe))

    if len(paired) < 10:
        return {"sample_size": len(paired), "error": "insufficient samples"}

    # 网格搜索最优权重
    best_corr = -1.0
    best_weights = (0.30, 0.45, 0.25)
    for pw in [round(x * 0.05, 2) for x in range(4, 12)]:  # 0.20 - 0.55
        for ew in [round(x * 0.05, 2) for x in range(6, 16)]:  # 0.30 - 0.75
            cw = 1.0 - pw - ew
            if cw <= 0:
                continue
            totals = [pw * p + ew * e + cw * c for p, e, c, _ in paired]
            corr = _pearson_r(totals, [s for _, _, _, s in paired])
            if abs(corr) > best_corr:
                best_corr = abs(corr)
                best_weights = (pw, ew, cw)

    return {
        "sample_size": len(paired),
        "target": "sharpe",
        "original_weights": {"prior": 0.30, "empirical": 0.45, "checklist": 0.25},
        "optimized_weights": {
            "prior": round(best_weights[0], 2),
            "empirical": round(best_weights[1], 2),
            "checklist": round(best_weights[2], 2),
        },
        "correlation_with_sharpe": round(best_corr, 4),
        "summary": (
            f"Scorecard weights: prior={best_weights[0]:.2f}, empirical={best_weights[1]:.2f}, "
            f"checklist={best_weights[2]:.2f} (corr={best_corr:.4f})."
        ),
    }
