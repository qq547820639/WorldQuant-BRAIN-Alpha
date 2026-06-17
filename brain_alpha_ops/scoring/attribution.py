"""Multi-dimensional scoring attribution with explainability.

AttributionNode — single dimension in the attribution tree.
build_attribution_tree() — builds the full three-layer attribution tree from a scorecard.
dim_explanation() — human-readable Chinese explanations for each dimension.
"""

from __future__ import annotations

from dataclasses import dataclass, field
# S-15: modern type hints (list[X], X | None) via from __future__ import annotations


@dataclass
class AttributionNode:
    """Single dimension in the attribution tree."""
    name: str
    score: float
    weight: float
    contribution: float  # score * weight
    children: list["AttributionNode"] = field(default_factory=list)
    explanation: str = ""
    calibratable: bool = False
    historical_trend: str | None = None  # "improving" | "stable" | "declining" | None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "contribution": round(self.contribution, 4),
            "explanation": self.explanation,
            "calibratable": self.calibratable,
            "historical_trend": self.historical_trend,
            "children": [c.to_dict() for c in self.children] if self.children else [],
        }


_DIM_EXPLANATIONS: dict[str, str] = {
    "economic_logic": "基于经济概念关键词检测评估",
    "structure": "算子数量与复杂度惩罚",
    "field_operator_support": "数据字段和算子可用性",
    "data_compliance": "数据字段是否为BRAIN官方字段",
    "horizon_turnover_proxy": "窗口参数与换手率估计",
    "risk_control_proxy": "截面/时序/风控算子组合",
    "diversity": "因子家族多样性",
    "explainability": "表达式可解释性(长度阈值)",
    # Empirical dimension explanations
    "sharpe": "BRAIN官方风险调整收益指标",
    "fitness": "BRAIN官方适应度: Sharpe × √(|Returns|/max(Turnover, 0.125))",
    "turnover_min": "最低换手率要求(≥1%)",
    "turnover_platform": "平台最高换手率限制(≤70%)",
    "turnover_quality": "质量目标换手率(≤30%)",
    "returns": "正收益预期",
    "drawdown": "最大回撤限制",
    "self_correlation": "PnL自相关检查(含Sharpe优势例外)",
    "prod_correlation": "生产相关性限制",
    "weight_concentration": "单股权重集中度限制(≤10%)",
    "sub_universe_sharpe": "子宇宙Sharpe稳定性检查",
    "margin_bps": "最低保证金要求(bps)",
    "fitness_crosscheck": "Fitness公式交叉验证(API vs 本地)",
    "is_oos_ratio": "样本内/样本外稳健性比率",
    # Checklist dimension explanations
    "official_metrics_present": "需要官方模拟指标",
    "official_pass": "需要BRAIN官方通过",
    "economic_logic_check": "需要经济逻辑假设文本(≥40字符)",
    "data_delay_conservative": "默认使用Delay 1保守设置",
    "local_quality": "本地预筛选质量通过",
    "self_correlation_proxy": "自相关代理检查",
}


def dim_explanation(dim_name: str, score: float = 0.0) -> str:
    """Return a human-readable explanation for a prior dimension."""
    return _DIM_EXPLANATIONS.get(dim_name, "")


def build_attribution_tree(scorecard: dict) -> AttributionNode:
    """Build multi-dimensional attribution tree from scorecard.

    Tree structure:
      total_score
      ├── prior_score (weight × score)
      │   ├── economic_logic
      │   ├── structure
      │   ├── field_operator_support
      │   ├── data_compliance
      │   ├── horizon_turnover_proxy
      │   ├── risk_control_proxy
      │   ├── diversity
      │   └── explainability
      ├── empirical_score (weight × score)
      │   ├── sharpe
      │   ├── fitness
      │   ├── turnover
      │   ├── self_correlation
      │   └── ...
      └── submission_checklist (weight × score)
          ├── official_metrics_present
          ├── official_pass
          └── ...
    """
    lw = scorecard.get("layer_weights", {"prior": 0.30, "empirical": 0.45, "checklist": 0.25})
    # S-03: Validate layer_weights sum ≈ 1.0 (warn if skewed)
    _lw_sum = sum(lw.values()) if lw else 0
    if _lw_sum and abs(_lw_sum - 1.0) > 1e-6:
        import warnings
        warnings.warn(f"layer_weights sum {_lw_sum:.4f} != 1.0; attribution may be skewed", stacklevel=2)

    # Prior children
    prior = scorecard.get("prior", {})
    prior_dims = prior.get("dimensions", {})
    prior_weights = prior.get("weights", {})
    prior_children = []
    for dim_name in ["economic_logic", "structure", "field_operator_support",
                     "data_compliance", "horizon_turnover_proxy",
                     "risk_control_proxy", "diversity", "explainability"]:
        dim_score = prior_dims.get(dim_name, 0)
        dim_weight = prior_weights.get(dim_name, 0)
        prior_children.append(AttributionNode(
            name=dim_name,
            score=dim_score,
            weight=dim_weight,
            contribution=dim_score * dim_weight,
            calibratable=True,
            explanation=dim_explanation(dim_name, dim_score),
        ))

    prior_node = AttributionNode(
        name="prior_score",
        score=prior.get("score", 0),
        weight=lw.get("prior", 0.30),
        contribution=prior.get("score", 0) * lw.get("prior", 0.30),
        children=prior_children,
        explanation=f"Source: {prior.get('source', '经验')}",
        calibratable=True,
    )

    # Empirical children
    empirical = scorecard.get("empirical", {})
    empirical_items = empirical.get("items", [])
    empirical_children = []
    for item in empirical_items:
        points = item.get("points", 0)
        empirical_children.append(AttributionNode(
            name=item["name"],
            score=item["points"] if item["passed"] else 0,
            weight=1.0,
            contribution=points if item["passed"] else 0,
            calibratable=False,
            explanation=f"{'PASS' if item['passed'] else 'FAIL'}: {item.get('actual')} {item.get('direction')} {item.get('target')}",
        ))

    empirical_node = AttributionNode(
        name="empirical_score",
        score=empirical.get("score", 0),
        weight=lw.get("empirical", 0.45),
        contribution=empirical.get("score", 0) * lw.get("empirical", 0.45),
        children=empirical_children,
        explanation=f"Status: {empirical.get('status', 'unknown')}",
        calibratable=False,
    )

    # Checklist children
    checklist = scorecard.get("submission_checklist", {})
    checklist_items = checklist.get("items", [])
    checklist_children = []
    for item in checklist_items:
        points = item.get("points", 0)
        checklist_children.append(AttributionNode(
            name=item["name"],
            score=points if item["passed"] else 0,
            weight=1.0,
            contribution=points if item["passed"] else 0,
            calibratable=False,
            explanation=item.get("meaning", ""),
        ))

    checklist_node = AttributionNode(
        name="submission_checklist",
        score=checklist.get("score", 0),
        weight=lw.get("checklist", 0.25),
        contribution=checklist.get("score", 0) * lw.get("checklist", 0.25),
        children=checklist_children,
        calibratable=False,
    )

    # Root
    return AttributionNode(
        name="total_score",
        # B-03/R4 S-04: defensive .get()
        score=scorecard.get("total_score", 0),
        weight=1.0,
        contribution=scorecard["total_score"],
        children=[prior_node, empirical_node, checklist_node],
        explanation=f"Decision: {scorecard.get('decision_band', 'unknown')}",
        calibratable=True,
    )
