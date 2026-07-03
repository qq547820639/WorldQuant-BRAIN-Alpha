"""DSR (Deflated Sharpe Ratio) 单元测试 — Bailey & Lopez de Prado 2014.

覆盖 spec 波次 1.1.5：
- N=1/10/100/200 四档 E[max_N] 与 DSR 计算
- N=1 等价于 PSR（向后兼容）
- 分层阈值门控
- 特性开关 use_dsr 回退（验证 1 分钟内可回滚）
- ScoringContext 跨候选持久化 N
"""

from __future__ import annotations

import math
import os
import time

import pytest

from brain_alpha_ops.scoring.dsr import (
    ALPHA_SOURCE_DATA,
    ALPHA_SOURCE_HYPOTHESIS,
    DEFAULT_T,
    DSR_DATA_DRIVEN_MIN,
    DSR_FILTER_THRESHOLD,
    DSR_HYPOTHESIS_DRIVEN_MIN,
    DSR_PASS_THRESHOLD,
    DSRThresholdPolicy,
    USE_DSR_ENV_VAR,
    deflated_sharpe_ratio,
    dsr_gate_decision,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    use_dsr_enabled,
)
from brain_alpha_ops.scoring.scoring_context import ScoringContext


# ═══════════════════════════════════════════════════════════════════════
# E[max_N] 公式
# ═══════════════════════════════════════════════════════════════════════

class TestExpectedMaxSharpe:
    """E[max_N] 多档覆盖。"""

    @pytest.mark.parametrize("N", [1, 10, 100, 200])
    def test_expected_max_returns_finite_for_N_levels(self, N: int) -> None:
        em = expected_max_sharpe(N)
        assert math.isfinite(em), f"E[max_N] 应为有限值，N={N} 得到 {em}"

    def test_N_eq_1_returns_zero(self) -> None:
        # 单次试验无多重检验惩罚，E[max_1] = 0
        assert expected_max_sharpe(1) == 0.0

    def test_expected_max_monotonically_increases_with_N(self) -> None:
        # E[max_N] 应随 N 单调递增（多重检验惩罚越强）
        Ns = [1, 10, 100, 200]
        values = [expected_max_sharpe(N) for N in Ns]
        for prev, nxt in zip(values, values[1:]):
            assert nxt > prev, f"E[max_N] 应单调递增：{prev} !< {next}"

    def test_N_eq_10_close_to_known_value(self) -> None:
        # N=10, σ=1 时 E[max_10] ≈ 1.57（与文献近似一致）
        em = expected_max_sharpe(10, sigma=1.0)
        assert 1.4 < em < 1.7, f"E[max_10] 期望在 (1.4, 1.7)，得到 {em}"

    def test_N_eq_200_close_to_known_value(self) -> None:
        # N=200, σ=1 时 E[max_200] ≈ 2.77
        em = expected_max_sharpe(200, sigma=1.0)
        assert 2.6 < em < 2.9, f"E[max_200] 期望在 (2.6, 2.9)，得到 {em}"

    def test_sigma_scales_linearly(self) -> None:
        # σ 翻倍，E[max_N] 也应翻倍
        em_s1 = expected_max_sharpe(50, sigma=1.0)
        em_s2 = expected_max_sharpe(50, sigma=2.0)
        assert em_s2 == pytest.approx(2.0 * em_s1, rel=1e-12)

    def test_invalid_N_raises(self) -> None:
        with pytest.raises(ValueError):
            expected_max_sharpe(0)
        with pytest.raises(ValueError):
            expected_max_sharpe(-5)

    def test_negative_sigma_raises(self) -> None:
        with pytest.raises(ValueError):
            expected_max_sharpe(10, sigma=-1.0)


# ═══════════════════════════════════════════════════════════════════════
# N=1 等价于 PSR（关键向后兼容性）
# ═══════════════════════════════════════════════════════════════════════

