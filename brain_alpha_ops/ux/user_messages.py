"""User-facing error messages with improved readability and actionable guidance.

Provides structured, human-readable error messages for the Web UI.
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
        suggestion="请在 BRAIN 账户连接区重新填写凭证并点击测试连接。"
                  "如仍失败，请让维护者检查托管凭证与网络状态。",
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
                  "可先在官方操作入口刷新官方能力集，再回到候选管理重新验证。",
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
        suggestion="请使用 BRAIN 平台支持的算子，并在 Web 控制台刷新官方能力集后重试。",
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
        suggestion="请等待 1-2 分钟后重试。若频繁出现，请在系统配置中降低并发或让维护者调整请求间隔。",
        severity="warning",
        error_code="RATE_LIMITED",
    ),
    "CONTEXT_REFRESH_FAILED": UserMessage(
        title="字段/算子上下文刷新失败",
        detail="Failed to refresh fields/operators context from BRAIN API.",
        suggestion="将使用本地缓存数据。如需更新，请在 Web 控制台点击官方操作里的刷新官方能力集。",
        severity="warning",
        error_code="CONTEXT_REFRESH_FAILED",
    ),

    # ── Configuration ──
    "CONFIG_VALIDATION_ERROR": UserMessage(
        title="配置验证失败",
        detail="The saved BRAIN settings contain invalid or unsupported values.",
        suggestion="请在系统配置页检查字段值是否符合 BRAIN 平台允许范围，并保存后重新验证。",
        severity="error",
        error_code="CONFIG_VALIDATION_ERROR",
    ),
    "DATASET_NOT_FOUND": UserMessage(
        title="数据集未找到",
        detail="Specified dataset_id is not available in the current context.",
        suggestion="请在 Web 控制台刷新官方能力集后，从系统配置中的官方数据集列表选择可用 Dataset。",
        severity="error",
        error_code="DATASET_NOT_FOUND",
    ),
    "UNKNOWN_TOOL": UserMessage(
        title="未知操作",
        detail="The requested operation is not recognized by the system.",
        suggestion="请回到状态卡选择可见入口；如入口不可用，请刷新页面后重试。",
        severity="error",
        error_code="UNKNOWN_TOOL",
    ),

    # ── Scoring / Gate ──
    "SCORE_INSUFFICIENT": UserMessage(
        title="评分未达到提交标准",
        detail="Alpha total score is below the configured submission threshold.",
        suggestion="请查看评分面板的归因树，针对低分维度优化表达式。"
                  "可尝试：增加经济概念多样性、添加风控算子、缩短窗口参数。",
        severity="warning",
        error_code="SCORE_INSUFFICIENT",
    ),
    "GATE_CONFIG_DEVIATION": UserMessage(
        title="门禁配置存在偏差",
        detail="Configured gates deviate from BRAIN official check specifications.",
        suggestion="请在系统配置页恢复官方门禁阈值，并在质量门禁页重新读取检查结果。",
        severity="error",
        error_code="GATE_CONFIG_DEVIATION",
    ),
    "API_DEVIATION_DETECTED": UserMessage(
        title="评分系统与官方 API 存在偏差",
        detail="Local scoring system output deviates from BRAIN official API results.",
        suggestion="请刷新官方能力集，并在可信环境重新运行官方仿真以获取最新官方指标。",
        severity="error",
        error_code="API_DEVIATION_DETECTED",
    ),

    # ── Data / Context ──
    "CONTEXT_STALE": UserMessage(
        title="BRAIN 上下文数据过期",
        detail="Official fields/operators/datasets cache is stale and may not reflect current BRAIN platform state.",
        suggestion="请在 Web 控制台点击官方操作里的刷新官方能力集，使用最新数据。",
        severity="warning",
        error_code="CONTEXT_STALE",
    ),
    "OFFICIAL_FIELDS_EMPTY": UserMessage(
        title="官方字段列表为空",
        detail="No official BRAIN fields are loaded.",
        suggestion="请在 Web 控制台刷新官方能力集；如刷新失败，请维护者检查 BRAIN API 连接。",
        severity="error",
        error_code="OFFICIAL_FIELDS_EMPTY",
    ),
    "OFFICIAL_OPERATORS_EMPTY": UserMessage(
        title="官方算子列表为空",
        detail="No official BRAIN operators are loaded.",
        suggestion="请在 Web 控制台刷新官方能力集；如刷新失败，请维护者检查 BRAIN API 连接。",
        severity="error",
        error_code="OFFICIAL_OPERATORS_EMPTY",
    ),

    # ── Threshold / Compliance ──
    "THRESHOLD_DRIFT_DETECTED": UserMessage(
        title="阈值与 BRAIN 官方不一致",
        detail="Some scoring thresholds in the configuration differ from BRAIN canonical values.",
        suggestion="请在系统配置页恢复官方阈值，并重新打开质量门禁确认偏差已消除。",
        severity="error",
        error_code="THRESHOLD_DRIFT_DETECTED",
    ),
    "DATASET_NOT_IN_OFFICIAL_CONTEXT": UserMessage(
        title="数据集不在官方上下文中",
        detail="The specified dataset_id was not found in official BRAIN datasets.",
        suggestion="请在官方操作入口刷新官方能力集，然后从系统配置里的官方数据集列表重新选择。",
        severity="error",
        error_code="DATASET_NOT_IN_OFFICIAL_CONTEXT",
    ),

    # ── Operational ──
    "JOBS_FULL": UserMessage(
        title="验证流程队列已满",
        detail="Maximum concurrent active jobs reached. Wait for current jobs to complete.",
        suggestion="请等待当前验证流程完成后再启动新的验证。可在运行总览查看进行中的流程。",
        severity="warning",
        error_code="JOBS_FULL",
    ),
    "JOB_CANCELLED": UserMessage(
        title="验证流程已取消",
        detail="The job was cancelled by user request.",
        suggestion="验证流程已被取消。你可以随时重新开始。",
        severity="info",
        error_code="JOB_CANCELLED",
    ),
    "PIPELINE_COMPLETE": UserMessage(
        title="流水线完成",
        detail="Research pipeline completed all cycles successfully.",
        suggestion="请在候选管理查看生成的 Alpha 列表，并在提交前就绪复核中查看阻断原因。",
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
        suggestion="请刷新当前页面后重试；如果问题持续，请让维护者查看诊断信息。",
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
