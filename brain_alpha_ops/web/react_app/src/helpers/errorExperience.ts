import { isRecord } from "@/types";

export interface ApiUserError {
  kind?: string;
  title?: string;
  message?: string;
  impact?: string;
  suggested_action?: string;
  action_label?: string;
  next_action?: string;
  severity?: string;
  recoverable?: boolean;
  retryable?: boolean;
  detail?: string;
}

export interface ApiErrorExperiencePayload {
  error?: string;
  error_code?: string;
  status_code?: string;
  status?: string;
  phase?: string;
  user_error?: ApiUserError;
  user_error_kind?: string;
  user_message?: string;
  next_action?: string;
  recoverable?: boolean;
  retryable?: boolean;
  progress?: ApiErrorExperiencePayload;
  data?: ApiErrorExperiencePayload;
}

export const RAW_UNSAFE_DISPLAY_TEXT_PATTERN = /(?:raw\s+backend|raw_backend|RAW_BACKEND|SESSION_INVALID|session_invalid|invalid local session|traceback|exception|stack trace|csrf[_-]?token|session[_-]?id|access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|password|passwd|pwd|token=|password=|api_key=|csrf_token=)/i;

const SESSION_INVALID_VALUES = new Set(["session_invalid", "invalid local session", "session_expired"]);

export function userErrorFromPayload(payload: ApiErrorExperiencePayload | null | undefined): ApiUserError | null {
  if (!payload || typeof payload.user_error !== "object" || payload.user_error === null) return null;
  return payload.user_error;
}

export function apiErrorMessage(
  payload: ApiErrorExperiencePayload | null | undefined,
  fallback = "Request failed",
): string {
  if (!payload) return fallback;
  const userError = userErrorFromPayload(payload);
  const progress = payload?.progress;
  const data = payload?.data;
  const userErrorMessage = safeUserFacingText(userError?.message);
  if (userErrorMessage) return userErrorMessage;
  const userMessage = safeUserFacingText(payload?.user_message);
  if (userMessage) return userMessage;
  const knownRawMessage =
    knownApiErrorMessage(payload?.error) ||
    knownApiErrorMessage(payload?.error_code) ||
    knownApiErrorMessage(payload?.status_code) ||
    knownApiErrorMessage(payload?.user_error_kind) ||
    knownApiErrorMessage(userError?.kind) ||
    apiErrorMessage(progress, "") ||
    apiErrorMessage(data, "");
  if (knownRawMessage) return knownRawMessage;
  return fallback;
}

export function safeDisplayErrorMessage(value: unknown, fallback = "请求失败，请稍后重试。"): string {
  const known = knownApiErrorMessage(value);
  if (known) return known;
  const text = String(value || "").trim();
  if (!text || unsafeBackendText(text)) return fallback;
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}

export function networkErrorMessage(err: unknown): string {
  if (err instanceof DOMException && err.name === "AbortError") {
    return "网络请求未在预期时间内返回，请刷新状态或稍后重试。";
  }
  if (err instanceof Error) {
    return knownApiErrorMessage(err.message) || "网络请求失败，请检查连接后重试。";
  }
  return knownApiErrorMessage(err) || "网络请求失败，请检查连接后重试。";
}

export function isSessionInvalidPayload(payload: unknown): boolean {
  return sessionInvalidValues(payload).some((value) => SESSION_INVALID_VALUES.has(value));
}

