"""User-friendly error message translation for common failure modes.

Split from the former ``brain_alpha_ops/ux/errors.py`` monolith
(deep-optimization-phase13). Maps raw technical error messages to
human-readable Chinese explanations with suggested remediation actions.
"""
from __future__ import annotations


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
