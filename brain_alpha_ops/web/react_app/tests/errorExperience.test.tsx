import { describe, expect, it } from "vitest";
import { apiErrorMessage, isSessionInvalidPayload, knownApiErrorMessage, networkErrorMessage, safeDisplayErrorMessage } from "@/helpers/errorExperience";

const REDACTED_SECRET_PLACEHOLDER = "REDACTED_SECRET_PLACEHOLDER";
const REDACTION_FIXTURE_EMAIL = "analyst" + "@example.test";
const MIRRORED_REDACTION_FIXTURE_CORPUS = [
  { label: "token", rawText: "token=" + REDACTED_SECRET_PLACEHOLDER + "_TOKEN" },
  { label: "api_key", rawText: "apiKey=" + REDACTED_SECRET_PLACEHOLDER + "_API_KEY" },
  { label: "password", rawText: "password=" + REDACTED_SECRET_PLACEHOLDER + "_PASSWORD" },
  { label: "csrf", rawText: "csrfToken=" + REDACTED_SECRET_PLACEHOLDER + "_CSRF" },
  { label: "auth_header", rawText: "Authorization: Bearer " + REDACTED_SECRET_PLACEHOLDER + "_AUTH" },
  { label: "email", rawText: "email=" + REDACTION_FIXTURE_EMAIL },
  { label: "session", rawText: "sessionId=" + REDACTED_SECRET_PLACEHOLDER + "_SESSION" },
] as const;

function fixtureText(label: typeof MIRRORED_REDACTION_FIXTURE_CORPUS[number]["label"]): string {
  const fixture = MIRRORED_REDACTION_FIXTURE_CORPUS.find((item) => item.label === label);
  if (!fixture) throw new Error(`Missing mirrored redaction fixture: ${label}`);
  return fixture.rawText;
}

