"""User-facing error messages with improved readability and actionable guidance.

Provides structured, human-readable error messages for both CLI and Web UI.
Each error has:
- A Chinese-readable title
- An English technical detail
- An actionable suggestion
- A severity level
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class UserMessage:
    """Structured user-facing message with actionable guidance."""
    title: str           # Chinese human-readable title
    detail: str          # English technical detail
    suggestion: str      # Actionable next step
    severity: str        # "error" | "warning" | "info"
    error_code: str = ""


# ═══════════════════════════════════════════════════════════════════════
# Pre-defined message catalog
# ═══════════════════════════════════════════════════════════════════════

MESSAGE_CATALOG: dict[str, UserMessage] = {
    # ── Authentication ──
    "AUTH_FAILED": UserMessage(
        title="认证失败",
        detail="BRAIN API authentication failed. Verify your username/password or token.",
        suggestion="请检查环境变量 BRAIN_USERNAME / BRAIN_PASSWORD 或 BRAIN_TOKEN 是否正确设置。"
                  "运行 'brain-alpha-ops init-config' 可查看配置示例。",
        severity="error",
        error_code="AUTH_FAILED",
    ),
    "AUTH_REQUIRED": UserMessage(
        title="需要认证",
        detail="Web session is expired or invalid. Please re-authenticate.",
        suggestion="请刷新页面重新登录。如果问题持续，请检查 Web 服务是否仍在运行。",
        severity="error",
        error_code="AUTH_REQUIRED",
    ),

    # ── Validation ──
    "VALIDATION_FAILED": UserMessage(
        title="表达式验证失败",
        detail="BRAIN API rejected the expression during pre-submit validation.",
        suggestion="请检查表达式的字段名和算子名是否均为 BRAIN 官方支持的拼写。"
                  "查看 data/official_fields.json 和 data/official_operators.json。",
        severity="error",
        error_code="VALIDATION_FAILED",
    ),
    "EXPRESSION_EMPTY": UserMessage(
        title="表达式为空",
        detail="Alpha expression must not be empty.",
        suggestion="请输入一个有效的 FASTEXPR 表达式，例如: rank(ts_delta(close, 10))",
        severity="error",
        error_code="EXPRESSION_EMPTY",
    ),
    "EXPRESSION_UNBALANCED_PARENS": UserMessage(
        title="括号不匹配",
        detail="Expression has unbalanced parentheses — '(' and ')' counts differ.",
        suggestion="请检查表达式中的括号是否都已正确闭合。每个 '(' 需要对应的 ')'。",
        severity="error",
        error_code="EXPRESSION_UNBALANCED_PARENS",
    ),
    "EXPRESSION_UNKNOWN_OPERATOR": UserMessage(
        title="未知算子",
        detail="Expression uses an operator not found in the BRAIN operator list.",
        suggestion="请使用 BRAIN 平台支持的算子。运行 'brain-alpha-ops list-context --operators' 查看完整算子列表。",
        severity="error",
        error_code="EXPRESSION_UNKNOWN_OPERATOR",
    ),
    "EXPRESSION_NO_FIELDS": UserMessage(
        title="未检测到数据字段",
        detail="No known BRAIN data fields found in the expression.",
        suggestion="表达式需要包含至少一个 BRAIN 数据字段（如 close, volume, vwap 等）。",
        severity="warning",
        error_code="EXPRESSION_NO_FIELDS",
    ),
    "EXPRESSION_NULL_BYTES": UserMessage(
        title="表达式包含非法字符",
        detail="Expression contains null bytes or non-printable characters.",
        suggestion="请去除表达式中的非法字符后重试。",
        severity="error",
        error_code="EXPRESSION_NULL_BYTES",
    ),
    "EXPRESSION_LONG": UserMessage(
        title="表达式过长",
        detail="Expression exceeds 250 characters; BRAIN may have trouble compiling.",
        suggestion="考虑拆分为多个简单 Alpha，或使用更简洁的函数组合。",
        severity="warning",
        error_code="EXPRESSION_LONG",
    ),

    # ── Simulation / Backtest ──
    "SIMULATION_FAILED": UserMessage(
        title="官方回测失败",
        detail="BRAIN API simulation completed with FAILED status.",
        suggestion="请检查：1) 表达式语法是否正确 2) 字段和算子是否在当前数据集中可用 "
                  "3) 设置是否合法（region, universe, delay 等）。",
        severity="error",
        error_code="SIMULATION_FAILED",
    ),
    "SIMULATION_TIMEOUT": UserMessage(
        title="回测超时",
        detail="BRAIN simulation did not complete within the expected timeframe.",
        suggestion="BRAIN 回测队列可能较长，请稍后重试或减少并发的回测数量。",
        severity="error",
        error_code="SIMULATION_TIMEOUT",
    ),
    "CONCURRENT_SIMULATION_LIMIT": UserMessage(
        title="并发回测超限",
        detail="BRAIN concurrent simulation limit exceeded. Your account-level cap was reached.",
        suggestion="当前并发回测数已达账户上限。请等待已有回测完成后再提交新的回测。"
                  "可在 Web 控制台的 '运行状态' 面板查看当前并发数。",
        severity="warning",
        error_code="CONCURRENT_SIMULATION_LIMIT",
    ),

    # ── Pre-submit / Gate ──
    "HARD_GATE_BLOCKED": UserMessage(
        title="硬性门禁未通过",
        detail="Alpha failed one or more BRAIN official hard gates (LOW_SHARPE, LOW_FITNESS, HIGH_TURNOVER, etc.).",
        suggestion="请在评分面板查看详细失败项，针对低分项优化后重新回测。"
                  "重点关注：Sharpe > 1.25, Fitness > 1.0, Turnover < 70%。",
        severity="error",
        error_code="HARD_GATE_BLOCKED",
    ),
    "SUBMIT_BLOCKED": UserMessage(
        title="提交被阻止",
        detail="Alpha submission was blocked by safety gate — duplicate, not ready, or config policy.",
        suggestion="请先完成所有检查项，确保状态为 'SUBMISSION_READY' 后再尝试提交。"
                  "检查云端是否已有相同表达式。",
        severity="error",
        error_code="SUBMIT_BLOCKED",
    ),
    "MISSING_OFFICIAL_ID": UserMessage(
        title="缺少官方 Alpha ID",
        detail="Alpha has no official_alpha_id — run BRAIN simulation first.",
        suggestion="请先在 Web 控制台的 '生成 & 回测' 页面提交官方回测，"
                  "获取 official_alpha_id 后再进行后续操作。",
        severity="error",
        error_code="MISSING_OFFICIAL_ID",
    ),

    # ── Connectivity ──
    "CONNECTION_FAILED": UserMessage(
        title="无法连接 BRAIN API",
        detail="Network connection to api.worldquantbrain.com failed.",
        suggestion="请检查：1) 网络是否连通 2) 是否需要 VPN 3) BRAIN API 服务是否正常。"
                  "也可尝试在 Web 控制台点击 '测试连接'。",
        severity="error",
        error_code="CONNECTION_FAILED",
    ),
    "RATE_LIMITED": UserMessage(
        title="API 访问频率超限",
        detail="BRAIN API rate limit exceeded. Please wait before sending more requests.",
        suggestion="请等待 1-2 分钟后重试。建议减少并发请求数，或在 run_config.json 中增加 "
                  "min_request_interval_seconds 的值。",
        severity="warning",
        error_code="RATE_LIMITED",
    ),
    "CONTEXT_REFRESH_FAILED": UserMessage(
        title="字段/算子上下文刷新失败",
        detail="Failed to refresh fields/operators context from BRAIN API.",
        suggestion="将使用本地缓存数据。如需更新，请运行 'fetch_official_context.py' 或"
                  "在 Web 控制台点击 '同步云端数据'。",
        severity="warning",
        error_code="CONTEXT_REFRESH_FAILED",
    ),

    # ── Configuration ──
    "CONFIG_VALIDATION_ERROR": UserMessage(
        title="配置验证失败",
        detail="run_config.json contains invalid or unsupported values for BRAIN settings.",
        suggestion="请检查 run_config.json 中的字段值是否符合 BRAIN 平台允许的范围。"
                  "运行 'brain-alpha-ops validate-config' 获取详细错误。",
        severity="error",
        error_code="CONFIG_VALIDATION_ERROR",
    ),
    "DATASET_NOT_FOUND": UserMessage(
        title="数据集未找到",
        detail="Specified dataset_id is not available in the current context.",
        suggestion="运行 'brain-alpha-ops list-context --datasets' 查看可用数据集列表。"
                  "确保已在 Web 控制台或 CLI 中同步了官方上下文。",
        severity="error",
        error_code="DATASET_NOT_FOUND",
    ),
    "UNKNOWN_TOOL": UserMessage(
        title="未知操作",
        detail="The requested operation is not recognized by the system.",
        suggestion="请检查操作名称是否正确。可用操作请参阅 README.md 或 Web 控制台帮助。",
        severity="error",
        error_code="UNKNOWN_TOOL",
    ),

    # ── Operational ──
    "JOBS_FULL": UserMessage(
        title="任务队列已满",
        detail="Maximum concurrent active jobs reached. Wait for current jobs to complete.",
        suggestion="请等待当前任务完成后再提交新任务。可在 '运行状态' 面板查看进行中的任务。",
        severity="warning",
        error_code="JOBS_FULL",
    ),
    "JOB_CANCELLED": UserMessage(
        title="任务已取消",
        detail="The job was cancelled by user request.",
        suggestion="任务已被取消。你可以随时重新开始。",
        severity="info",
        error_code="JOB_CANCELLED",
    ),
    "PIPELINE_COMPLETE": UserMessage(
        title="流水线完成",
        detail="Research pipeline completed all cycles successfully.",
        suggestion="查看结果面板获取生成的 Alpha 列表。可以筛选达标项进行提交。",
        severity="info",
        error_code="PIPELINE_COMPLETE",
    ),
}


def get_message(error_code: str, fallback_detail: str = "") -> UserMessage:
    """Look up a user-facing message by error code.

    Returns a pre-defined UserMessage if the code is recognized,
    otherwise a generic fallback message with the provided detail.
    """
    msg = MESSAGE_CATALOG.get(error_code)
    if msg is not None:
        return msg
    return UserMessage(
        title="操作异常",
        detail=fallback_detail or f"Unexpected error: {error_code}",
        suggestion="请查看日志获取更多信息，或联系开发人员。",
        severity="error",
        error_code=error_code,
    )


def classify_expression_error(exc: Exception, expression: str = "") -> dict[str, Any]:
    """Classify an expression-related error into a user-friendly payload.

    Returns a dict compatible with web JSON error responses.
    """
    text = str(exc).lower()
    msg = get_message("VALIDATION_FAILED")

    if not expression or not expression.strip():
        msg = get_message("EXPRESSION_EMPTY")
    elif expression.count("(") != expression.count(")"):
        msg = get_message("EXPRESSION_UNBALANCED_PARENS")
    elif "unknown operator" in text or "operator" in text:
        msg = get_message("EXPRESSION_UNKNOWN_OPERATOR")
        msg.detail = str(exc)
    elif "empty" in text:
        msg = get_message("EXPRESSION_EMPTY")
    elif "\x00" in expression:
        msg = get_message("EXPRESSION_NULL_BYTES")

    return {
        "ok": False,
        "error_code": msg.error_code,
        "error": {"title": msg.title, "detail": msg.detail, "suggestion": msg.suggestion, "severity": msg.severity},
    }


def web_actionable_error(error_code: str, detail: str = "", context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Web-friendly error response with actionable next steps.

    Usage in web handlers:
        return web_actionable_error("AUTH_FAILED", str(exc))
    """
    msg = get_message(error_code, fallback_detail=detail)
    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
        "error": {
            "title": msg.title,
            "detail": msg.detail if detail else msg.detail,
            "suggestion": msg.suggestion,
            "severity": msg.severity,
        },
    }
    if context:
        payload["context"] = context
    return payload