class TestDSREqualsPSRWhenN1:
    """spec 场景：DSR N=1 等价于 PSR。"""

    @pytest.mark.parametrize("sharpe", [0.0, 0.5, 1.0, 1.5, 2.0, 3.0])
    @pytest.mark.parametrize("T", [50, 252, 504, 1260])
    def test_dsr_equals_psr_when_N1(self, sharpe: float, T: int) -> None:
        dsr = deflated_sharpe_ratio(sharpe=sharpe, T=T, N=1)
        psr = probabilistic_sharpe_ratio(sharpe=sharpe, T=T, sr_benchmark=0.0)
        assert dsr == pytest.approx(psr, abs=1e-15), (
            f"DSR(N=1) 应等于 PSR(bench=0)：sharpe={sharpe}, T={T}, "
            f"DSR={dsr}, PSR={psr}"
        )

    def test_dsr_n1_equals_psr_with_nonnormal_params(self) -> None:
        # 含偏度/峰度也应保持等价
        dsr = deflated_sharpe_ratio(
            sharpe=1.2, T=504, N=1, skewness=0.3, kurtosis=4.0,
        )
        psr = probabilistic_sharpe_ratio(
            sharpe=1.2, T=504, sr_benchmark=0.0, skewness=0.3, kurtosis=4.0,
        )
        assert dsr == pytest.approx(psr, abs=1e-15)


# ═══════════════════════════════════════════════════════════════════════
# DSR 多档 N
# ═══════════════════════════════════════════════════════════════════════

class TestDSRMultipleNLevels:
    """N=1/10/100/200 四档 DSR 计算。"""

    @pytest.mark.parametrize("N", [1, 10, 100, 200])
    def test_dsr_in_unit_interval(self, N: int) -> None:
        dsr = deflated_sharpe_ratio(sharpe=1.5, T=504, N=N)
        assert 0.0 <= dsr <= 1.0, f"DSR 应在 [0,1]，N={N} 得到 {dsr}"

    def test_dsr_decreases_as_N_increases(self) -> None:
        # 同一 Sharpe，N 越大 DSR 越低（多重检验惩罚）
        sharpe, T = 1.5, 504
        dsr_n1 = deflated_sharpe_ratio(sharpe, T=T, N=1)
        dsr_n10 = deflated_sharpe_ratio(sharpe, T=T, N=10)
        dsr_n100 = deflated_sharpe_ratio(sharpe, T=T, N=100)
        dsr_n200 = deflated_sharpe_ratio(sharpe, T=T, N=200)
        assert dsr_n1 >= dsr_n10 >= dsr_n100 >= dsr_n200, (
            f"DSR 应随 N 单调递减：N1={dsr_n1}, N10={dsr_n10}, "
            f"N100={dsr_n100}, N200={dsr_n200}"
        )

    def test_dsr_high_sharpe_passes_at_n1(self) -> None:
        # 高 Sharpe，N=1 时 DSR 应接近 1
        dsr = deflated_sharpe_ratio(sharpe=2.0, T=504, N=1)
        assert dsr > DSR_PASS_THRESHOLD, f"高 Sharpe N=1 应通过 0.95：DSR={dsr}"

    def test_dsr_low_sharpe_filtered_at_large_N(self) -> None:
        # 低 Sharpe + 大 N 应被过滤（DSR < 0.5）
        dsr = deflated_sharpe_ratio(sharpe=0.5, T=504, N=200)
        assert dsr < DSR_FILTER_THRESHOLD, (
            f"低 Sharpe 大 N 应被过滤：DSR={dsr}"
        )


# ═══════════════════════════════════════════════════════════════════════
# PSR 单元
# ═══════════════════════════════════════════════════════════════════════

class TestProbabilisticSharpeRatio:
    """PSR 公式正确性。"""

    def test_psr_zero_sharpe_zero_benchmark_is_half(self) -> None:
        # SR=0, bench=0, 对称分布 → PSR = 0.5
        psr = probabilistic_sharpe_ratio(sharpe=0.0, T=504, sr_benchmark=0.0)
        assert psr == pytest.approx(0.5, abs=1e-12)

    def test_psr_higher_sharpe_higher_psr(self) -> None:
        psr_low = probabilistic_sharpe_ratio(sharpe=0.5, T=504)
        psr_high = probabilistic_sharpe_ratio(sharpe=2.0, T=504)
        assert psr_high > psr_low

    def test_psr_invalid_T_raises(self) -> None:
        with pytest.raises(ValueError):
            probabilistic_sharpe_ratio(sharpe=1.0, T=1)
        with pytest.raises(ValueError):
            probabilistic_sharpe_ratio(sharpe=1.0, T=0)

    def test_psr_nonfinite_sharpe_returns_zero(self) -> None:
        assert probabilistic_sharpe_ratio(sharpe=float("nan"), T=504) == 0.0
        assert probabilistic_sharpe_ratio(sharpe=float("inf"), T=504) == 0.0


