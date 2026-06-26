"""Data loading, dimension computation, and mock feature generation
for ``calibration_engine``.

Extracted from the original ``calibration_engine.py``.
"""
from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List

from brain_alpha_ops.scoring.shared_scores import default_prior_dimensions


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