// P0-1: exact BRAIN error_code → Chinese translation map.
// Matched case-insensitively; covers every error_code the backend may
// emit directly (e.g. from web_errors._BRAIN_ERROR_TRANSLATIONS) plus
// codes that arrive via BRAIN's own API responses.
const _BRAIN_ERROR_CODE_MAP: Record<string, string> = {
  "auth_invalid": "认证失败，用户名或密码不正确。",
  "auth_bearer_invalid": "Bearer Token 无效，请重新连接。",
  "auth_token_expired": "登录已过期，请重新输入凭据。",
  "rate_limited": "BRAIN 平台限流，系统将自动重试，请稍候。",
  "network_timeout": "连接 BRAIN 平台超时，请检查网络后重试。",
  "brain_server_error": "BRAIN 平台服务异常，请稍后重试。",
  "connection_refused": "无法连接到 BRAIN 平台，请确认网络正常。",
  "concurrent_simulation_limit_exceeded": "BRAIN 回测并发槽位已满，系统将等待释放后自动重试。",
  "validation_error": "请求参数不合规，请检查输入后重试。",
  "connection_error": "连接 BRAIN 失败，请检查凭据和网络后重试。",
  "auth_required": "需要重新登录，请刷新页面或重新输入凭据。",
  "session_expired": "本地会话已失效，请重新连接后继续。",
  "admin_auth_required": "远程 Web 访问需要管理员认证。",
  // Fix 6: Additional common error codes for Chinese coverage
  "internal_server_error": "服务器内部错误，请稍后重试或联系管理员。",
  "bad_gateway": "上游 BRAIN 服务暂时不可用，请稍后重试。",
  "service_unavailable": "服务暂时不可用，正在恢复中，请稍后重试。",
  "request_timeout": "请求处理超时，BRAIN 平台仍在处理中，请稍后重试。",
  "too_many_requests": "请求过于频繁，请等待片刻后再试。",
  "invalid_credentials": "凭据无效，请检查用户名和密码后重新测试连接。",
  "missing_credentials": "缺少连接凭据，请填写账户邮箱和密码或 API Token。",
  "sync_failed": "云端同步失败，请检查网络后手动重试。",
  "sync_timeout": "云端同步超时，建议缩小同步范围后重试。",
  "cache_unavailable": "本地缓存不可用，请先完成首次同步或检查本地数据目录。",
  "config_invalid": "配置无效，请检查生产参数后重新保存。",
  "job_already_running": "已有验证任务在运行，请等待当前任务完成或手动停止后再启动。",
  "job_start_failed": "验证任务启动失败，请检查配置和连接后重试。",
  "sse_connection_failed": "实时进度连接失败，系统将自动重试。",
  "sse_timeout": "实时进度连接超时，请检查网络后刷新页面。",
  "backtest_failed": "回测请求失败，BRAIN 平台可能暂时繁忙，请稍后重试。",
  "backtest_timeout": "回测请求超时，BRAIN 平台处理时间较长，系统将继续等待。",
};

// P1-4: backend next_action → frontend action label.
// The backend web_state_contract._ERROR_DEFINITIONS defines a
// ``next_action`` for each error kind.  This table maps those
// snake_case action names to a human-readable Chinese button label.
const _NEXT_ACTION_LABELS: Record<string, string> = {
  "reconnect_session": "重新连接",
  "refresh_cache": "刷新缓存",
  "wait_and_retry": "重试",
  "check_config": "检查配置",
  "review_official_slots": "查看回测槽位",
  "refresh_capabilities": "刷新能力集",
  "fix_expression": "查看候选",
  "refresh_status": "刷新状态",
  "restart_flow": "重新启动",
  "review_active_job": "查看任务",
  "review_warnings": "查看警告",
  "resume_or_restart": "恢复流程",
  "inspect_error": "查看详情",
  "retry_operation": "重试",
  "monitor_or_cancel": "查看或停止",
  "review_results": "查看结果",
};

/** Get a human-readable Chinese label for a next_action enum value. */
export function nextActionLabel(nextAction: string | null | undefined): string | null {
  if (!nextAction) return null;
  return _NEXT_ACTION_LABELS[nextAction] ?? null;
}