# ═══════════════════════════════════════════════════════════════════════
# 阈值门控（spec 波次 1.1.3）
# ═══════════════════════════════════════════════════════════════════════

class TestDSRGateDecision:
    """分层阈值门控：>0.95 通过，<0.50 过滤；假设 ≥0.30，数据 ≥0.50。"""

    def test_below_filter_threshold_filtered(self) -> None:
        decision = dsr_gate_decision(0.40, alpha_source=ALPHA_SOURCE_HYPOTHESIS)
        assert decision["filtered"] is True
        assert decision["passed"] is False
        assert decision["reason"] == "dsr_below_filter_threshold"
        assert decision["threshold_used"] == DSR_FILTER_THRESHOLD

    def test_above_pass_threshold_passes(self) -> None:
        decision = dsr_gate_decision(0.96, alpha_source=ALPHA_SOURCE_HYPOTHESIS)
        assert decision["passed"] is True
        assert decision["filtered"] is False
        assert decision["reason"] == "dsr_pass"
        assert decision["threshold_used"] == DSR_PASS_THRESHOLD

    def test_hypothesis_driven_min_threshold(self) -> None:
        # 假设驱动型 ≥ 0.30 即可通过
        decision = dsr_gate_decision(0.55, alpha_source=ALPHA_SOURCE_HYPOTHESIS)
        assert decision["passed"] is True
        assert decision["filtered"] is False
        assert decision["threshold_used"] == DSR_HYPOTHESIS_DRIVEN_MIN

    def test_data_driven_min_threshold(self) -> None:
        # 数据驱动型 ≥ 0.50 才能通过
        decision = dsr_gate_decision(0.55, alpha_source=ALPHA_SOURCE_DATA)
        assert decision["passed"] is True
        assert decision["filtered"] is False
        assert decision["threshold_used"] == DSR_DATA_DRIVEN_MIN

    def test_data_driven_below_min_but_above_filter(self) -> None:
        # 数据驱动型，DSR=0.45：未到 filter 但低于数据驱动 min，应不通过且不过滤
        decision = dsr_gate_decision(0.45, alpha_source=ALPHA_SOURCE_DATA)
        assert decision["passed"] is False
        assert decision["filtered"] is False
        assert decision["reason"] == "dsr_below_source_min"
        assert decision["threshold_used"] == DSR_DATA_DRIVEN_MIN

    def test_custom_policy_overrides_defaults(self) -> None:
        policy = DSRThresholdPolicy(
            pass_threshold=0.99,
            filter_threshold=0.20,
            hypothesis_driven_min=0.40,
            data_driven_min=0.60,
        )
        decision = dsr_gate_decision(0.30, alpha_source=ALPHA_SOURCE_HYPOTHESIS, policy=policy)
        # 0.30 < filter_threshold(0.20)? 否，0.30 > 0.20；< pass(0.99) 是；< hyp_min(0.40) 是
        assert decision["passed"] is False
        assert decision["filtered"] is False
        assert decision["threshold_used"] == 0.40


# ═══════════════════════════════════════════════════════════════════════
# 特性开关 use_dsr（spec 波次 1.1.4 + 1.1.6 回滚验证）
# ═══════════════════════════════════════════════════════════════════════

