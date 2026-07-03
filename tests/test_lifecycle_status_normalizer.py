"""Tests for LifecycleStatusNormalizer (Task 6.1 — 遗留状态映射清理)."""
from __future__ import annotations

import warnings

import pytest

from brain_alpha_ops.candidate_lifecycle import LifecycleState, get_lifecycle
from brain_alpha_ops.lifecycle_status_normalizer import (
    LifecycleStatusNormalizer,
    normalizer as default_normalizer,
)
from brain_alpha_ops.models import Candidate

_PHASE_ENV = "BRAIN_ALPHA_LIFECYCLE_DEPRECATION_PHASE"


# ---- SubTask 6.1.1 / 6.1.6: 封装 30+ 项映射 ----

def test_normalizer_encapsulates_legacy_map_with_30_plus_entries():
    """SubTask 6.1.1/6.1.6：normalizer 封装的映射项 ≥30（基线 37）。"""
    norm = LifecycleStatusNormalizer()
    assert len(norm.legacy_map) >= 30
    # normalizer 引用同一数据源，未复制。
    from brain_alpha_ops.candidate_lifecycle import _LEGACY_STATUS_MAP
    assert norm.legacy_map is _LEGACY_STATUS_MAP


# ---- SubTask 6.1.2: vN 静默映射 + 遗留字符串映射到规范枚举 ----

def test_legacy_string_maps_to_canonical():
    """遗留别名字符串正确映射到规范 LifecycleState。"""
    norm = LifecycleStatusNormalizer()
    assert norm.normalize("created") is LifecycleState.draft
    assert norm.normalize("local_scored") is LifecycleState.locally_scored
    assert norm.normalize("candidate_pool_retained") is LifecycleState.locally_scored
    assert norm.normalize("local_prefilter_rejected") is LifecycleState.gate_rejected
    assert norm.normalize("previously_rejected_expression_skipped") is LifecycleState.gate_rejected
    assert norm.normalize("backtest_slot_selected") is LifecycleState.queued_for_simulation
    assert norm.normalize("simulation_deferred_rate_limit") is LifecycleState.queued_for_simulation
    assert norm.normalize("simulation_submitted") is LifecycleState.simulating
    assert norm.normalize("simulation_poll_deferred_unknown") is LifecycleState.simulating
    assert norm.normalize("simulation_poll_failed") is LifecycleState.simulation_failed
    assert norm.normalize("simulation_request_failed") is LifecycleState.simulation_failed
    assert norm.normalize("official_simulated") is LifecycleState.simulation_passed
    assert norm.normalize("submission_ready") is LifecycleState.ready_for_review
    assert norm.normalize("auto_submit_readiness_blocked") is LifecycleState.ready_for_review
    assert norm.normalize("candidate_pool_pruned") is LifecycleState.archived


def test_canonical_name_string_maps_to_self():
    """规范名字符串（如 "draft"）映射到自身对应枚举。"""
    norm = LifecycleStatusNormalizer()
    canonical_states = [
        LifecycleState.draft, LifecycleState.locally_scored, LifecycleState.gate_rejected,
        LifecycleState.queued_for_simulation, LifecycleState.simulating,
        LifecycleState.simulation_failed, LifecycleState.simulation_passed,
        LifecycleState.needs_optimization, LifecycleState.ready_for_review,
        LifecycleState.submitted, LifecycleState.archived,
    ]
    for state in canonical_states:
        assert norm.normalize(state.value) is state


def test_unknown_string_falls_back_to_draft():
    """未知字符串回退到 draft，保持与原 .get(..., draft) 语义一致。"""
    norm = LifecycleStatusNormalizer()
    assert norm.normalize("totally_unknown_status_xyz") is LifecycleState.draft


# ---- SubTask 6.1.5: 新增状态走规范 enum，枚举实例直接返回 ----

def test_enum_instance_passes_through():
    norm = LifecycleStatusNormalizer()
    assert norm.normalize(LifecycleState.simulating) is LifecycleState.simulating
    assert norm.normalize(LifecycleState.archived) is LifecycleState.archived
    assert norm.normalize(LifecycleState.ready_for_review) is LifecycleState.ready_for_review


# ---- SubTask 6.1.2: vN 默认静默，不发出警告 ----

def test_default_phase_is_vN(monkeypatch):
    monkeypatch.delenv(_PHASE_ENV, raising=False)
    assert LifecycleStatusNormalizer._current_phase() == "vN"


def test_vN_silent_no_warning_for_legacy_alias(monkeypatch):
    """vN 阶段对遗留别名静默映射，不发出任何警告。"""
    monkeypatch.setenv(_PHASE_ENV, "vN")
    norm = LifecycleStatusNormalizer()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 任何警告升级为错误
        result = norm.normalize("created")
    assert result is LifecycleState.draft


# ---- SubTask 6.1.3: vN+1 对遗留别名发出 DeprecationWarning ----

def test_vN_plus_1_emits_deprecation_warning_for_legacy_alias(monkeypatch):
    monkeypatch.setenv(_PHASE_ENV, "vN+1")
    norm = LifecycleStatusNormalizer()
    with pytest.warns(DeprecationWarning, match="deprecated"):
        result = norm.normalize("created")
    assert result is LifecycleState.draft


