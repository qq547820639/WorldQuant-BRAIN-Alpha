"""Internal scoring-weight calibration helpers.

These helpers are consumed by the Web/automation pipeline after enough official
PASS/FAIL evidence has accumulated.  They are deliberately package-internal:
operators must use the browser Web console rather than a command-line tool.
"""

from __future__ import annotations

import json
import math
import os
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from brain_alpha_ops.scoring.shared_scores import default_prior_dimensions

# ═══════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════

def load_alpha_features(path: str) -> List[Dict[str, Any]]:
    """Load all Alpha feature records from alpha_features.jsonl.

    Each line should contain:
        - Official metrics: sharpe, fitness, turnover, correlation, margin, etc.
        - Features: field_set, operator_set, window_values, family
        - pass_fail: PASS/FAIL
    """
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


# ═══════════════════════════════════════════════════════════════════════
# Prior Score dimension computation (reuses runtime scoring default logic)
# ═══════════════════════════════════════════════════════════════════════

def compute_prior_dimensions(record: Dict[str, Any]) -> Dict[str, float]:
    """Compute the same eight default dimensions used by ``prior_score``.

    Returns: {"economic_logic": 85, "structure": 74, ...}
    """
    expression = str(record.get("expression", ""))
    fields = set(str(f).lower() for f in (record.get("field_set") or []))
    operators = list(record.get("operator_set") or [])
    hypothesis = str(record.get("hypothesis", ""))
    family = str(record.get("family", ""))

    return default_prior_dimensions(
        expression=expression,
        fields=fields,
        operators=operators,
        hypothesis=hypothesis,
        family=family,
    )


# ═══════════════════════════════════════════════════════════════════════
# Linear regression calibration
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
# 统计工具
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
# Mock 数据生成（dry-run）
# ═══════════════════════════════════════════════════════════════════════

def generate_mock_features(n: int = 50) -> List[Dict[str, Any]]:
    """生成 mock alpha_features 数据用于校准算法验证。"""
    operators_pool = [
        ["rank", "ts_delta", "ts_std", "winsorize"],
        ["ts_mean", "zscore", "group_rank"],
        ["rank", "ts_rank", "ts_decay_linear", "scale"],
        ["ts_zscore", "group_neutralize"],
        ["rank", "ts_delta", "ts_mean", "abs"],
    ]
    fields_pool = [
        ["close", "volume", "adv20", "returns"],
        ["open", "high", "low", "close", "vwap"],
        ["returns", "ivol", "market_cap"],
        ["pe_ratio", "pb_ratio", "dividend_yield"],
        ["close", "volume", "sector"],
    ]
    expressions = [
        "rank(ts_delta(close, 20) / ts_std(returns, 20))",
        "rank(ts_mean(volume / adv20, 10)) * rank(-ts_std(returns, 60))",
        "group_rank(winsorize(ts_zscore(close, 60), 3), subindustry)",
        "rank(ts_decay_linear(ts_delta(close, 20) / ts_std(returns, 20), 10))",
        "rank(ts_mean(returns, 40)) * rank(ts_mean(volume / adv20, 20))",
    ]
    hypotheses = [
        "短期动量：近期价格趋势持续，高换手个股有动量效应。",
        "流动性溢价：高成交量的股票在短期内表现出价格异常。",
        "均值回归 + 波动率过滤：在子行业内做 zscore 信号。",
        "多周期动量衰减：用 decay_linear 平滑近期动量和波动率信号。",
        "交叉验证：动量 × 流动性双因子复合。",
    ]
    families = ["Momentum", "Liquidity", "Volatility", "Hybrid", "Momentum"]

    random.seed(42)
    records = []
    for i in range(n):
        idx = i % len(expressions)
        ops = operators_pool[idx]
        flds = fields_pool[idx]

        # 模拟 official 指标
        sharpe = round(0.8 + random.random() * 1.2, 3)
        fitness = round(sharpe * (0.6 + random.random() * 0.3), 3)
        turnover = round(0.05 + random.random() * 0.40, 3)

        records.append({
            "alpha_id": f"mock_cal_{i:04d}",
            "expression": expressions[idx],
            "field_set": flds,
            "operator_set": ops,
            "hypothesis": hypotheses[idx],
            "family": families[idx],
            "sharpe": sharpe,
            "fitness": fitness,
            "turnover": turnover,
            "returns": round(sharpe * 0.03 + random.random() * 0.02, 5),
            "correlation": round(0.15 + random.random() * 0.35, 4),
            "margin": round(3.0 + sharpe * 4.0, 2),
            "weight_concentration": round(0.03 + random.random() * 0.07, 4),
            "pass_fail": "PASS" if sharpe >= 1.25 else "FAIL",
        })

    return records


# ═══════════════════════════════════════════════════════════════════════
# 报告输出
# ═══════════════════════════════════════════════════════════════════════

