"""User-facing error translation and status-code localization.

Provides human-readable Chinese translations for technical error codes,
friendly error messages for common failure modes, and structured guidance
for users to resolve issues without needing to interpret raw tracebacks.

Usage::

    from brain_alpha_ops.ux.errors import translate_error, translate_status_code
    friendly = translate_error(raw_error_message)
    status_text = translate_status_code("SUBMISSION_READY")
"""

from __future__ import annotations

from typing import Any

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


# ═══════════════════════════════════════════════════════════════════════
# User-friendly error messages for common failure modes
# ═══════════════════════════════════════════════════════════════════════

_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    # (keyword pattern, user-friendly message, suggested action)
    (
        "authentication",
        "BRAIN 平台认证失败",
        "请在 BRAIN 账户连接区重新测试连接；如果仍失败，请让维护者检查托管凭证和网络状态。",
    ),
    (
        "rate limit",
        "API 请求频率超限，请稍后重试",
        "系统会自动等待后重试。如果频繁遇到此问题，请在系统配置中降低并发或让维护者调整请求间隔。",
    ),
    (
        "connection",
        "无法连接到 BRAIN API 服务器",
        "请确认网络连接正常，并检查是否在公司 VPN 或防火墙之后。可在 Web 控制台重新测试连接。",
    ),
    (
        "timeout",
        "API 请求超时",
        "BRAIN 模拟流程可能需要几分钟才能完成。系统会自动轮询结果，请耐心等待。",
    ),
    (
        "json",
        "数据格式解析错误",
        "返回数据格式异常。请在系统配置中检查参数，或尝试重新同步云端数据。",
    ),
    (
        "config",
        "配置文件验证失败",
        "请在 Web 控制台的系统配置页检查参数；维护者可使用质量门禁中的配置验证结果定位具体错误。",
    ),
    (
        "validation",
        "表达式验证失败",
        "表达式可能包含不支持的字段或算子。请使用「检查表达式」功能验证语法，或从官方字段/算子列表中选择。",
    ),
    (
        "simulation",
        "官方模拟失败",
        "BRAIN 模拟返回了失败结果。请检查评分详情中的失败维度，针对性调整表达式后重新提交模拟。",
    ),
    (
        "correlation",
        "云端关联度过高",
        "此 Alpha 与已有的 Alpha 表达式结构过于相似。建议变更算子组合（如 ts_mean→ts_std）或使用不同字段族。",
    ),
    (
        "submit",
        "提交请求被阻止",
        "提交前需要：1) 完成官方模拟；2) 通过质量门禁检查；3) 确认表达式不重复。请按提交工作流步骤操作。",
    ),
    (
        "not found",
        "请求的资源不存在",
        "请回到候选管理或运行总览重新选择可见记录。",
    ),
    (
        "permission",
        "权限不足",
        "当前账号权限不足以执行此操作。请联系 WorldQuant 支持或确认账号级别。",
    ),
    (
        "memory",
        "系统内存不足",
        "当前数据处理量过大。请在系统配置中减少候选数量或保留池规模。",
    ),
    (
        "disk",
        "磁盘空间不足",
        "本地缓存空间不足。请让维护者清理缓存或调整存储位置。",
    ),
    (
        "syntax",
        "表达式语法错误",
        "请检查表达式括号是否匹配、算子名称是否正确。可在 BRAIN 平台 Web 界面中先测试表达式。",
    ),
    (
        "token",
        "访问令牌无效或已过期",
        "请在 BRAIN 账户连接区重新测试连接；如果使用托管凭证，请让维护者刷新凭证。",
    ),
    (
        "convergence_stalled",
        "搜索收敛停滞",
        "当前策略已无法产生更好的 Alpha。系统会自动触发融合策略或切换搜索配置。",
    ),
    (
        "self_correlation",
        "自相关度过高",
        "Alpha 与自身的回测表现高度相关，可能过拟合。建议增加 out-of-sample 验证窗口或简化表达式。",
    ),
    (
        "turnover",
        "换手率不符合要求",
        "换手率过高(>70%)会触发 BRAIN 平台硬门禁，过高或过低都会影响质量评分。建议调整窗口参数或添加流动性约束。",
    ),
    (
        "concentration",
        "权重集中度过高",
        "单个股票权重超过 10% 会触发 BRAIN 平台门禁。建议添加分散化约束。",
    ),
]