def test_vN_plus_1_emits_warning_for_each_legacy_alias(monkeypatch):
    monkeypatch.setenv(_PHASE_ENV, "vN+1")
    norm = LifecycleStatusNormalizer()
    for legacy in ("official_simulated", "candidate_pool_pruned", "simulation_submitted"):
        with pytest.warns(DeprecationWarning):
            norm.normalize(legacy)


def test_vN_plus_1_no_warning_for_canonical_name_string(monkeypatch):
    """vN+1 阶段规范名字符串（如 "draft"）不发出警告。"""
    monkeypatch.setenv(_PHASE_ENV, "vN+1")
    norm = LifecycleStatusNormalizer()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = norm.normalize("draft")
    assert result is LifecycleState.draft


def test_vN_plus_1_no_warning_for_enum(monkeypatch):
    """vN+1 阶段枚举实例不发出警告（SubTask 6.1.5）。"""
    monkeypatch.setenv(_PHASE_ENV, "vN+1")
    norm = LifecycleStatusNormalizer()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = norm.normalize(LifecycleState.simulating)
    assert result is LifecycleState.simulating


# ---- 阶段切换健壮性 ----

def test_invalid_phase_falls_back_to_vN(monkeypatch):
    """未知阶段值回退到 vN，避免配置笔误阻断生产。"""
    monkeypatch.setenv(_PHASE_ENV, "garbage_value")
    assert LifecycleStatusNormalizer._current_phase() == "vN"
    norm = LifecycleStatusNormalizer()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert norm.normalize("created") is LifecycleState.draft


# ---- is_legacy 语义 ----

def test_is_legacy_true_for_aliases():
    norm = LifecycleStatusNormalizer()
    assert norm.is_legacy("created") is True
    assert norm.is_legacy("candidate_pool_retained") is True
    assert norm.is_legacy("official_simulated") is True
    assert norm.is_legacy("simulation_submitted") is True


def test_is_legacy_false_for_canonical_name_string_and_enum_and_unknown():
    norm = LifecycleStatusNormalizer()
    assert norm.is_legacy("draft") is False          # 规范名字符串
    assert norm.is_legacy("locally_scored") is False
    assert norm.is_legacy(LifecycleState.draft) is False  # 枚举实例
    assert norm.is_legacy("unknown_status") is False     # 未知字符串
    assert norm.is_legacy(123) is False                  # 非字符串


# ---- SubTask 6.1.7: 无功能回归 ----

def _make_candidate(alpha_id: str, status: str) -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression="rank(close)",
        family="test",
        hypothesis="regression",
        scorecard={"total_score": 80},
        lifecycle_status=status,
    )


def test_get_lifecycle_no_regression_legacy_alias(monkeypatch):
    """get_lifecycle 仍能从遗留别名 lifecycle_status 正确初始化状态（向后兼容）。"""
    monkeypatch.delenv(_PHASE_ENV, raising=False)
    cand = _make_candidate("alpha-1", "official_simulated")
    lc = get_lifecycle(cand)
    assert lc.state is LifecycleState.simulation_passed


def test_get_lifecycle_no_regression_canonical_name(monkeypatch):
    monkeypatch.delenv(_PHASE_ENV, raising=False)
    cand = _make_candidate("alpha-2", "simulation_passed")
    lc = get_lifecycle(cand)
    assert lc.state is LifecycleState.simulation_passed


def test_get_lifecycle_no_regression_unknown_status(monkeypatch):
    """未知 lifecycle_status 回退到 draft（保持原 .get(..., draft) 行为）。"""
    monkeypatch.delenv(_PHASE_ENV, raising=False)
    cand = _make_candidate("alpha-3", "totally_unknown")
    lc = get_lifecycle(cand)
    assert lc.state is LifecycleState.draft


def test_candidate_pool_inactive_classification_unchanged(monkeypatch):
    """candidate_pool 的 INACTIVE_BACKTEST_STATUSES 派生结果与直接使用映射一致。"""
    monkeypatch.delenv(_PHASE_ENV, raising=False)
    from brain_alpha_ops.research.candidate_pool import (
        INACTIVE_BACKTEST_STATUSES,
        _is_inactive,
    )
    # 派生集合非空且包含已知 inactive 遗留串。
    assert "simulation_poll_failed" in INACTIVE_BACKTEST_STATUSES
    assert "candidate_pool_pruned" in INACTIVE_BACKTEST_STATUSES
    assert "local_standard_rejected" in INACTIVE_BACKTEST_STATUSES
    # 活跃遗留串不在 inactive 集合中。
    assert "candidate_pool_retained" not in INACTIVE_BACKTEST_STATUSES
    # _is_inactive 行为：inactive 遗留串 → True；活跃遗留串 → False；未知串 → False。
    assert _is_inactive("simulation_poll_failed") is True
    assert _is_inactive("candidate_pool_retained") is False
    assert _is_inactive("unknown_status") is False
    # 枚举实例。
    assert _is_inactive(LifecycleState.archived) is True
    assert _is_inactive(LifecycleState.simulating) is False


def test_default_normalizer_singleton_is_usable():
    """模块级单例 normalizer 可直接使用。"""
    assert isinstance(default_normalizer, LifecycleStatusNormalizer)
    assert default_normalizer.normalize("created") is LifecycleState.draft
    assert default_normalizer.normalize(LifecycleState.archived) is LifecycleState.archived
