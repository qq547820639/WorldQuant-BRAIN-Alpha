"""定向迭代优化器 — 基于诊断信息应用变异算子，实现有方向的 alpha 改进。

将原 v2.1 的"停滞→切换策略"进化为基于失败维度的定向变异：
- sharpe/fitness 低 → field_swap + window_perturb
- correlation 高   → field_swap_semantic + operator_substitute
- turnover 高      → longer_window + structure_refine
- concentration 高 → structure_refine

每类变异算子均可独立调用，optimize() 方法自动根据诊断结果排序变异。

接入了 OfficialDataLoader + FieldDatasetMapper 以支持语义级别的字段/算子替换。

Usage::

    from brain_alpha_ops.research.iterative_optimizer import IterativeOptimizer

    optimizer = IterativeOptimizer(loader, mapper)
    mutations = optimizer.optimize(candidate, diagnosis)
    for mut in mutations:
        print(f"Mode: {mut.mode}, Reason: {mut.reason}")
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from brain_alpha_ops.data.loader import OfficialDataLoader
from brain_alpha_ops.data.field_dataset_mapper import FieldDatasetMapper
from brain_alpha_ops.models import Candidate


# ═══════════════════════════════════════════════════════════════════════
# 算子功能分组 — 基于 BRAIN 算子语义
# ═══════════════════════════════════════════════════════════════════════

_OPERATOR_FAMILIES: Dict[str, List[str]] = {
    "ranking":       ["ts_rank", "rank", "group_rank"],
    "standardization": ["zscore", "scale", "group_zscore"],
    "moving_average":  ["ts_mean", "ts_sum", "ts_product", "ts_arg_max", "ts_arg_min"],
    "difference":      ["ts_delta", "ts_av_diff"],
    "volatility":      ["ts_std_dev", "ts_skewness", "ts_kurtosis"],
    "correlation":     ["ts_corr", "ts_covariance"],
    "winsorization":   ["winsorize"],
    "decay":           ["ts_decay_linear"],
    "step":            ["ts_step"],
    "minmax":          ["ts_min", "ts_max"],
}

# 每个家族的备选算子（用于 operator_substitute）
_FAMILY_ALTERNATIVES: Dict[str, List[str]] = {}
for _family, _ops in _OPERATOR_FAMILIES.items():
    for _op in _ops:
        _FAMILY_ALTERNATIVES[_op] = [o for o in _ops if o != _op]

_STRUCTURE_WRAPS: List[str] = ["winsorize", "zscore", "scale"]


# ═══════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MutationResult:
    """单次变异结果。"""
    expression: str
    mode: str                        # field_swap | window_perturb | structure_refine | operator_substitute
    reason: str                      # 为什么选择这个变异
    parent_failure: str              # 原始失败维度
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# 定向迭代优化器
# ═══════════════════════════════════════════════════════════════════════

class IterativeOptimizer:
    """基于诊断信息的定向优化器。

    将 diagnostics.diagnose() 的输出转化为定向变异操作，
    优先修复最严重的失败维度。
    """

    # 失败维度 → 变异策略映射
    _FAILURE_TO_STRATEGY: Dict[str, List[str]] = {
        "sharpe":              ["field_swap", "window_perturb", "structure_refine"],
        "fitness":             ["field_swap", "structure_refine", "operator_substitute"],
        "correlation":         ["field_swap_semantic", "operator_substitute", "structure_refine"],
        "turnover_platform":   ["longer_window", "structure_refine"],
        "turnover_quality":    ["longer_window", "structure_refine"],
        "turnover_low":        ["window_perturb", "field_swap"],
        "concentration":       ["structure_refine", "field_swap"],
        "margin":              ["structure_refine", "operator_substitute"],
        "sub_universe_sharpe": ["structure_refine", "field_swap"],
        "gate":                ["structure_refine", "field_swap"],
    }

    def __init__(
        self,
        loader: Optional[OfficialDataLoader] = None,
        mapper: Optional[FieldDatasetMapper] = None,
    ):
        self._loader = loader or OfficialDataLoader.instance()
        self._mapper = mapper

    # ── 主入口 ──

    def optimize(
        self,
        candidate: Candidate,
        diagnosis: Dict[str, Any],
        max_mutations: int = 4,
    ) -> List[MutationResult]:
        """根据诊断结果生成定向变异序列。

        按失败维度的严重程度排序（最差指标优先），每个失败维度尝试生成
        其对应策略列表中第一个可执行的变异。

        Args:
            candidate: 待优化的候选 alpha
            diagnosis: diagnostics.diagnose() 的输出
            max_mutations: 最大变异数量

        Returns:
            MutationResult 列表（可能少于 max_mutations）
        """
        expression = candidate.expression or ""
        fields = candidate.data_fields or []
        dataset_id = getattr(candidate, "dataset_id", "") or ""

        results: List[MutationResult] = []
        attempted_modes: Set[str] = set()

        failed_dims = diagnosis.get("failed_dimensions", [])
        suggested_mutations = diagnosis.get("suggested_mutations", [])

        # 优先使用 suggested_mutations 中的 mode（如果不冲突）
        suggested_modes = {m["mutation_mode"] for m in suggested_mutations}

        for dim in failed_dims:
            if len(results) >= max_mutations:
                break

            strategies = self._FAILURE_TO_STRATEGY.get(dim, ["field_swap", "structure_refine"])
            for strategy in strategies:
                if len(results) >= max_mutations:
                    break
                if strategy in attempted_modes:
                    continue

                mut = self._apply_strategy(strategy, expression, fields, dataset_id, dim)
                if mut and mut.expression != expression:
                    results.append(mut)
                    attempted_modes.add(strategy)

        # 如果没有成功生成任何变异，尝试通用的 structure_refine
        if not results and "structure_refine" not in attempted_modes:
            mut = self._apply_strategy("structure_refine", expression, fields, dataset_id, "general")
            if mut and mut.expression != expression:
                results.append(mut)

        return results

    def _apply_strategy(
        self, strategy: str, expression: str, fields: List[str],
        dataset_id: str, failure_dim: str,
    ) -> Optional[MutationResult]:
        """执行单个策略，返回 MutationResult 或 None。"""
        try:
            if strategy == "field_swap":
                new_expr = self.field_swap(expression, fields, dataset_id)
                return MutationResult(
                    expression=new_expr, mode="field_swap",
                    reason=f"Field swap to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "field_swap_semantic":
                new_expr = self.field_swap_semantic(expression, dataset_id)
                return MutationResult(
                    expression=new_expr, mode="field_swap_semantic",
                    reason=f"Semantic field swap to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "window_perturb":
                new_expr = self.window_perturb(expression)
                return MutationResult(
                    expression=new_expr, mode="window_perturb",
                    reason=f"Window perturb to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "longer_window":
                new_expr = self.window_perturb(expression, factor=2.0)
                return MutationResult(
                    expression=new_expr, mode="longer_window",
                    reason=f"Longer window to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "structure_refine":
                new_expr = self.structure_refine(expression)
                return MutationResult(
                    expression=new_expr, mode="structure_refine",
                    reason=f"Structure refine to address {failure_dim}",
                    parent_failure=failure_dim,
                )

            elif strategy == "operator_substitute":
                new_expr = self.operator_substitute(expression)
                return MutationResult(
                    expression=new_expr, mode="operator_substitute",
                    reason=f"Operator substitute to address {failure_dim}",
                    parent_failure=failure_dim,
                )
        except Exception:
            pass
        return None

    # ── 变异算子 ──

    def field_swap(
        self, expression: str, fields: List[str], dataset_id: str = ""
    ) -> str:
        """同类别字段替换：用当前 dataset 中的其他字段替换表达式中的字段。

        优先选择同一 dataset 的字段；若 mapper 不可用，则在 fields 列表中轮换。
        """
        if not fields or len(fields) < 2:
            return expression

        # 尝试通过 mapper 获取同 dataset 的替代字段
        if self._mapper and dataset_id:
            dataset_fields = self._mapper.fields_for(dataset_id)
            if dataset_fields and len(dataset_fields) > 1:
                alt_pool = [f for f in dataset_fields if f not in fields]
                if not alt_pool:
                    alt_pool = dataset_fields
            else:
                alt_pool = fields
        else:
            alt_pool = fields

        # 替换表达式中的 1-2 个字段
        target = random.choice(fields) if fields else ""
        if not target or target not in expression:
            return expression

        replacement = random.choice([f for f in alt_pool if f != target])
        return self._safe_replace_token(expression, target, replacement)

    def field_swap_semantic(self, expression: str, dataset_id: str = "") -> str:
        """语义级字段替换：替换表达式中的字段为同类别字段。

        通过 FieldDatasetMapper 查找同 dataset 且最接近的类别字段。
        """
        field_tokens = re.findall(r"\b([a-zA-Z_]\w*)\b", expression)
        # 过滤出可能是字段名的 token（排除算子名和数字）
        operator_names = {op for family in _OPERATOR_FAMILIES.values() for op in family}
        candidate_fields = [
            t for t in field_tokens
            if t not in operator_names and not t.isdigit()
            and len(t) > 1 and "_" in t
        ]

        if not candidate_fields:
            return expression

        target = random.choice(candidate_fields)
        if self._mapper and dataset_id:
            replacements = self._mapper.fields_for(dataset_id)
            if replacements:
                replacement = random.choice([f for f in replacements if f != target])
                return self._safe_replace_token(expression, target, replacement)

        return expression

    def window_perturb(self, expression: str, factor: float = 0.2) -> str:
        """窗口 ±factor 扰动。

        对表达式中的所有数字做随机 ±random()*factor*value 的扰动，
        结果限制在 [3, 252] 范围内（BRAIN 合理窗口范围）。
        """
        def _perturb(m: re.Match) -> str:
            val = int(m.group(0))
            if val < 2 or val > 1000:  # 非窗口值的数字（如分子分母系数）
                return m.group(0)
            delta = random.uniform(-factor, factor) * val
            new_val = int(val + delta)
            new_val = max(3, min(252, new_val))
            return str(new_val)

        return re.sub(r"\b\d+\b", _perturb, expression)

    def structure_refine(self, expression: str) -> str:
        """增加/移除标准化层。

        50% 概率增加一个标准化包裹（winsorize/zscore/scale），
        50% 概率移除最外层包裹（如果存在）。
        """
        if random.random() < 0.5:
            # 增加包裹
            wrap = random.choice(_STRUCTURE_WRAPS)
            # 检查是否已包裹
            stripped = expression.strip()
            for existing_wrap in _STRUCTURE_WRAPS:
                if stripped.startswith(f"{existing_wrap}(") and stripped.endswith(")"):
                    return expression  # 已被包裹，不重复包裹
            # winsorize 和 truncation 需要 std 参数
            if wrap in ("winsorize", "truncation"):
                return f"{wrap}({expression}, std=4)"
            return f"{wrap}({expression})"
        else:
            # 移除最外层包裹
            stripped = expression.strip()
            for existing_wrap in _STRUCTURE_WRAPS:
                prefix = f"{existing_wrap}("
                if stripped.startswith(prefix) and stripped.endswith(")"):
                    inner = stripped[len(prefix):-1]
                    # 处理带参数的情况如 winsorize(expr, std=4)
                    if "," in inner:
                        # 取第一个逗号之前的内容直到匹配括号
                        inner = inner[:inner.rfind(",")].strip()
                    return inner if inner else expression
            return expression

    def operator_substitute(self, expression: str) -> str:
        """同功能算子替换。

        识别表达式中的算子，找到其所属家族，替换为同家族的另一个算子。
        """
        # 提取所有算子名
        op_pattern = re.findall(r"\b([a-zA-Z_]\w*)\s*\(", expression)
        known_ops = set(_FAMILY_ALTERNATIVES.keys())

        substituted = False
        result = expression

        for op in op_pattern:
            if op in known_ops and op in _FAMILY_ALTERNATIVES:
                alternatives = _FAMILY_ALTERNATIVES[op]
                if alternatives:
                    replacement = random.choice(alternatives)
                    # 安全替换（作为完整 token，不作为子字符串）
                    result = self._safe_replace_token(result, op, replacement)
                    substituted = True
                    break  # 一次只替换一个算子

        return result if substituted else expression

    # ── 辅助 ──

    @staticmethod
    def _safe_replace_token(text: str, old: str, new: str) -> str:
        """安全替换 token（确保 old 是完整单词，不是子串）。"""
        # 使用单词边界匹配
        pattern = r"\b" + re.escape(old) + r"\b"
        if not re.search(pattern, text):
            return text
        return re.sub(pattern, new, text, count=1)


# ═══════════════════════════════════════════════════════════════════════
# 独立工具函数（兼容现有 mutate_expression 调用）
# ═══════════════════════════════════════════════════════════════════════

_DEFAULT_WINDOWS = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]


def window_perturb_expression(expression: str, factor: float = 0.2) -> str:
    """独立窗口扰动函数（可直接替代 mutate_expression mode='window_perturb'）。"""
    opt = IterativeOptimizer()
    return opt.window_perturb(expression, factor)


def operator_substitute_expression(expression: str) -> str:
    """独立算子替换函数（可直接替代 mutate_expression mode='operator_substitute'）。"""
    opt = IterativeOptimizer()
    return opt.operator_substitute(expression)


def structure_refine_expression(expression: str) -> str:
    """独立结构优化函数（可直接替代 mutate_expression mode='structure_refine'）。"""
    opt = IterativeOptimizer()
    return opt.structure_refine(expression)
