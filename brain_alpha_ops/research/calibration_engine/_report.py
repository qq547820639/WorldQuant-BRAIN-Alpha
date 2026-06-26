"""Formatted report output for ``calibration_engine``.

Extracted from the original ``calibration_engine.py``.
"""
from __future__ import annotations

from typing import Any, Dict


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
        print("\n  【Prior Score 权重校准】")
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
        print("\n  【Scorecard 三层权重校准】")
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
    print("\n  【使用建议】")
    if prior_result.get("optimized_weights"):
        print("  将以下配置加入 config/run_config.json 的 scoring 段:")
        print("  \"prior_weights_override\": {")
        for dim, w in prior_result["optimized_weights"].items():
            print(f'    "{dim}": {w:.4f},')
        print("  }")
    if scorecard_result.get("optimized_weights"):
        print("\n  \"scorecard_layer_weights\": {")
        sw = scorecard_result["optimized_weights"]
        for k in ["prior", "empirical", "checklist"]:
            print(f'    "{k}": {sw.get(k, 0)}')
        print("  }")

    print("\n" + "=" * 72)