export function knownApiErrorMessage(value: unknown): string | null {
  const text = String(value || "").trim();
  if (!text) return null;
  const normalized = text.toLowerCase();

  // P0-1: exact error_code match (highest priority, before regex/pattern checks).
  const codeTranslation = _BRAIN_ERROR_CODE_MAP[normalized];
  if (codeTranslation) return codeTranslation;

  const httpMatch = text.match(/^HTTP[_\s-]?(\d{3})\b/i);
  if (httpMatch) {
    const status = httpMatch[1];
    if (status === "429") return "BRAIN 官方接口请求过于频繁，请稍后重试。";
    if (status === "401" || status === "403") return "BRAIN 连接已失效，请重新测试连接后继续。";
    if (status === "408") return "BRAIN 官方接口响应超时，请稍后重试。";
    if (status === "500" || status === "502" || status === "503" || status === "504") {
      return `BRAIN 官方接口暂时不可用（HTTP ${status}），请稍后重试。`;
    }
  }
  // P2-2 [C8]: removed "connection aborted" — user-initiated AbortController.abort() is not a network fault
  if (/network\s*error|urlopen error|connection reset|remote end closed/i.test(text)) {
    return "网络连接异常，无法读取 BRAIN 官方接口。请检查网络后重试。";
  }
  if (SESSION_INVALID_VALUES.has(normalized)) {
    return "本地会话已失效，请重新连接后继续。";
  }
  if (normalized === "job_not_found" || normalized === "unknown job" || normalized === "unknown sync job") {
    return "找不到本次任务，请刷新状态或重新启动流程。";
  }
  if (normalized === "rate_limited" || normalized === "official_rate_limited") {
    return "BRAIN 官方接口请求过于频繁，请稍后重试。";
  }
  if (normalized === "web_rate_limited") {
    return "本地页面请求过于频繁，请稍后重试。";
  }
  if (normalized === "concurrent_simulation_limit_exceeded" || normalized.includes("concurrent simulation limit")) {
    return "官方模拟并发槽位已满，请等待当前回测结束后再重试。";
  }
  if (normalized === "raw backend cancellation" || normalized === "task_cancelled") {
    return "验证流程已停止，结果未确认完成。";
  }
  if (normalized === "backend did not confirm stop" || normalized === "stop_failed") {
    return "停止请求未确认，后台状态仍需重新读取。";
  }
  if (normalized === "official_context_refresh_timeout" || normalized === "official context timeout") {
    return "官方上下文刷新超时，请稍后重试。";
  }
  if (normalized.startsWith("web flow watchdog stopped this task after no clear progress update")) {
    return "Web 流程长时间没有明确进度，已自动停止并请求中断。";
  }
  if (/timed out|timeout/i.test(text)) {
    return "请求超时，BRAIN 官方接口仍未返回。请稍后重试或缩小同步范围。";
  }
  return null;
}

function unsafeBackendText(text: string): boolean {
  if (/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/.test(text)) {
    return true;
  }
  if (/\b(?:Basic|Bearer)\s+[A-Za-z0-9._~+/=-]+/i.test(text)) {
    return true;
  }
  if (/(?:raw\s+backend|raw_backend|traceback|stack trace|session_invalid|invalid local session)/i.test(text)) {
    return true;
  }
  // P2-3 [C9]: require 8+ chars of value after colon/equal to avoid false-flagging short messages
  if (/(?:password|passwd|pwd|token|csrf(?:[-_\s]?token)?|cookie|set[-_\s]?cookie|authorization|api[-_\s]?key|client[-_\s]?secret|access[-_\s]?token|refresh[-_\s]?token|id[-_\s]?token|session(?:[-_\s]?(?:id|key|token))?)\s*[:=]\s*[A-Za-z0-9._~+\/=-]{8,}/i.test(text)) {
    return true;
  }
  if (/^[A-Z][A-Z0-9_]{8,}(?:\b|$)/.test(text)) {
    return true;
  }
  return false;
}

function safeUserFacingText(value: unknown): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text || unsafeBackendText(text)) return "";
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}

function sessionInvalidValues(payload: unknown): string[] {
  if (payload == null) return [];
  if (typeof payload === "string") return [payload.trim().toLowerCase()].filter(Boolean);
  if (Array.isArray(payload)) return payload.flatMap((item) => sessionInvalidValues(item));
  if (!isRecord(payload)) return [];
  const rec = payload;
  const values = [
    rec.error,
    rec.error_code,
    rec.user_error_kind,
    rec.status_code,
    rec.status,
    rec.phase,
  ];
  const userError = rec.user_error;
  if (isRecord(userError)) {
    values.push(userError.kind);
  }
  return [
    ...values.map((value) => String(value || "").trim().toLowerCase()).filter(Boolean),
    ...sessionInvalidValues(rec.progress),
    ...sessionInvalidValues(rec.data),
  ];
}
