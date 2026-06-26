"""Workflow phase guidance for user-facing pipeline stages.

Split from the former ``brain_alpha_ops/ux/errors.py`` monolith
(deep-optimization-phase13). Provides the ``PHASE_GUIDANCE`` mapping and
``get_phase_guidance`` helper used to surface per-stage descriptions and
recommended actions in the UI.
"""
from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════
# Phase description for workflow guidance
# ═══════════════════════════════════════════════════════════════════════

PHASE_GUIDANCE: dict[str, dict[str, str]] = {
    "connection": {
        "title": "连接与认证",
        "description": "验证本地服务能否通过 BRAIN API 认证。认证成功后，可以进行云端同步和候选生成。",
        "action": "点击「测试连接」按钮。如果失败，请重新填写凭证或让维护者检查托管凭证。",
    },
    "sync": {
        "title": "云端数据同步",
        "description": "从 BRAIN 平台完整同步已提交的 Alpha 列表；3d/7d 只作为本次显式过滤选项。",
        "action": "点击「开始同步」。未显式选择短范围时，系统会同步云端全部可用 Alpha，进度会通过进度条和事件日志展示。",
    },
    "generate": {
        "title": "候选 Alpha 生成",
        "description": "基于当前配置策略生成新的 Alpha 候选。本地生成结合 Hypothesis-Driven 和经验学习。",
        "action": "配置生成数量后点击「开始生成」。生成完成后可在候选列表中查看和筛选。",
    },
    "score": {
        "title": "评分与验证",
        "description": "对候选 Alpha 进行多维评分，包括先验评分（8维）、实证评分（16项）和提交清单（7项）。",
        "action": "选中候选后点击「评分」。评分结果包含决策建议和改进提示。",
    },
    "check": {
        "title": "提交前检查",
        "description": "批量检查候选 Alpha 的提交资格，包括表达式验证、重复检测和安全门禁。",
        "action": "选中符合条件的候选后点击「批量检查」。检查通过后可进入提交阶段。",
    },
    "submit": {
        "title": "提交到 BRAIN",
        "description": "将通过所有检查的 Alpha 提交到 BRAIN 平台。提交前请确认评分和检查结果均满足要求。",
        "action": "仅选中有 official_alpha_id 的候选。提交不可撤销，请仔细确认。",
    },
}


def get_phase_guidance(phase: str) -> dict[str, str]:
    """Get user-facing workflow phase guidance."""
    return PHASE_GUIDANCE.get(phase, {
        "title": phase,
        "description": "操作进行中",
        "action": "请按工作流步骤操作",
    })