class TestUseDSRFeatureFlag:
    """特性开关：环境变量 / 配置 / 默认值，且 1 分钟内可回滚。"""

    def test_default_is_true_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(USE_DSR_ENV_VAR, raising=False)
        assert use_dsr_enabled() is True

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "TRUE", "True"])
    def test_truthy_env_values_enable_dsr(
        self, monkeypatch: pytest.MonkeyPatch, value: str,
    ) -> None:
        monkeypatch.setenv(USE_DSR_ENV_VAR, value)
        assert use_dsr_enabled() is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "FALSE"])
    def test_falsy_env_values_disable_dsr(
        self, monkeypatch: pytest.MonkeyPatch, value: str,
    ) -> None:
        monkeypatch.setenv(USE_DSR_ENV_VAR, value)
        assert use_dsr_enabled() is False

    def test_config_dict_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USE_DSR_ENV_VAR, "true")
        assert use_dsr_enabled({"use_dsr": False}) is False

    def test_config_object_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USE_DSR_ENV_VAR, "false")

        class _Cfg:
            use_dsr = True

        assert use_dsr_enabled(_Cfg()) is True

    def test_config_none_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(USE_DSR_ENV_VAR, "false")

        class _Cfg:
            use_dsr = None

        assert use_dsr_enabled(_Cfg()) is False

    def test_rollback_under_one_minute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # spec 1.1.6：特性开关可在 1 分钟内回滚
        monkeypatch.setenv(USE_DSR_ENV_VAR, "true")
        assert use_dsr_enabled() is True
        start = time.monotonic()
        # 切换为 false
        monkeypatch.setenv(USE_DSR_ENV_VAR, "false")
        assert use_dsr_enabled() is False
        elapsed = time.monotonic() - start
        assert elapsed < 60.0, f"特性开关回滚应在 1 分钟内完成，实际 {elapsed:.3f}s"


# ═══════════════════════════════════════════════════════════════════════
# ScoringContext 跨候选持久化 N（spec 波次 1.1.2）
# ═══════════════════════════════════════════════════════════════════════

class TestScoringContext:
    """ScoringContext 持久化试验计数 N 与 DSR 评分集成。"""

    def test_initial_N_defaults_to_zero(self) -> None:
        ctx = ScoringContext()
        assert ctx.trials() == 0

    def test_increment_trials_accumulates(self) -> None:
        ctx = ScoringContext()
        assert ctx.increment_trials() == 1
        assert ctx.increment_trials() == 2
        assert ctx.increment_trials(5) == 7
        assert ctx.trials() == 7

    def test_reset_trials(self) -> None:
        ctx = ScoringContext(initial_N=10)
        assert ctx.trials() == 10
        assert ctx.reset_trials() == 0
        assert ctx.trials() == 0

    def test_invalid_initial_N_raises(self) -> None:
        with pytest.raises(ValueError):
            ScoringContext(initial_N=-1)

    def test_negative_delta_raises(self) -> None:
        ctx = ScoringContext()
        with pytest.raises(ValueError):
            ctx.increment_trials(-1)

    def test_use_dsr_property_toggle(self) -> None:
        ctx = ScoringContext(use_dsr=True)
        assert ctx.use_dsr is True
        ctx.use_dsr = False
        assert ctx.use_dsr is False

    def test_use_dsr_false_skips_dsr_evaluation(self) -> None:
        ctx = ScoringContext(use_dsr=False)
        ctx.increment_trials(100)
        result = ctx.evaluate_dsr(sharpe=2.0, T=504)
        assert result["use_dsr"] is False
        assert result["dsr"] is None
        assert result["decision"] is None
        assert result["sharpe"] == 2.0
        assert result["N"] == 100

    def test_use_dsr_true_computes_dsr(self) -> None:
        ctx = ScoringContext(use_dsr=True)
        ctx.increment_trials(10)  # N=10
        result = ctx.evaluate_dsr(sharpe=2.0, T=504, alpha_source=ALPHA_SOURCE_HYPOTHESIS)
        assert result["use_dsr"] is True
        assert result["dsr"] is not None
        assert 0.0 <= result["dsr"] <= 1.0
        assert result["N"] == 10
        assert result["decision"] is not None
        assert "passed" in result["decision"]

    def test_N_zero_treated_as_one(self) -> None:
        # N=0 时按 N=1 处理，DSR == PSR
        ctx = ScoringContext(use_dsr=True)
        # N 仍为 0
        result = ctx.evaluate_dsr(sharpe=1.5, T=504)
        psr = probabilistic_sharpe_ratio(sharpe=1.5, T=504, sr_benchmark=0.0)
        assert result["dsr"] == pytest.approx(psr, abs=1e-15)

    def test_persistent_N_across_candidates(self) -> None:
        # 模拟连续候选评分，N 应单调累加
        ctx = ScoringContext(use_dsr=True)
        sharpes = [1.8, 1.5, 2.0, 0.9, 1.2]
        Ns_seen = []
        for sharpe in sharpes:
            ctx.increment_trials()
            result = ctx.evaluate_dsr(sharpe=sharpe, T=504)
            Ns_seen.append(result["N"])
        assert Ns_seen == [1, 2, 3, 4, 5], f"N 应单调累加：{Ns_seen}"
        # DSR 应随 N 增加而降低（对同一 Sharpe）
        # 验证最后一个候选（sharpe=1.2）与第一个（sharpe=1.8）相比，DSR 更低
        # 但 sharpe 不同，所以直接验证单调性：使用相同 sharpe 重新跑一遍
        ctx2 = ScoringContext(use_dsr=True)
        dsr_n1 = None
        dsr_n5 = None
        for i in range(5):
            ctx2.increment_trials()
            result = ctx2.evaluate_dsr(sharpe=1.5, T=504)
            if i == 0:
                dsr_n1 = result["dsr"]
            dsr_n5 = result["dsr"]
        assert dsr_n5 < dsr_n1, (
            f"N=5 时 DSR 应低于 N=1：DSR(N=1)={dsr_n1}, DSR(N=5)={dsr_n5}"
        )


