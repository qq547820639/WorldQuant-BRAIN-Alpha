"""Quality check result descriptions and gate failure formatting.

Split from the former ``brain_alpha_ops/ux/errors.py`` monolith
(deep-optimization-phase13). Provides ``translate_check_result`` for
user-facing descriptions of each quality gate, and ``format_gate_failure``
for rendering a raw gate failure string into structured guidance.
"""
from __future__ import annotations


def translate_check_result(check_name: str) -> dict[str, str]:
    """Provide user-friendly description for a quality check."""
    descriptions: dict[str, dict[str, str]] = {
        "sharpe_positive": {
            "name": "夏普比率 ≥ 1.25",
            "meaning": "风险调整后收益。低于阈值说明风险回报不理想。",
            "fix": "尝试减少极端值暴露或缩短回看窗口。",
        },
        "fitness_minimum": {
            "name": "适应度 ≥ 1.0",
            "meaning": "综合评分。BRAIN 官方公式：Sharpe × √(|收益| / max(换手率, 0.125))。",
            "fix": "提高夏普比率或降低换手率可提升适应度。",
        },
        "returns_positive": {
            "name": "收益为正",
            "meaning": "平均每日收益。负收益意味着策略方向可能错误。",
            "fix": "检查因子方向是否正确，可尝试取反。",
        },
        "turnover_platform": {
            "name": "换手率 ≤ 70%",
            "meaning": "日均换手率。超过 70% 会被 BRAIN 平台硬门禁拒绝。",
            "fix": "增加回看窗口、减少交易频率、添加流动性过滤。",
        },
        "turnover_quality": {
            "name": "换手率质量阈值 ≤ 30%",
            "meaning": "顾问建议的质量阈值（非 BRAIN 硬门禁）。",
            "fix": "进一步优化换手率以提升评分。",
        },
        "self_correlation": {
            "name": "自相关 < 0.70",
            "meaning": "PnL 自相关。过高表明 Alpha 可能过拟合或表现不稳定。",
            "fix": "简化表达式、增加 OOS 验证、避免过度参数化。",
        },
        "prod_correlation": {
            "name": "产品相关 < 0.70",
            "meaning": "与已有产品 Alpha 的相关性。过高会被 BRAIN 拒绝。",
            "fix": "改变算子组合或使用不同的数据字段族。",
        },
        "weight_concentration": {
            "name": "权重集中度 ≤ 10%",
            "meaning": "单只股票最大权重。超过 10% 会被 BRAIN 拒绝。",
            "fix": "添加分散化约束或使用 group_neutralize。",
        },
        "sub_universe_sharpe": {
            "name": "子域夏普比率",
            "meaning": "在子域（如中小盘）中的表现。低于阈值说明泛化能力不足。",
            "fix": "增加跨市场验证或选择更通用的因子。",
        },
        "expression_valid": {
            "name": "表达式语法有效",
            "meaning": "表达式是否能在 BRAIN 平台正确解析。",
            "fix": "检查算子名称、括号匹配、字段是否存在。",
        },
    }

    info = descriptions.get(check_name)
    if info:
        return info
    return {
        "name": check_name,
        "meaning": "质量检查项",
        "fix": "请查看评分详情了解具体不通过原因。",
    }


def format_gate_failure(failure: str) -> dict[str, str]:
    """Format a gate failure reason into user-friendly terms."""
    parts = failure.split(" ", 1)
    check_name = parts[0].rstrip(":") if parts else failure

    info = translate_check_result(check_name)

    return {
        "check": check_name,
        "friendly_name": info["name"],
        "meaning": info["meaning"],
        "fix": info["fix"],
        "raw": failure,
    }