def print_calibration_report(
    prior_result: Dict[str, Any],
    scorecard_result: Dict[str, Any],
) -> None:
    """打印格式化的校准报告。"""
    print("\n" + "=" * 72)
    print("  评分权重校准报告")
    print("=" * 72)

    # ── Prior weights ──
    if prior_result:
        print(f"\n  【Prior Score 权重校准】")
        print(f"  样本数: {prior_result.get('sample_size', 0)} | "
              f"目标: {prior_result.get('target', 'sharpe')} | "
              f"R²: {prior_result.get('r_squared', 'N/A')}")
        print(f"\n  {'维度':<28} {'原权重':>8} {'优化权重':>10} {'Pearson r':>10}")
        print(f"  {'-'*56}")
        dim_corrs = {c["dim"]: c["pearson_r"] for c in prior_result.get("dimension_correlations", [])}
        for dim in ["economic_logic", "structure", "field_operator_support",
                    "data_compliance", "horizon_turnover_proxy",
                    "risk_control_proxy", "diversity", "explainability"]:
            orig = prior_result["original_weights"].get(dim, 0)
            opt = prior_result.get("optimized_weights", {}).get(dim, 0)
            r = dim_corrs.get(dim, 0)
            delta = "+" if opt > orig else ""
            print(f"  {dim:<28} {orig:>8.4f} {delta}{opt:>9.4f} {r:>10.4f}")
        print(f"\n  {prior_result.get('summary', '')}")

    # ── Scorecard weights ──
    if scorecard_result:
        print(f"\n  【Scorecard 三层权重校准】")
        print(f"  样本数: {scorecard_result.get('sample_size', 0)} | "
              f"与 Sharpe 相关系数: {scorecard_result.get('correlation_with_sharpe', 'N/A')}")
        if "original_weights" not in scorecard_result:
            print(f"  {scorecard_result.get('error', '校准结果不完整，暂不能生成权重表。')}")
        else:
            print(f"\n  {'层':<16} {'原权重':>8} {'优化权重':>10}")
            print(f"  {'-'*34}")
            for key in ["prior", "empirical", "checklist"]:
                orig = scorecard_result["original_weights"].get(key, 0)
                opt = scorecard_result.get("optimized_weights", {}).get(key, 0)
                delta = "+" if opt > orig else ""
                print(f"  {key:<16} {orig:>8.2f} {delta}{opt:>9.2f}")
            print(f"\n  {scorecard_result.get('summary', '')}")

    # ── 使用建议 ──
    print(f"\n  【使用建议】")
    if prior_result.get("optimized_weights"):
        print(f"  将以下配置加入 config/run_config.json 的 scoring 段:")
        print(f"  \"prior_weights_override\": {{")
        for dim, w in prior_result["optimized_weights"].items():
            print(f'    "{dim}": {w:.4f},')
        print(f"  }}")
    if scorecard_result.get("optimized_weights"):
        print(f"\n  \"scorecard_layer_weights\": {{")
        sw = scorecard_result["optimized_weights"]
        for k in ["prior", "empirical", "checklist"]:
            print(f'    "{k}": {sw.get(k, 0)}')
        print(f"  }}")

    print("\n" + "=" * 72)


def auto_calibrate_if_stalled(
    storage_dir: str = "data",
    *,
    min_evaluations: int = 12,
    stall_threshold: float = 3.0,
    min_pass_rate: float = 0.3,
    features_path: str = "data/alpha_features.jsonl",
) -> dict:
    """Check convergence stats and auto-trigger calibration if stalled.

    Called by the research pipeline after accumulating enough score history.
    Returns a dict with advice / override config, or ok: False if not triggered.
    """
    try:
        from brain_alpha_ops.scoring.history import ScoreHistoryDB
        db = ScoreHistoryDB(storage_dir)
        stats = db.convergence_stats()
    except Exception as exc:
        return {"ok": False, "triggered": False, "reason": f"ScoreHistoryDB unavailable: {exc}"}

    if stats.get("status") != "ready":
        return {"ok": True, "triggered": False, "reason": "insufficient_data", "stats": stats}

    n = stats.get("total_evaluations", 0)
    if n < min_evaluations:
        return {"ok": True, "triggered": False, "reason": f"below min_evaluations ({n} < {min_evaluations})", "stats": stats}

    trend = stats.get("trend", "stable")
    recent_avg = stats.get("recent_avg", 0)
    global_avg = stats.get("avg_score", 0)
    pass_rate = stats.get("pass_rate", 0)

    stalled = (
        trend == "declining"
        or (trend == "stable" and abs(recent_avg - global_avg) < stall_threshold)
    )

    if not stalled:
        return {"ok": True, "triggered": False, "reason": f"trend={trend} not stalled", "stats": stats}

    # Load features and calibrate
    features = load_alpha_features(features_path)
    if len(features) < 8:
        return {"ok": True, "triggered": True, "calibration_failed": True, "reason": "insufficient features for calibration", "stats": stats}

    prior_result = calibrate_prior_weights(features, target_metric="sharpe")
    scorecard_result = calibrate_scorecard_weights(features)

    advice = {}
    if prior_result.get("optimized_weights"):
        advice["prior_weights_override"] = prior_result["optimized_weights"]
    if scorecard_result.get("optimized_layer_weights"):
        advice.update(scorecard_result["optimized_layer_weights"])

    return {
        "ok": True,
        "triggered": True,
        "reason": f"score convergence stalled (trend={trend}, pass_rate={pass_rate})",
        "stats": stats,
        "prior_calibration": prior_result,
        "scorecard_calibration": scorecard_result,
        "advice": advice,
        "recommendation": "Review the advice in the Web console and let maintainer automation apply approved scoring configuration changes.",
    }