# ═══════════════════════════════════════════════════════════════════════
# 端到端集成场景
# ═══════════════════════════════════════════════════════════════════════

class TestDSREndToEnd:
    """spec 端到端场景：阈值过滤 + 特性开关回退。"""

    def test_scenario_dsr_below_0_50_filtered(self) -> None:
        # 候选 DSR < 0.50 应被直接过滤
        decision = dsr_gate_decision(0.30, alpha_source=ALPHA_SOURCE_HYPOTHESIS)
        assert decision["filtered"] is True

    def test_scenario_dsr_above_0_95_passes(self) -> None:
        # 候选 DSR > 0.95 应通过
        decision = dsr_gate_decision(0.97, alpha_source=ALPHA_SOURCE_HYPOTHESIS)
        assert decision["passed"] is True

    def test_scenario_use_dsr_false_falls_back_to_sharpe(self) -> None:
        # 特性开关 use_dsr=false 时评分回退到原始 Sharpe，DSR 不参与判定
        ctx = ScoringContext(use_dsr=False)
        result = ctx.evaluate_dsr(sharpe=0.3, T=504)  # 即使 Sharpe 很低
        assert result["use_dsr"] is False
        assert result["decision"] is None  # 不施加 DSR 门控

    def test_scenario_full_pipeline_with_dsr(self) -> None:
        # 模拟完整评分流程：N 个候选，每个累加 N 并评估 DSR
        ctx = ScoringContext(use_dsr=True)
        candidates = [
            {"sharpe": 2.5, "source": ALPHA_SOURCE_HYPOTHESIS},   # 应通过
            {"sharpe": 0.2, "source": ALPHA_SOURCE_HYPOTHESIS},   # 应过滤
            {"sharpe": 0.6, "source": ALPHA_SOURCE_DATA},         # 边界
        ]
        decisions = []
        for cand in candidates:
            ctx.increment_trials()
            result = ctx.evaluate_dsr(
                sharpe=cand["sharpe"], T=504, alpha_source=cand["source"],
            )
            decisions.append(result["decision"])

        # 高 Sharpe 假设驱动应通过
        assert decisions[0]["passed"] is True
        # 低 Sharpe 应被过滤
        assert decisions[1]["filtered"] is True
        # N=3 时低 Sharpe 数据驱动应在过滤线附近
        assert decisions[2]["dsr"] < DSR_FILTER_THRESHOLD or decisions[2]["passed"] is False
