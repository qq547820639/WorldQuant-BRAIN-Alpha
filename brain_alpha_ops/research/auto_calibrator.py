"""自动校准器 — 从官方回测记录中学习，最小化 prior 与 empirical 之间的误差。

读取 data/alpha_features.jsonl 中的 PASS 记录，对每个评分维度进行 grid search
优化参数，并调用 calibrate_weights.py 中的算法校准维度权重和层权重。

触发条件：积累 >= 20 个新 official_verified 样本后自动校准。

Usage::

    from brain_alpha_ops.research.auto_calibrator import AutoCalibrator

    calibrator = AutoCalibrator(storage_dir="data")
    if calibrator.needs_calibration():
        report = calibrator.calibrate()
        # report["calibrated"] == True 表示校准成功
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from brain_alpha_ops.jsonl import count_jsonl_records, read_jsonl_records
from brain_alpha_ops.research.scoring_params import DimensionParam, ScoringParams


# ═══════════════════════════════════════════════════════════════════════
# 自动校准器
# ═══════════════════════════════════════════════════════════════════════

class AutoCalibrator:
    """自动校准评分参数，最小化 prior 与 empirical 之间的误差。

    职责：
    1. 从 alpha_features.jsonl 读取官方回测记录
    2. 检测是否有足够新样本触发校准
    3. 对每个维度的可调参数做 grid search 优化
    4. 调用维度和层权重校准算法
    5. 持久化校准结果到 scoring_calibration.json

    P1-6: 校准样本量门禁
    - MIN_CALIBRATION_SAMPLES = 30（需 ≥ 30 条 BRAIN 官方 PASS 记录）
    - 不足时返回 calibrated=False + 详细诊断信息
    - pipeline 中产生 "校准推迟" 事件，不阻断主流程
    """

    # P1-6: 校准触发阈值 — 提高到 30 确保统计可靠性
    MIN_CALIBRATION_SAMPLES: int = 30
    CALIBRATION_HISTORY_LIMIT: int = 1000

    # 每个维度的 grid search 步长配置
    GRID_SEARCH_CONFIG: Dict[str, Dict[str, List[float]]] = {
        "structure": {
            "penalty_per_unit": [6.0, 7.0, 8.0, 9.0, 10.0],
            "penalty_threshold": [3.0, 4.0, 5.0],
            "base_score": [85.0, 90.0, 95.0],
            "floor": [15.0, 20.0, 25.0, 30.0],
        },
        "field_operator_support": {
            "base_score": [38.0, 42.0, 46.0],
            "bonus_per_unit": [6.0, 8.0, 10.0],
        },
        "horizon_turnover_proxy": {
            "threshold_low": [3.0, 5.0, 8.0],
            "threshold_high": [60.0, 90.0, 120.0],
            "score_in_range": [78.0, 82.0, 86.0],
            "score_out_range": [62.0, 68.0, 74.0],
            "score_no_data": [42.0, 50.0, 58.0],
        },
        "risk_control_proxy": {
            "tier_3_score": [80.0, 84.0, 88.0],
            "tier_2_score": [60.0, 66.0, 72.0],
            "tier_1_score": [42.0, 48.0, 54.0],
        },
        "diversity": {
            "high_score": [75.0, 80.0, 85.0],
            "low_score": [55.0, 60.0, 65.0, 70.0],
        },
        "explainability": {
            "threshold_high": [120.0, 140.0, 160.0],
            "score_in_range": [80.0, 85.0, 90.0],
            "score_out_range": [55.0, 60.0, 65.0],
        },
        "data_compliance": {
            "high_score": [78.0, 82.0, 86.0],
            "low_score": [25.0, 30.0, 35.0, 40.0],
        },
    }

    def __init__(self, storage_dir: str = "data"):
        self._storage_dir = storage_dir
        self._params: Optional[ScoringParams] = None
        self._last_calibrated_count: int = 0
        self._load_existing()

    # ── 公开 API ──

    def needs_calibration(self) -> bool:
        """检查是否有足够新样本触发校准。

        条件：alpha_features.jsonl 中 PASS 记录数 >= MIN_CALIBRATION_SAMPLES，
        且自上次校准后新增 >= MIN_CALIBRATION_SAMPLES 个 PASS 记录。
        """
        passing_count = self._count_passing_records()
        new_since_last = passing_count - self._last_calibrated_count
        return passing_count >= self.MIN_CALIBRATION_SAMPLES and new_since_last >= self.MIN_CALIBRATION_SAMPLES

    def calibrate(self) -> Dict[str, Any]:
        """执行完整校准流程。

        1. 加载 baseline（默认参数）
        2. 加载 PASS 记录
        3. 对每个维度做 grid search 优化参数
        4. 调用维度权重校准
        5. 调用层权重校准
        6. 持久化结果

        返回校准报告 dict。
        """
        baseline = ScoringParams.defaults()
        total_pass_records = self._count_passing_records()
        records = self._load_passing_records(limit=self.CALIBRATION_HISTORY_LIMIT)

        if total_pass_records < self.MIN_CALIBRATION_SAMPLES:
            deficit = self.MIN_CALIBRATION_SAMPLES - total_pass_records
            return {
                "calibrated": False,
                "status": "insufficient_samples",
                "error": f"insufficient samples: {total_pass_records} < {self.MIN_CALIBRATION_SAMPLES}",
                "sample_size": len(records),
                "total_pass_records": total_pass_records,
                "required": self.MIN_CALIBRATION_SAMPLES,
                "deficit": deficit,
                "summary": (
                    f"Calibration deferred: {total_pass_records} PASS records available, "
                    f"need {deficit} more (minimum {self.MIN_CALIBRATION_SAMPLES}). "
                    f"Using default/experience weights until threshold is met."
                ),
            }

        # 对每个可校准维度做 grid search
        optimized_dims = {}
        dim_reports = {}
        for dim_name, grid_config in self.GRID_SEARCH_CONFIG.items():
            if dim_name not in baseline.dimensions:
                continue
            base_dim = baseline.dimensions[dim_name]
            best_dim, best_mae = self._grid_search_dimension(
                dim_name, base_dim, grid_config, records
            )
            optimized_dims[dim_name] = best_dim
            dim_reports[dim_name] = {
                "original_mae": self._compute_mae(dim_name, base_dim, records),
                "optimized_mae": best_mae,
                "improvement": round(
                    self._compute_mae(dim_name, base_dim, records) - best_mae, 2
                ),
            }

        # 复制未优化维度
        for dim_name, dim in baseline.dimensions.items():
            if dim_name not in optimized_dims:
                optimized_dims[dim_name] = dim

        # 校准维度权重
        dim_weight_report = self._calibrate_dimension_weights(records)

        # 校准层权重
        layer_weight_report = self._calibrate_layer_weights(records)

        # 构建最终参数
        params = ScoringParams(
            dimensions=optimized_dims,
            layer_weights=layer_weight_report.get("optimized_weights", baseline.layer_weights),
            calibrated_at=datetime.now(timezone.utc).isoformat(),
        )

        # 更新维度权重
        if "optimized_weights" in dim_weight_report:
            for dim_name, weight in dim_weight_report["optimized_weights"].items():
                if dim_name in params.dimensions:
                    params.dimensions[dim_name].weight = weight

        # 计算整体质量
        overall_mae = self._compute_overall_mae(params, records)
        baseline_mae = self._compute_overall_mae(baseline, records)
        params.calibration_quality = {
            "r_squared": dim_weight_report.get("r_squared", 0.0),
            "mean_abs_error": round(overall_mae, 2),
            "sample_size": len(records),
            "total_pass_records": total_pass_records,
            "calibration_history_limit": self.CALIBRATION_HISTORY_LIMIT,
            "baseline_mae": round(baseline_mae, 2),
            "improvement_pct": round((baseline_mae - overall_mae) / max(baseline_mae, 0.01) * 100, 1),
        }

        # 持久化
        params.save(self._storage_dir)
        self._params = params
        self._last_calibrated_count = total_pass_records

        return {
            "calibrated": True,
            "sample_size": len(records),
            "total_pass_records": total_pass_records,
            "calibration_history_limit": self.CALIBRATION_HISTORY_LIMIT,
            "calibrated_at": params.calibrated_at,
            "calibration_quality": params.calibration_quality,
            "dimension_reports": dim_reports,
            "dimension_weights": dim_weight_report,
            "layer_weights": layer_weight_report,
            "summary": (
                f"Calibrated with {len(records)} records. "
                f"Overall MAE: {baseline_mae:.1f} → {overall_mae:.1f} "
                f"({params.calibration_quality['improvement_pct']:.1f}% improvement). "
                f"R²={params.calibration_quality['r_squared']:.4f}."
            ),
        }

    def apply(self, scoring_config: Any) -> Any:
        """将校准结果应用到 ScoringConfig。

        如果暂无校准结果，使用默认参数。

        Args:
            scoring_config: ScoringConfig 实例

        Returns:
            修改后的 scoring_config（原地修改）
        """
        params = self._params or ScoringParams.defaults()
        scoring_config.prior_weights_override = params.get_weights_override()
        scoring_config.prior_layer_weight = params.layer_weights.get("prior", 0.30)
        scoring_config.empirical_layer_weight = params.layer_weights.get("empirical", 0.45)
        scoring_config.checklist_layer_weight = params.layer_weights.get("checklist", 0.25)
        return scoring_config

    @property
    def params(self) -> ScoringParams:
        """获取当前校准参数。未校准时返回默认值。"""
        return self._params or ScoringParams.defaults()

    # ── 内部方法 ──

    def _load_existing(self) -> None:
        """加载已有校准文件。"""
        self._params = ScoringParams.load(self._storage_dir)
        if self._params:
            quality = self._params.calibration_quality
            self._last_calibrated_count = int(quality.get("total_pass_records") or quality.get("sample_size") or 0)

    def _load_passing_records(self, *, limit: int | None = CALIBRATION_HISTORY_LIMIT) -> List[Dict[str, Any]]:
        """Load recent PASS records used as the calibration sample."""
        filepath = os.path.join(self._storage_dir, "alpha_features.jsonl")
        if not os.path.exists(filepath):
            return []

        return [
            record
            for record in read_jsonl_records(filepath, limit=limit)
            if record.get("pass_fail") == "PASS"
        ]

    def _count_passing_records(self) -> int:
        filepath = os.path.join(self._storage_dir, "alpha_features.jsonl")
        if not os.path.exists(filepath):
            return 0
        return count_jsonl_records(filepath, predicate=lambda record: record.get("pass_fail") == "PASS")

    def _compute_prior_for_record(
        self, record: Dict[str, Any], dim: DimensionParam, dim_name: str
    ) -> float:
        """对单条记录计算某个维度的参数化先验分数。"""
        fields = set(record.get("field_set", []))
        operators = list(record.get("operator_set", []))
        expression = record.get("expression", "")
        hypothesis = record.get("hypothesis", "")
        family = record.get("family", "")

        import re
        windows = [int(v) for v in re.findall(r"\b\d+\b", expression)]
        median_window = sorted(windows)[len(windows) // 2] if windows else 0

        if dim_name == "structure":
            return max(dim.floor, dim.base_score - max(0, len(operators) - dim.penalty_threshold) * dim.penalty_per_unit)

        elif dim_name == "field_operator_support":
            score = dim.base_score + len(fields) * dim.bonus_per_unit + len(set(operators)) * 4
            return min(dim.cap, max(dim.floor, score))

        elif dim_name == "data_compliance":
            return dim.high_score if fields else dim.low_score

        elif dim_name == "horizon_turnover_proxy":
            if not median_window:
                return dim.score_no_data
            if dim.threshold_low <= median_window <= dim.threshold_high:
                return dim.score_in_range
            return dim.score_out_range

        elif dim_name == "risk_control_proxy":
            has_cs = any(op in operators for op in ("rank", "zscore", "scale", "group_rank", "group_zscore"))
            has_ts = any(op.startswith("ts_") for op in operators)
            has_rc = any(op in operators for op in ("winsorize", "zscore", "scale", "group_rank")) or "adv20" in fields
            conditions = sum([has_cs, has_ts, has_rc])
            if conditions >= 3:
                return dim.tier_3_score
            elif conditions >= 2:
                return dim.tier_2_score
            return dim.tier_1_score

        elif dim_name == "diversity":
            high_set = set(dim.high_value_set or [])
            return dim.high_score if family in high_set else dim.low_score

        elif dim_name == "explainability":
            return dim.score_in_range if len(expression) < dim.threshold_high else dim.score_out_range

        elif dim_name == "economic_logic":
            text = f"{hypothesis} {expression} {' '.join(fields)} {' '.join(operators)}".lower()
            concepts = {
                "momentum": ["momentum", "trend", "ts_delta", "ts_rank", "ts_mean", "moving_average", "breakout", "continuation"],
                "mean_reversion": ["reversal", "mean_revert", "zscore", "ts_zscore", "overbought", "oversold", "bounce", "revert"],
                "value": ["value", "cheap", "undervalue", "pe_ratio", "pb_ratio", "market_cap", "book", "dividend_yield", "earnings_yield"],
                "quality": ["quality", "profit", "margin", "roe", "roa", "stable", "fundamental", "balance_sheet"],
                "volatility": ["volatility", "vol", "ts_std", "std", "ivol", "beta", "risk", "variance", "uncertainty"],
                "liquidity": ["liquidity", "volume", "turn", "adv", "vwap", "bid", "spread", "depth", "market_impact"],
                "growth": ["growth", "earnings", "revenue", "sales_growth", "expansion", "accelerat"],
                "risk_management": ["winsorize", "truncation", "neutralize", "group_neutralize", "hedge", "sector_neutral", "risk_adjust"],
                "cross_sectional": ["cross_section", "rank", "group_rank", "sector", "industry", "subindustry", "relative", "peer"],
            }
            detected = sum(1 for kw_list in concepts.values() if any(kw in text for kw in kw_list))
            if detected == 0:
                if len(hypothesis) >= dim.fallback_length_threshold:
                    return dim.fallback_length_score
                return dim.fallback_insufficient_score
            if dim.concept_scores:
                return dim.concept_scores.get(detected, dim.concept_scores.get(max(dim.concept_scores.keys(), default=68), 68))
            return 68 if detected == 1 else (78 if detected == 2 else (85 if detected == 3 else 92))

        return 50.0  # 未知维度默认分数

    def _compute_full_prior(self, params: ScoringParams, record: Dict[str, Any]) -> float:
        """计算完整 prior_score（加权 8 维）。"""
        total = 0.0
        total_weight = 0.0
        for dim_name, dim in params.dimensions.items():
            if not dim.enabled:
                continue
            dim_score = self._compute_prior_for_record(record, dim, dim_name)
            total += dim_score * dim.weight
            total_weight += dim.weight
        return total / max(total_weight, 0.01)

    def _compute_mae(
        self, dim_name: str, dim: DimensionParam,
        records: List[Dict[str, Any]]
    ) -> float:
        """计算单个维度 prior 与 empirical 之间的 MAE。"""
        errors = []
        for record in records:
            prior = self._compute_prior_for_record(record, dim, dim_name)
            empirical = record.get("sharpe", 0) * 50
            empirical = min(100, max(0, empirical))
            errors.append(abs(prior - empirical))
        return sum(errors) / max(len(errors), 1)

    def _compute_overall_mae(
        self, params: ScoringParams, records: List[Dict[str, Any]]
    ) -> float:
        """计算整体 prior_score 与 empirical 之间的 MAE。"""
        errors = []
        for record in records:
            prior = self._compute_full_prior(params, record)
            empirical = min(100, max(0, record.get("sharpe", 0) * 50))
            errors.append(abs(prior - empirical))
        return sum(errors) / max(len(errors), 1)

    def _grid_search_dimension(
        self,
        dim_name: str,
        base_dim: DimensionParam,
        grid_config: Dict[str, List[float]],
        records: List[Dict[str, Any]],
    ) -> Tuple[DimensionParam, float]:
        """对单个维度的可调参数做 grid search。

        Returns:
            (最优 DimensionParam, 最优 MAE)
        """
        best_dim = base_dim
        best_mae = self._compute_mae(dim_name, base_dim, records)

        # 生成所有参数组合
        param_names = list(grid_config.keys())
        combinations = self._generate_grid_combinations(grid_config)

        for combo in combinations:
            test_dim = DimensionParam(
                name=dim_name,
                weight=base_dim.weight,
                enabled=base_dim.enabled,
                **{k: base_dim.__dict__.get(k, 0) for k in base_dim.__dict__},
            )
            for i, name in enumerate(param_names):
                setattr(test_dim, name, combo[i])

            mae = self._compute_mae(dim_name, test_dim, records)
            if mae < best_mae:
                best_mae = mae
                best_dim = test_dim

        return best_dim, best_mae

    @staticmethod
    def _generate_grid_combinations(
        grid_config: Dict[str, List[float]]
    ) -> List[Tuple[float, ...]]:
        """生成 grid search 参数组合（笛卡尔积）。"""
        keys = list(grid_config.keys())
        if not keys:
            return [()]

        result = [(v,) for v in grid_config[keys[0]]]
        for key in keys[1:]:
            new_result = []
            for combo in result:
                for v in grid_config[key]:
                    new_result.append(combo + (v,))
            result = new_result
        return result

    # ── 权重校准 ──

    def _calibrate_dimension_weights(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """使用 Pearson 相关法校准 8 维权重。

        数据格式兼容 calibrate_weights.py:calibrate_prior_weights()。
        """
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        try:
            from calibrate_weights import calibrate_prior_weights as _calib_fn
            return _calib_fn(records, target_metric="sharpe")
        except ImportError:
            return {
                "sample_size": len(records),
                "error": "calibrate_weights module not importable",
            }

    def _calibrate_layer_weights(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """使用 grid search 法校准三层权重。

        数据格式兼容 calibrate_weights.py:calibrate_scorecard_weights()。
        """
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        try:
            from calibrate_weights import calibrate_scorecard_weights as _calib_fn
            return _calib_fn(records)
        except ImportError:
            return {
                "sample_size": len(records),
                "error": "calibrate_weights module not importable",
            }
