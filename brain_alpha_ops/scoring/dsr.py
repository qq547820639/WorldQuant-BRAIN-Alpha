"""Deflated Sharpe Ratio (DSR) — Bailey & Lopez de Prado 2014.

实现 DSR 解析公式，用于对多次试验产生的 Sharpe 比率进行多重检验校正。
当 N=1 时 DSR 退化为 PSR（Probabilistic Sharpe Ratio），保持向后兼容。

公式参考:
    PSR(SR) = Φ( ((SR - SR_benchmark) * √(T-1)) / √(1 - γ3*SR + (γ4-1)/4 * SR²) )
    SR_benchmark(N) = E[max_N] ≈ σ * ( (1-γ)*Φ^{-1}(1-1/N) + γ*Φ^{-1}(1-1/(N*e)) )

其中 γ ≈ 0.5772 为 Euler-Mascheroni 常数。N=1 时 E[max_1] = 0，故 DSR == PSR。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any

# ═══════════════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════════════

# Euler-Mascheroni 常数 γ ≈ 0.5772156649
_EULER_MASCHERONI: float = 0.5772156649015328606

# 单次试验 Sharpe 标准差默认值（Bailey & Lopez de Prado 2014 推荐 σ ≈ 1）
DEFAULT_SHARPE_STD: float = 1.0

# 默认收益序列偏度与峰度（近似正态分布）
DEFAULT_SKEWNESS: float = 0.0
DEFAULT_KURTOSIS: float = 3.0

# 默认观测样本数（约两年日频）
DEFAULT_T: int = 504

# 标准正态分布实例
_ND = NormalDist(0.0, 1.0)


# ═══════════════════════════════════════════════════════════════════════
# 正态分布辅助函数（仅依赖 stdlib）
# ═══════════════════════════════════════════════════════════════════════

def _phi_cdf(z: float) -> float:
    """标准正态分布累积分布函数 Φ(z)。"""
    return _ND.cdf(z)


def _phi_ppf(p: float) -> float:
    """标准正态分布分位数函数 Φ^{-1}(p)，p 必须在 (0, 1) 开区间内。"""
    if not 0.0 < p < 1.0:
        raise ValueError(f"phi_ppf 要求 0 < p < 1，得到 p={p}")
    return _ND.inv_cdf(p)


# ═══════════════════════════════════════════════════════════════════════
# DSR 核心计算
# ═══════════════════════════════════════════════════════════════════════

def expected_max_sharpe(N: int, sigma: float = DEFAULT_SHARPE_STD) -> float:
    """计算 N 次独立试验下 Sharpe 比率最大值的期望 E[max_N]。

    基于独立标准正态样本最大值的近似公式（Bailey & Lopez de Prado 2014）：
        E[max_N] ≈ σ * ( (1-γ)*Φ^{-1}(1-1/N) + γ*Φ^{-1}(1-1/(N*e)) )

    当 N=1 时直接返回 0（单次试验无多重检验惩罚），保证 DSR(N=1) 等价于 PSR。
    """
    if N < 1:
        raise ValueError(f"N 必须 ≥ 1，得到 N={N}")
    if sigma < 0:
        raise ValueError(f"sigma 必须 ≥ 0，得到 sigma={sigma}")
    if N == 1:
        # 单次试验：E[max_1] = 0，DSR 退化为 PSR(sr_benchmark=0)
        return 0.0
    gamma = _EULER_MASCHERONI
    z1 = _phi_ppf(1.0 - 1.0 / N)
    z2 = _phi_ppf(1.0 - 1.0 / (N * math.e))
    return sigma * ((1.0 - gamma) * z1 + gamma * z2)


def probabilistic_sharpe_ratio(
    sharpe: float,
    T: int = DEFAULT_T,
    sr_benchmark: float = 0.0,
    skewness: float = DEFAULT_SKEWNESS,
    kurtosis: float = DEFAULT_KURTOSIS,
) -> float:
    """计算 Probabilistic Sharpe Ratio (PSR)。

    PSR(SR) = Φ( ((SR - SR_benchmark) * √(T-1)) / √(1 - γ3*SR + (γ4-1)/4 * SR²) )

    返回 PSR ∈ [0, 1]：Sharpe 超过基准的概率。
    """
    if T <= 1:
        raise ValueError(f"T 必须 > 1，得到 T={T}")
    if not math.isfinite(sharpe):
        return 0.0
    numerator = (sharpe - sr_benchmark) * math.sqrt(T - 1)
    denom_sq = 1.0 - skewness * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe * sharpe
    if denom_sq <= 0.0:
        # 非正态参数退化：保守返回 0
        return 0.0
    z = numerator / math.sqrt(denom_sq)
    return _phi_cdf(z)


def deflated_sharpe_ratio(
    sharpe: float,
    T: int = DEFAULT_T,
    N: int = 1,
    sigma: float = DEFAULT_SHARPE_STD,
    skewness: float = DEFAULT_SKEWNESS,
    kurtosis: float = DEFAULT_KURTOSIS,
) -> float:
    """计算 Deflated Sharpe Ratio (DSR)。

    DSR 在 PSR 基础上，将 SR_benchmark 上调为多次试验下 Sharpe 最大值的期望，
    从而控制多重检验导致的假阳性。N=1 时 DSR == PSR(sr_benchmark=0)。
    """
    sr_benchmark = expected_max_sharpe(N, sigma)
    return probabilistic_sharpe_ratio(
        sharpe=sharpe, T=T, sr_benchmark=sr_benchmark,
        skewness=skewness, kurtosis=kurtosis,
    )


# ═══════════════════════════════════════════════════════════════════════
# 阈值与门控决策（spec 波次 1.1.3）
# ═══════════════════════════════════════════════════════════════════════

# DSR 门控阈值
DSR_PASS_THRESHOLD: float = 0.95      # 通过此维度
DSR_FILTER_THRESHOLD: float = 0.50    # 直接过滤

# 分层阈值（按 alpha 来源）
DSR_HYPOTHESIS_DRIVEN_MIN: float = 0.30
DSR_DATA_DRIVEN_MIN: float = 0.50

ALPHA_SOURCE_HYPOTHESIS: str = "hypothesis_driven"
ALPHA_SOURCE_DATA: str = "data_driven"


@dataclass
class DSRThresholdPolicy:
    """DSR 分层阈值策略，支持按 alpha 来源差异化门控。"""
    pass_threshold: float = DSR_PASS_THRESHOLD
    filter_threshold: float = DSR_FILTER_THRESHOLD
    hypothesis_driven_min: float = DSR_HYPOTHESIS_DRIVEN_MIN
    data_driven_min: float = DSR_DATA_DRIVEN_MIN


def dsr_gate_decision(
    dsr: float,
    alpha_source: str = ALPHA_SOURCE_HYPOTHESIS,
    policy: DSRThresholdPolicy | None = None,
) -> dict[str, Any]:
    """根据 DSR 与分层阈值生成门控决策。

    返回字典：{passed, filtered, reason, threshold_used, dsr}
    """
    policy = policy or DSRThresholdPolicy()
    if alpha_source == ALPHA_SOURCE_DATA:
        min_threshold = policy.data_driven_min
    else:
        min_threshold = policy.hypothesis_driven_min

    if dsr < policy.filter_threshold:
        return {
            "passed": False, "filtered": True,
            "reason": "dsr_below_filter_threshold",
            "threshold_used": policy.filter_threshold, "dsr": dsr,
        }
    if dsr >= policy.pass_threshold:
        return {
            "passed": True, "filtered": False,
            "reason": "dsr_pass",
            "threshold_used": policy.pass_threshold, "dsr": dsr,
        }
    if dsr >= min_threshold:
        return {
            "passed": True, "filtered": False,
            "reason": "dsr_above_source_min",
            "threshold_used": min_threshold, "dsr": dsr,
        }
    return {
        "passed": False, "filtered": False,
        "reason": "dsr_below_source_min",
        "threshold_used": min_threshold, "dsr": dsr,
    }


# ═══════════════════════════════════════════════════════════════════════
# 特性开关 use_dsr（spec 波次 1.1.4）
# ═══════════════════════════════════════════════════════════════════════

USE_DSR_ENV_VAR: str = "BRAIN_ALPHA_USE_DSR"
_USE_DSR_DEFAULT: bool = True
_TRUTHY: set[str] = {"1", "true", "yes", "on"}


def use_dsr_enabled(config: Any = None) -> bool:
    """读取 use_dsr 特性开关。

    优先级：
    1. 配置对象/字典中的 `use_dsr` 字段（若提供且非 None）
    2. 环境变量 `BRAIN_ALPHA_USE_DSR`（"true"/"1"/"yes"/"on" 视为启用）
    3. 默认值 True

    返回 True 表示启用 DSR；False 回退到原始 Sharpe。
    """
    if config is not None:
        cfg_value: Any = None
        if isinstance(config, dict):
            cfg_value = config.get("use_dsr")
        else:
            cfg_value = getattr(config, "use_dsr", None)
        if cfg_value is not None:
            return bool(cfg_value)
    raw = os.environ.get(USE_DSR_ENV_VAR)
    if raw is None:
        return _USE_DSR_DEFAULT
    return raw.strip().lower() in _TRUTHY
