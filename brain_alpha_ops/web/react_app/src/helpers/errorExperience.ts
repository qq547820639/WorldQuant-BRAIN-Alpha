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

export function knownApiErrorMessage(value: unknown): string | null {
  const text = String(value || "").trim();
  if (!text) return null;
  const normalized = text.toLowerCase();
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
  if (/network\s*error|urlopen error|connection reset|connection aborted|remote end closed/i.test(text)) {
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
  if (/(?:password|passwd|pwd|token|csrf(?:[-_\s]?token)?|cookie|set[-_\s]?cookie|authorization|api[-_\s]?key|client[-_\s]?secret|access[-_\s]?token|refresh[-_\s]?token|id[-_\s]?token|session(?:[-_\s]?(?:id|key|token))?)\s*[:=]/i.test(text)) {
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
  if (typeof payload !== "object") return [];

  const record = payload as Record<string, unknown>;
  const values = [
    record.error,
    record.error_code,
    record.user_error_kind,
    record.status_code,
    record.status,
    record.phase,
  ];
  const userError = record.user_error;
  if (userError && typeof userError === "object") {
    values.push((userError as Record<string, unknown>).kind);
  }
  return [
    ...values.map((value) => String(value || "").trim().toLowerCase()).filter(Boolean),
    ...sessionInvalidValues(record.progress),
    ...sessionInvalidValues(record.data),
  ];
}
