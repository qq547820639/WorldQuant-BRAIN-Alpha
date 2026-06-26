"""Status code to Chinese display text localization.

Split from the former ``brain_alpha_ops/ux/errors.py`` monolith
(deep-optimization-phase13). Provides the ``STATUS_CODE_ZH`` mapping and
``translate_status_code`` helper used to render pipeline / job / gate
statuses in user-facing Chinese text.
"""
from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════
# Status code to Chinese display text mapping
# ═══════════════════════════════════════════════════════════════════════

STATUS_CODE_ZH: dict[str, str] = {
    # Pipeline lifecycle statuses
    "created": "已创建",
    "generated": "已生成",
    "local_prefilter_passed": "本地预筛通过",
    "local_prefilter_rejected": "本地预筛未通过",
    "local_backtest_passed": "本地回测通过",
    "local_backtest_failed": "本地回测未通过",
    "validation_passed": "官方验证通过",
    "validation_failed": "官方验证未通过",
    "simulation_started": "已提交模拟",
    "simulation_running": "模拟运行中",
    "simulation_completed": "模拟已完成",
    "simulation_failed": "模拟失败",
    "scored": "已评分",
    "gate_submission_ready": "待提交",
    "gate_needs_iteration": "需要迭代",
    "gate_hard_gate_blocked": "硬门禁阻断",
    "submitted": "已提交",
    "submit_blocked": "提交阻止",
    "research_only": "仅研究",
    "optimize_before_submit": "优化后可提交",
    "abandon_or_rebuild": "放弃或重建",
    "submit_candidate": "可提交候选",
    "hard_gate_blocked": "硬门禁阻断",

    # Decision bands
    "SUBMISSION_READY": "提交就绪",
    "NEEDS_ITERATION": "需要迭代优化",
    "BLOCKED": "已被阻止",
    "ALLOW": "允许提交",
    "PASS": "已通过",
    "FAIL": "未通过",
    "PENDING": "等待中",
    "UNKNOWN": "未知",

    # Job statuses
    "starting": "正在启动",
    "running": "运行中",
    "completed": "已完成",
    "failed": "已失败",
    "pending": "等待中",
    "idle": "空闲",
    "stopping": "正在停止",
    "stopped": "已停止",
    "missing": "验证流程不存在",
    "not_started": "未开始",

    # Gate/Check statuses
    "ready": "就绪",
    "needs_iteration": "需要迭代",
    "hard_gate_blocked": "硬门禁阻断",
    "pass": "通过",
    "fail": "未通过",
    "block": "阻止",
}


def translate_status_code(code: str) -> str:
    """Translate a status code to Chinese display text.

    Falls back to the original code if no translation exists.
    """
    if not code:
        return "未知"
    # Try exact match first
    if code in STATUS_CODE_ZH:
        return STATUS_CODE_ZH[code]
    # Try uppercase
    upper = code.upper()
    if upper in STATUS_CODE_ZH:
        return STATUS_CODE_ZH[upper]
    # Try lowercase
    lower = code.lower()
    if lower in STATUS_CODE_ZH:
        return STATUS_CODE_ZH[lower]
    return code