def translate_error(error_message: str) -> dict[str, str]:
    """Translate a raw error message to a user-friendly explanation.

    Returns:
        {
            "original": original error message (redacted),
            "friendly": user-friendly Chinese explanation,
            "suggested_action": actionable next step,
            "error_code": extracted or inferred error code,
        }
    """
    if not error_message:
        return {
            "original": "",
            "friendly": "发生未知错误",
            "suggested_action": "请重试操作。如果问题持续出现，请让维护者查看诊断信息。",
            "error_code": "UNKNOWN",
        }

    lower = str(error_message).lower()

    for pattern, friendly, action in _ERROR_PATTERNS:
        if pattern in lower:
            return {
                "original": str(error_message)[:200],
                "friendly": friendly,
                "suggested_action": action,
                "error_code": _extract_error_code(error_message) or pattern.upper(),
            }

    # Generic fallback
    return {
        "original": str(error_message)[:200],
        "friendly": "操作未能完成",
        "suggested_action": "请重试操作。如果问题持续出现，请查看页面事件记录或让维护者查看诊断信息。",
        "error_code": _extract_error_code(error_message) or "GENERIC_ERROR",
    }


def _extract_error_code(message: str) -> str:
    """Extract an error code from the message if present."""
    import re

    # Match patterns like "error_code": "XXX" or error_code=XXX
    patterns = [
        r'"error_code"\s*:\s*"([^"]+)"',
        r"error_code[=:]\s*(\w+)",
        r"\[([A-Z_]{3,})\]",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    return ""


def translate_check_result(check_name: str) -> dict[str, str]:
    """Provide user-friendly description for a quality check."""
    descriptions: dict[str, dict[str, str]] = {
        "sharpe_positive": {
            "name": "夏普比率 ≥ 1.25",
            "meaning": "风险调整后收益。低于阈值说明风险回报不理想。",
            "fix": "尝试减少极端值暴露或缩短回看窗口。",
        },
        "fitness_minimum": {
            "name": "适应度 ≥ 1.0",
            "meaning": "综合评分。BRAIN 官方公式：Sharpe × √(|收益| / max(换手率, 0.125))。",
            "fix": "提高夏普比率或降低换手率可提升适应度。",
        },
        "returns_positive": {
            "name": "收益为正",
            "meaning": "平均每日收益。负收益意味着策略方向可能错误。",
            "fix": "检查因子方向是否正确，可尝试取反。",
        },
        "turnover_platform": {
            "name": "换手率 ≤ 70%",
            "meaning": "日均换手率。超过 70% 会被 BRAIN 平台硬门禁拒绝。",
            "fix": "增加回看窗口、减少交易频率、添加流动性过滤。",
        },
        "turnover_quality": {
            "name": "换手率质量阈值 ≤ 30%",
            "meaning": "顾问建议的质量阈值（非 BRAIN 硬门禁）。",
            "fix": "进一步优化换手率以提升评分。",
        },
        "self_correlation": {
            "name": "自相关 < 0.70",
            "meaning": "PnL 自相关。过高表明 Alpha 可能过拟合或表现不稳定。",
            "fix": "简化表达式、增加 OOS 验证、避免过度参数化。",
        },
        "prod_correlation": {
            "name": "产品相关 < 0.70",
            "meaning": "与已有产品 Alpha 的相关性。过高会被 BRAIN 拒绝。",
            "fix": "改变算子组合或使用不同的数据字段族。",
        },
        "weight_concentration": {
            "name": "权重集中度 ≤ 10%",
            "meaning": "单只股票最大权重。超过 10% 会被 BRAIN 拒绝。",
            "fix": "添加分散化约束或使用 group_neutralize。",
        },
        "sub_universe_sharpe": {
            "name": "子域夏普比率",
            "meaning": "在子域（如中小盘）中的表现。低于阈值说明泛化能力不足。",
            "fix": "增加跨市场验证或选择更通用的因子。",
        },
        "expression_valid": {
            "name": "表达式语法有效",
            "meaning": "表达式是否能在 BRAIN 平台正确解析。",
            "fix": "检查算子名称、括号匹配、字段是否存在。",
        },
    }

    info = descriptions.get(check_name)
    if info:
        return info
    return {
        "name": check_name,
        "meaning": "质量检查项",
        "fix": "请查看评分详情了解具体不通过原因。",
    }


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
        "description": "从 BRAIN 平台同步已提交的 Alpha 列表。首次运行建议使用 7d 范围。",
        "action": "选择同步范围后点击「开始同步」。进度会通过进度条和事件日志展示。",
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


def format_gate_failure(failure: str) -> dict[str, str]:
    """Format a gate failure reason into user-friendly terms."""
    parts = failure.split(" ", 1)
    check_name = parts[0].rstrip(":") if parts else failure

    info = translate_check_result(check_name)

    return {
        "check": check_name,
        "friendly_name": info["name"],
        "meaning": info["meaning"],
        "fix": info["fix"],
        "raw": failure,
    }
