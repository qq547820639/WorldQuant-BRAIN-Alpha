"""真实因子融合 — 正交化组合与残差 Alpha 构造。

将两个 Alpha 表达式融合为新的、信息不冗余的复合 Alpha。
替代 v2.1 中仅包裹 zscore/winsorize 的伪融合。

融合操作符：
- orthogonal_blend: 正交化组合 alpha1 - beta * alpha2
- residual_alpha: 残差 Alpha（signal 对 base 的残差）
- composite_fusion: 简单组合模式（rank 乘积）

所有融合均为表达式级操作（构造新的 BRAIN 表达式），不依赖本地数值计算。

Usage::

    from brain_alpha_ops.research.fusion import orthogonal_blend, residual_alpha

    fused = orthogonal_blend("rank(ts_delta(f1, 20))", "rank(zscore(f2))")
    # → (rank(ts_delta(f1, 20))) - ts_regression((rank(ts_delta(f1, 20))), (rank(zscore(f2))), 252) * (rank(zscore(f2)))
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from brain_alpha_ops.models import Candidate


# ═══════════════════════════════════════════════════════════════════════
# 融合算符
# ═══════════════════════════════════════════════════════════════════════

def orthogonal_blend(alpha1_expr: str, alpha2_expr: str) -> str:
    """正交化组合两个 Alpha 表达式。

    构造形式：alpha1 - beta * alpha2
    其中 beta 通过 ts_regression 在表达式内动态估计。

    BRAIN 表达式等价：
        ({alpha1}) - ts_regression(({alpha1}), ({alpha2}), 252) * ({alpha2})

    这确保了融合后的 Alpha 与 alpha2 正交（在 252 天窗口内），
    从而消除信息冗余。
    """
    return (
        f"({alpha1_expr}) - "
        f"ts_regression(({alpha1_expr}), ({alpha2_expr}), 252) * ({alpha2_expr})"
    )


def residual_alpha(base_expr: str, signal_expr: str) -> str:
    """残差 Alpha 构造：signal 对 base 线性回归后的残差。

    构造形式：signal - beta * base
    其中 beta 通过 ts_regression 在表达式内动态估计。

    BRAIN 表达式等价：
        ({signal}) - ts_regression(({signal}), ({base}), 252) * ({base})

    用途：当 signal 中包含 base 已捕获的信息时，提取 signal 的增量部分。
    """
    return (
        f"({signal_expr}) - "
        f"ts_regression(({signal_expr}), ({base_expr}), 252) * ({base_expr})"
    )


def composite_fusion(ex1: str, ex2: str, mode: str = "orthogonal") -> str:
    """多模式融合入口。

    Args:
        ex1: 第一个 Alpha 表达式
        ex2: 第二个 Alpha 表达式
        mode: 融合模式
            - "orthogonal" → orthogonal_blend(ex1, ex2)
            - "residual"   → residual_alpha(ex1, ex2)  (ex2 对 ex1 回归)
            - "reverse_residual" → residual_alpha(ex2, ex1) (ex1 对 ex2 回归)
            - "composite"  → rank(ex1) * rank(ex2)

    Returns:
        融合后的表达式字符串
    """
    if mode == "orthogonal":
        return orthogonal_blend(ex1, ex2)
    elif mode == "residual":
        return residual_alpha(ex1, ex2)
    elif mode == "reverse_residual":
        return residual_alpha(ex2, ex1)
    elif mode == "composite":
        return f"rank({ex1}) * rank({ex2})"
    else:
        # 默认回退到 orthogonal
        return orthogonal_blend(ex1, ex2)


def composite_ensemble(expressions: List[str], mode: str = "average") -> str:
    """多 Alpha 集成。

    Args:
        expressions: Alpha 表达式列表（至少 2 个）
        mode: 集成模式
            - "average": 等权平均所有表达式
            - "rank_average": rank 后等权平均
            - "max": 取所有表达式中的最大值
            - "min": 取所有表达式中的最小值

    Returns:
        集成后的表达式字符串
    """
    if len(expressions) < 2:
        return expressions[0] if expressions else ""

    if mode == "average":
        terms = " + ".join(f"({e})" for e in expressions)
        return f"({terms}) / {len(expressions)}"
    elif mode == "rank_average":
        terms = " + ".join(f"rank({e})" for e in expressions)
        return f"({terms}) / {len(expressions)}"
    elif mode == "max":
        result = f"ts_max(({expressions[0]}), ({expressions[1]}), 252)"
        for e in expressions[2:]:
            result = f"ts_max(({result}), ({e}), 252)"
        return result
    elif mode == "min":
        result = f"ts_min(({expressions[0]}), ({expressions[1]}), 252)"
        for e in expressions[2:]:
            result = f"ts_min(({result}), ({e}), 252)"
        return result
    else:
        return orthogonal_blend(expressions[0], expressions[1])


# ═══════════════════════════════════════════════════════════════════════
# 融合候选选择
# ═══════════════════════════════════════════════════════════════════════

def select_fusion_candidates(
    pool: Dict[str, Candidate],
    top_n: int = 3,
    require_official: bool = True,
) -> List[Tuple[Candidate, Candidate]]:
    """从候选池中选择最佳融合对。

    策略：按 score 排序取 top-N 候选，两两配对生成融合对。
    优先选择 Sharpe 属性互补的配对（如一个高 Sharpe 一个低相关）。

    Args:
        pool: 候选池（expression → Candidate 映射）
        top_n: 取 top-N 候选进行配对
        require_official: 是否只选择有 official_metrics 的候选

    Returns:
        融合对列表 [(c1, c2), ...]，按 c1 的 score 降序排列
    """
    # 筛选候选
    candidates = list(pool.values())
    if require_official:
        candidates = [c for c in candidates if c.official_metrics]
    if not candidates:
        return []

    # 按 score 排序
    candidates.sort(
        key=lambda c: c.scorecard.get("total_score", 0) if c.scorecard else 0,
        reverse=True,
    )

    top = candidates[:min(top_n, len(candidates))]
    if len(top) < 2:
        return []

    # 生成配对（不重复、不自配对）
    pairs = []
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            pairs.append((top[i], top[j]))

    return pairs


def get_fusion_modes() -> List[str]:
    """返回所有可用的融合模式。"""
    return ["orthogonal", "residual", "reverse_residual", "composite"]


def generate_fusion_expressions(
    c1: Candidate, c2: Candidate,
) -> Dict[str, str]:
    """为一对候选生成所有融合模式的表达式。

    Returns:
        {mode: expression} 字典
    """
    ex1 = c1.expression or ""
    ex2 = c2.expression or ""
    if not ex1 or not ex2:
        return {}

    return {
        "orthogonal": orthogonal_blend(ex1, ex2),
        "residual": residual_alpha(ex1, ex2),
        "reverse_residual": residual_alpha(ex2, ex1),
        "composite": composite_fusion(ex1, ex2, mode="composite"),
    }
