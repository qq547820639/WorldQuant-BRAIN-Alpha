"""可参数化的先验评分系统 — 评分维度参数定义、持久化与校准接口。

将 scoring.py prior_score() 的 8 维硬编码公式重构为可调参数驱动的评分函数。
每维参数通过 JSON 持久化到 data/scoring_calibration.json，支持 AutoCalibrator 自动校准。

Usage::

    from brain_alpha_ops.research.scoring_params import ScoringParams

    # 默认参数（与当前硬编码行为一致）
    params = ScoringParams.defaults()

    # 从校准文件加载
    params = ScoringParams.load("data")

    # 持久化
    params.save("data")

    # 应用到 prior_score
    from brain_alpha_ops.research.scoring import prior_score
    result = prior_score(candidate, params=params)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DimensionParam:
    """单个评分维度的可调参数。

    不同类型的维度使用参数的不同子集：
    - 线性惩罚型（structure, field_operator_support）: base_score, penalty_per_unit, penalty_threshold, floor, cap
    - 阈值型（horizon_turnover_proxy）: threshold_low, threshold_high, score_in_range, score_out_range, score_no_data
    - 分类型（diversity, data_compliance, explainability, risk_control_proxy）: high_value_set, high_score, low_score
    - 关键词型（economic_logic）: concept_scores 字典
    """
    name: str                                    # 维度名，如 "structure"
    enabled: bool = True                         # 是否启用此维度
    weight: float = 0.12                         # 在 prior_score 中的权重

    # ── 通用 ──
    floor: float = 0.0                           # 分数下限
    cap: float = 100.0                           # 分数上限

    # ── 线性惩罚型参数 ──
    base_score: float = 90.0                     # 基础分
    penalty_per_unit: float = 8.0                # 每超一单位的扣分
    penalty_threshold: float = 4.0               # 惩罚起点（超过此值开始扣分）
    bonus_per_unit: float = 0.0                  # 单位加分（field_operator_support 等正向维度）
    bonus_base: float = 0.0                      # 加分基础值

    # ── 阈值型参数 ──
    threshold_low: float = 0.0                   # 窗口下界
    threshold_high: float = 0.0                  # 窗口上界
    score_in_range: float = 82.0                 # 窗口在范围内得分
    score_out_range: float = 68.0                # 窗口在范围外得分
    score_no_data: float = 50.0                  # 无数据得分

    # ── 分类型参数 ──
    high_value_set: Optional[List[str]] = None   # 高分值集合
    high_score: float = 80.0                     # 匹配高分值时的得分
    low_score: float = 60.0                      # 不匹配时的得分

    # ── 多条件型 (risk_control_proxy) ──
    tier_3_score: float = 84.0                   # 三个条件都满足
    tier_2_score: float = 66.0                   # 两个条件满足
    tier_1_score: float = 48.0                   # 一个或零个条件

    # ── 关键词型 (economic_logic) ──
    concept_scores: Optional[Dict[int, int]] = None  # {concept_count: score}
    fallback_length_threshold: int = 60           # 兜底 hypothesis 长度阈值
    fallback_length_score: int = 52               # 兜底长度满足时的得分
    fallback_insufficient_score: int = 40         # 兜底不满足时的得分


@dataclass
class ScoringParams:
    """完整的可校准评分参数集。

    包含 8 个维度的 DimensionParam + 三层权重 + 元数据。
    """
    schema_version: str = "scoring_calibration-v1.0"
    dimensions: Dict[str, DimensionParam] = field(default_factory=dict)
    layer_weights: Dict[str, float] = field(default_factory=lambda: {
        "prior": 0.30, "empirical": 0.45, "checklist": 0.25
    })
    calibration_quality: Dict[str, float] = field(default_factory=lambda: {
        "r_squared": 0.0, "mean_abs_error": 0.0, "sample_size": 0
    })
    calibrated_at: str = ""

    @classmethod
    def defaults(cls) -> "ScoringParams":
        """返回与当前硬编码先验评分 100% 一致的默认参数。"""
        dims = {}

        # ── 1. economic_logic：关键词概念检测 ──
        dims["economic_logic"] = DimensionParam(
            name="economic_logic",
            weight=0.18,
            floor=40.0, cap=92.0,
            concept_scores={4: 92, 3: 85, 2: 78, 1: 68},
            fallback_length_threshold=60,
            fallback_length_score=52,
            fallback_insufficient_score=40,
        )

        # ── 2. structure：算子数量线性惩罚 ──
        # 原公式: max(25, 90 - max(0, len(operators) - 4) * 8)
        dims["structure"] = DimensionParam(
            name="structure",
            weight=0.14,
            floor=25.0, cap=90.0,
            base_score=90.0,
            penalty_per_unit=8.0,
            penalty_threshold=4.0,
        )

        # ── 3. field_operator_support：字段和算子加分配置 ──
        # 原公式: min(92, 42 + len(fields) * 8 + len(set(operators)) * 4)
        dims["field_operator_support"] = DimensionParam(
            name="field_operator_support",
            weight=0.16,
            floor=42.0, cap=92.0,
            base_score=42.0,
            bonus_per_unit=8.0,  # 字段加分
            # 算子加分在评分时单独处理（4分/算子）
        )

        # ── 4. data_compliance：二值化 ──
        # 原公式: 82 if fields else 35
        dims["data_compliance"] = DimensionParam(
            name="data_compliance",
            weight=0.12,
            high_score=82.0,
            low_score=35.0,
        )

        # ── 5. horizon_turnover_proxy：窗口阈值 ──
        # 原公式: 82 if 5 <= median_window <= 90 else 68 if median_window else 50
        dims["horizon_turnover_proxy"] = DimensionParam(
            name="horizon_turnover_proxy",
            weight=0.14,
            threshold_low=5.0,
            threshold_high=90.0,
            score_in_range=82.0,
            score_out_range=68.0,
            score_no_data=50.0,
        )

        # ── 6. risk_control_proxy：三条件分层 ──
        # 原公式: 84 if has_cs and has_ts and has_rc else 66 if has_cs and has_ts else 48
        dims["risk_control_proxy"] = DimensionParam(
            name="risk_control_proxy",
            weight=0.14,
            tier_3_score=84.0,
            tier_2_score=66.0,
            tier_1_score=48.0,
        )

        # ── 7. diversity：分类匹配 ──
        # 原公式: 80 if family in {"Liquidity", "Volatility", "Hybrid"} else 65
        dims["diversity"] = DimensionParam(
            name="diversity",
            weight=0.07,
            high_value_set=["Liquidity", "Volatility", "Hybrid"],
            high_score=80.0,
            low_score=65.0,
        )

        # ── 8. explainability：表达式长度 ──
        # 原公式: 85 if len(expression) < 140 else 60
        dims["explainability"] = DimensionParam(
            name="explainability",
            weight=0.05,
            threshold_high=140.0,
            score_in_range=85.0,
            score_out_range=60.0,
        )

        return cls(dimensions=dims)

    # ── 持久化 ──

    def save(self, storage_dir: str = "data") -> str:
        """持久化到 data/scoring_calibration.json。"""
        os.makedirs(storage_dir, exist_ok=True)
        filepath = os.path.join(storage_dir, "scoring_calibration.json")
        data = {
            "schema_version": self.schema_version,
            "calibrated_at": self.calibrated_at,
            "layer_weights": self.layer_weights,
            "calibration_quality": self.calibration_quality,
            "dimensions": {
                name: _dimension_to_dict(d) for name, d in self.dimensions.items()
            },
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return filepath

    @classmethod
    def load(cls, storage_dir: str = "data") -> Optional["ScoringParams"]:
        """从 data/scoring_calibration.json 加载参数。文件不存在返回 None。"""
        filepath = os.path.join(storage_dir, "scoring_calibration.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        dims = {}
        for name, d in data.get("dimensions", {}).items():
            dims[name] = _dimension_from_dict(d)
            dims[name].name = name  # 确保 name 与 key 一致

        return cls(
            schema_version=data.get("schema_version", "scoring_calibration-v1.0"),
            dimensions=dims,
            layer_weights=data.get("layer_weights", {"prior": 0.30, "empirical": 0.45, "checklist": 0.25}),
            calibration_quality=data.get("calibration_quality", {"r_squared": 0.0, "mean_abs_error": 0.0, "sample_size": 0}),
            calibrated_at=data.get("calibrated_at", ""),
        )

    def get_weights_override(self) -> Dict[str, float]:
        """提取维度权重字典，可直接作为 prior_score 的 weights_override。"""
        return {name: d.weight for name, d in self.dimensions.items() if d.enabled}

    def get_layer_weights(self) -> Dict[str, float]:
        """提取三层权重字典。"""
        return dict(self.layer_weights)

    def get_dimension(self, name: str) -> Optional[DimensionParam]:
        """获取单个维度参数。"""
        return self.dimensions.get(name)


# ── 序列化辅助 ──

def _dimension_to_dict(d: DimensionParam) -> Dict[str, Any]:
    """将 DimensionParam 转换为可 JSON 序列化的 dict。"""
    result = asdict(d)
    # 清理不需要持久化的字段
    result.pop("name", None)
    return result


def _dimension_from_dict(d: Dict[str, Any]) -> DimensionParam:
    """从 dict 恢复 DimensionParam。处理可能缺失的字段用默认值。"""
    return DimensionParam(
        name=d.get("name", ""),
        enabled=d.get("enabled", True),
        weight=d.get("weight", 0.12),
        floor=d.get("floor", 0.0),
        cap=d.get("cap", 100.0),
        base_score=d.get("base_score", 90.0),
        penalty_per_unit=d.get("penalty_per_unit", 8.0),
        penalty_threshold=d.get("penalty_threshold", 4.0),
        bonus_per_unit=d.get("bonus_per_unit", 0.0),
        bonus_base=d.get("bonus_base", 0.0),
        threshold_low=d.get("threshold_low", 0.0),
        threshold_high=d.get("threshold_high", 0.0),
        score_in_range=d.get("score_in_range", 82.0),
        score_out_range=d.get("score_out_range", 68.0),
        score_no_data=d.get("score_no_data", 50.0),
        high_value_set=d.get("high_value_set"),
        high_score=d.get("high_score", 80.0),
        low_score=d.get("low_score", 60.0),
        tier_3_score=d.get("tier_3_score", 84.0),
        tier_2_score=d.get("tier_2_score", 66.0),
        tier_1_score=d.get("tier_1_score", 48.0),
        concept_scores=d.get("concept_scores"),
        fallback_length_threshold=d.get("fallback_length_threshold", 60),
        fallback_length_score=d.get("fallback_length_score", 52),
        fallback_insufficient_score=d.get("fallback_insufficient_score", 40),
    )