describe("errorExperience", () => {
  it("prefers structured user_error messages over raw backend fields", () => {
    expect(apiErrorMessage({
      error_code: "SESSION_INVALID",
      error: "invalid local session",
      user_error: { message: "请重新连接后继续。" },
    })).toBe("请重新连接后继续。");
  });

  it("prefers AF-018 user_message metadata over raw backend fields", () => {
    expect(apiErrorMessage({
      error_code: "SESSION_INVALID",
      error: "invalid local session",
      user_message: "本地连接状态已过期，请重新连接后继续。",
      next_action: "reconnect_session",
      recoverable: true,
      retryable: true,
    })).toBe("本地连接状态已过期，请重新连接后继续。");
  });

  it("maps known raw backend/session codes to safe user-facing copy", () => {
    expect(apiErrorMessage({ error_code: "SESSION_INVALID", error: "invalid local session" }))
      .toBe("本地会话已失效，请重新连接后继续。");
    expect(apiErrorMessage({ error_code: "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" }))
      .toBe("官方模拟并发槽位已满，请等待当前回测结束后再重试。");
    expect(apiErrorMessage({ error: "raw backend cancellation" }))
      .toBe("验证流程已停止，结果未确认完成。");
    expect(apiErrorMessage({ error: "backend did not confirm stop" }))
      .toBe("停止请求未确认，后台状态仍需重新读取。");
    expect(apiErrorMessage({ error_code: "JOB_NOT_FOUND", error: "unknown job" }))
      .toBe("找不到本次任务，请刷新状态或重新启动流程。");
    expect(apiErrorMessage({ error: "unknown sync job" }))
      .toBe("找不到本次任务，请刷新状态或重新启动流程。");
  });

  it("falls through blank structured messages to safer known codes", () => {
    expect(apiErrorMessage({
      error_code: "JOB_NOT_FOUND",
      user_error: { message: "  " },
    })).toBe("找不到本次任务，请刷新状态或重新启动流程。");
  });

  it("fails closed when structured user messages contain sensitive text", () => {
    const fallback = "安全兜底";
    expect(apiErrorMessage({
      error_code: "UNMAPPED_BACKEND_ERROR",
      user_error: { message: fixtureText("token") },
    }, fallback)).toBe(fallback);
    expect(apiErrorMessage({
      user_message: fixtureText("auth_header"),
    }, fallback)).toBe(fallback);
    expect(apiErrorMessage({
      user_error_kind: "session_expired",
      user_error: { message: fixtureText("csrf") },
    }, fallback)).toBe("本地会话已失效，请重新连接后继续。");
  });

  it.each(MIRRORED_REDACTION_FIXTURE_CORPUS)(
    "fails closed for mirrored shared redaction fixture $label",
    ({ rawText }) => {
      const fallback = "安全兜底";

      expect(apiErrorMessage({ user_error: { message: rawText } }, fallback)).toBe(fallback);
      expect(apiErrorMessage({ user_message: rawText }, fallback)).toBe(fallback);
      expect(safeDisplayErrorMessage(rawText, fallback)).toBe(fallback);
    },
  );

  it("detects session-invalid payloads nested under progress and data", () => {
    expect(isSessionInvalidPayload({ progress: { status_code: "SESSION_INVALID" } })).toBe(true);
    expect(isSessionInvalidPayload({ data: { user_error: { kind: "session_expired" } } })).toBe(true);
    expect(isSessionInvalidPayload({ error_code: "JOB_NOT_FOUND" })).toBe(false);
    expect(apiErrorMessage({ progress: { status_code: "SESSION_INVALID" } }))
      .toBe("本地会话已失效，请重新连接后继续。");
  });

  it("maps common HTTP and network backend strings to safe user-facing copy", () => {
    expect(apiErrorMessage({ error: "HTTP 429: rate limited" }))
      .toBe("BRAIN 官方接口请求过于频繁，请稍后重试。");
    expect(apiErrorMessage({ error: "HTTP 403: forbidden" }))
      .toBe("BRAIN 连接已失效，请重新测试连接后继续。");
    expect(apiErrorMessage({ error: "HTTP 503: service unavailable" }))
      .toBe("BRAIN 官方接口暂时不可用（HTTP 503），请稍后重试。");
    expect(apiErrorMessage({ error: "urlopen error connection reset" }))
      .toBe("网络连接异常，无法读取 BRAIN 官方接口。请检查网络后重试。");
    expect(apiErrorMessage({ error: "NetworkError when attempting to fetch resource." }))
      .toBe("网络连接异常，无法读取 BRAIN 官方接口。请检查网络后重试。");
    expect(apiErrorMessage({ error: "Web flow watchdog stopped this task after no clear progress update." }))
      .toBe("Web 流程长时间没有明确进度，已自动停止并请求中断。");
    expect(apiErrorMessage({ error: "request timed out" }))
      .toBe("请求超时，BRAIN 官方接口仍未返回。请稍后重试或缩小同步范围。");
  });

  it("keeps standalone network errors user-facing and fail-closed", () => {
    expect(networkErrorMessage(new Error("HTTP 503: service unavailable")))
      .toBe("BRAIN 官方接口暂时不可用（HTTP 503），请稍后重试。");
    expect(networkErrorMessage(new Error("Traceback: private worker path /tmp/session")))
      .toBe("网络请求失败，请检查连接后重试。");
  });

  it("uses fallback copy for unknown backend diagnostic errors", () => {
    expect(apiErrorMessage({ error: "new backend failure" }, "fallback"))
      .toBe("fallback");
    expect(apiErrorMessage({ error_code: "UNMAPPED_BACKEND_ERROR" }, "fallback"))
      .toBe("fallback");
    expect(knownApiErrorMessage("not_known_yet")).toBeNull();
  });

  it("fails closed when app shell display receives raw backend or secret-shaped text", () => {
    const fallback = "安全占位";
    expect(safeDisplayErrorMessage("raw backend worker failed " + fixtureText("password"), fallback)).toBe(fallback);
    expect(safeDisplayErrorMessage("Traceback: private /tmp/session " + fixtureText("token"), fallback)).toBe(fallback);
    expect(safeDisplayErrorMessage(fixtureText("email"), fallback)).toBe(fallback);
    expect(safeDisplayErrorMessage(fixtureText("auth_header"), fallback)).toBe(fallback);
    expect(safeDisplayErrorMessage(fixtureText("csrf"), fallback)).toBe(fallback);
    expect(safeDisplayErrorMessage("RAW_BACKEND_STATUS", fallback)).toBe(fallback);
    expect(safeDisplayErrorMessage("HTTP 503: service unavailable", fallback))
      .toBe("BRAIN 官方接口暂时不可用（HTTP 503），请稍后重试。");
    expect(safeDisplayErrorMessage("本地服务暂不可达，请重试", fallback))
      .toBe("本地服务暂不可达，请重试");
  });
});
