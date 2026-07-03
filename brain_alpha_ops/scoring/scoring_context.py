"""ScoringContext —— 跨候选持久化的评分上下文（spec 波次 1.1.2）。

`ScoringContext` 持有累计试验次数 N，供 DSR 多重检验惩罚使用。
N 通过 `increment_trials()` 在每个新候选评分时累加，通过 `trials()` 读取。
当 `use_dsr=False` 时回退到原始 Sharpe，DSR 不参与判定（spec 波次 1.1.4）。
"""

from __future__ import annotations

import threading
from typing import Any

from brain_alpha_ops.scoring.dsr import (
    ALPHA_SOURCE_DATA,
    ALPHA_SOURCE_HYPOTHESIS,
    DEFAULT_KURTOSIS,
    DEFAULT_SHARPE_STD,
    DEFAULT_SKEWNESS,
    DEFAULT_T,
    DSRThresholdPolicy,
    deflated_sharpe_ratio,
    dsr_gate_decision,
    use_dsr_enabled,
)


class ScoringContext:
    """评分上下文：跨候选持久化累计试验次数 N（线程安全）。

    使用方式：
        ctx = ScoringContext()
        for candidate in candidates:
            ctx.increment_trials()
            result = ctx.evaluate_dsr(sharpe=candidate.sharpe, T=T)
    """

    def __init__(
        self,
        *,
        initial_N: int = 0,
        use_dsr: bool | None = None,
        policy: DSRThresholdPolicy | None = None,
    ) -> None:
        if initial_N < 0:
            raise ValueError(f"initial_N 必须 ≥ 0，得到 {initial_N}")
        self._N: int = int(initial_N)
        self._lock = threading.Lock()
        # 显式传入优先；否则按特性开关解析
        self._use_dsr: bool = use_dsr if use_dsr is not None else use_dsr_enabled()
        self._policy: DSRThresholdPolicy = policy or DSRThresholdPolicy()

    # --- 试验计数 N -------------------------------------------------------
    def trials(self) -> int:
        """返回当前累计试验次数 N。"""
        with self._lock:
            return self._N

    def increment_trials(self, delta: int = 1) -> int:
        """增加累计试验次数，返回更新后的 N。"""
        if delta < 0:
            raise ValueError(f"delta 必须 ≥ 0，得到 {delta}")
        with self._lock:
            self._N += int(delta)
            return self._N

    def reset_trials(self) -> int:
        """重置试验计数（用于新管线 / 测试）。"""
        with self._lock:
            self._N = 0
            return self._N

    # --- 特性开关 ---------------------------------------------------------
    @property
    def use_dsr(self) -> bool:
        """是否启用 DSR。False 时回退到原始 Sharpe。"""
        return self._use_dsr

    @use_dsr.setter
    def use_dsr(self, value: bool) -> None:
        self._use_dsr = bool(value)

    @property
    def policy(self) -> DSRThresholdPolicy:
        return self._policy

    # --- 评分集成 ---------------------------------------------------------
    def evaluate_dsr(
        self,
        sharpe: float,
        T: int = DEFAULT_T,
        alpha_source: str = ALPHA_SOURCE_HYPOTHESIS,
        sigma: float = DEFAULT_SHARPE_STD,
        skewness: float = DEFAULT_SKEWNESS,
        kurtosis: float = DEFAULT_KURTOSIS,
    ) -> dict[str, Any]:
        """对单个候选计算 DSR 并产生门控决策。

        若 use_dsr=False，直接返回原始 Sharpe 信息而不施加 DSR 门控。

        Args:
            sharpe: 观测 Sharpe 比率。
            T: 观测样本数。
            alpha_source: "hypothesis_driven" 或 "data_driven"。
            sigma: 单次试验 Sharpe 标准差。
            skewness: 收益偏度。
            kurtosis: 收益峰度。

        Returns:
            字典：{use_dsr, sharpe, dsr, N, decision}
        """
        if not self._use_dsr:
            return {
                "use_dsr": False,
                "sharpe": sharpe,
                "dsr": None,
                "N": self.trials(),
                "decision": None,
            }
        N = self.trials()
        # N=0 时按 1 处理，保证数学定义域；DSR == PSR
        effective_N = max(N, 1)
        dsr = deflated_sharpe_ratio(
            sharpe=sharpe, T=T, N=effective_N,
            sigma=sigma, skewness=skewness, kurtosis=kurtosis,
        )
        decision = dsr_gate_decision(
            dsr, alpha_source=alpha_source, policy=self._policy,
        )
        return {
            "use_dsr": True,
            "sharpe": sharpe,
            "dsr": dsr,
            "N": N,
            "decision": decision,
        }
