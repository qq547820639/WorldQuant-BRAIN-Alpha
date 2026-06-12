import { describe, expect, it } from "vitest";
import { classifyJobState, classifyProgressState, jobStatusMessage, resolveJobEventState } from "@/helpers/runPayload";

describe("runPayload job state contract", () => {
  it("treats interrupted status_kind as a terminal retryable state", () => {
    const state = classifyJobState({
      status: "running",
      status_kind: "interrupted",
      terminal: true,
      interrupted: true,
    });

    expect(state.terminal).toBe(true);
    expect(state.interrupted).toBe(true);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
    expect(state.successful).toBe(false);
  });

  it("treats interrupted payload flags as terminal even without a terminal flag", () => {
    const state = classifyJobState({
      status: "running",
      interrupted: true,
    });

    expect(state.terminal).toBe(true);
    expect(state.active).toBe(false);
    expect(state.interrupted).toBe(true);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
  });

  it.each(["stopped", "cancelled", "canceled"])("classifies %s as interrupted, not successful", (status) => {
    const state = classifyJobState({ status });

    expect(state.terminal).toBe(true);
    expect(state.interrupted).toBe(true);
    expect(state.successful).toBe(false);
    expect(state.retryable).toBe(true);
  });

  it("treats SESSION_INVALID status_code as missing and recoverable", () => {
    const state = classifyJobState({
      ok: false,
      progress: {
        status_code: "SESSION_INVALID",
      },
    });

    expect(state.terminal).toBe(true);
    expect(state.missing).toBe(true);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
  });

  it("classifies raw JOB_NOT_FOUND cancel responses as missing instead of generic failure", () => {
    const state = classifyJobState({
      ok: false,
      error_code: "JOB_NOT_FOUND",
      error: "unknown job",
    });

    expect(state.failed).toBe(false);
    expect(state.missing).toBe(true);
    expect(state.terminal).toBe(true);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
  });

  it("reads missing job semantics from user_error fields", () => {
    const state = classifyJobState({
      ok: false,
      user_error_kind: "job_not_found",
      user_error: {
        kind: "job_not_found",
        recoverable: true,
        retryable: true,
      },
    });

    expect(state.failed).toBe(false);
    expect(state.missing).toBe(true);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
  });

  it("reads nested progress and data error codes", () => {
    const fromProgress = classifyJobState({
      ok: false,
      progress: { error_code: "JOB_NOT_FOUND" },
    });
    const fromData = classifyJobState({
      ok: false,
      data: { user_error_kind: "job_not_found" },
    });

    expect(fromProgress.missing).toBe(true);
    expect(fromProgress.failed).toBe(false);
    expect(fromData.missing).toBe(true);
    expect(fromData.failed).toBe(false);
  });

  it("lets backend progress contract override the outer error lifecycle", () => {
    const state = classifyProgressState("error", {
      status: "stopped",
      status_kind: "interrupted",
      interrupted: true,
      terminal: true,
      percent_complete: 100,
    });

    expect(state.failed).toBe(false);
    expect(state.interrupted).toBe(true);
    expect(state.terminal).toBe(true);
    expect(state.successful).toBe(false);
  });

  it("keeps session invalid progress missing instead of folding it into generic failure", () => {
    const state = classifyProgressState("error", {
      phase: "session_invalid",
      status_code: "SESSION_INVALID",
      terminal: true,
    });

    expect(state.failed).toBe(false);
    expect(state.missing).toBe(true);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
  });

  it("treats watchdog failure as failed when progress provides only a phase", () => {
    const state = classifyProgressState("progress", {
      phase: "watchdog_failed",
      percent_complete: 100,
    });

    expect(state.failed).toBe(true);
    expect(state.terminal).toBe(true);
  });

  it("keeps completed_with_warnings as terminal warning progress", () => {
    const state = classifyProgressState("progress", {
      status: "completed_with_warnings",
      status_kind: "warning",
    });

    expect(state.warning).toBe(true);
    expect(state.successful).toBe(true);
    expect(state.terminal).toBe(true);
  });

  it("resolves terminal SSE errors through one failed outcome", () => {
    const outcome = resolveJobEventState({
      type: "error",
      user_error: { message: "后台状态读取失败，请重试。" },
    }, null, { failed: "验证流程错误" });

    expect(outcome.terminal).toBe(true);
    expect(outcome.kind).toBe("failed");
    expect(outcome.notifyType).toBe("error");
    expect(outcome.nextStatus).toBe("failed");
    expect(outcome.message).toBe("后台状态读取失败，请重试。");
  });

  it("gives interrupted terminal outcomes priority over generic failed payloads", () => {
    const outcome = resolveJobEventState({
      ok: false,
      type: "error",
      status: "stopped",
      status_kind: "interrupted",
      interrupted: true,
      error: "raw backend cancellation",
    }, null, {
      failed: "验证流程错误",
      interrupted: "验证流程已停止，结果未确认完成。",
    });

    expect(outcome.terminal).toBe(true);
    expect(outcome.kind).toBe("interrupted");
    expect(outcome.notifyType).toBe("warning");
    expect(outcome.nextStatus).toBe("stopped");
    expect(outcome.message).toBe("验证流程已停止，结果未确认完成。");
  });

  it.each([
    { error: "raw backend cancellation" },
    { user_error: { kind: "task_cancelled" } },
    { user_error_kind: "task_interrupted" },
  ])("classifies error-kind-only interruption payloads as recoverable stops %#", (payload) => {
    const state = classifyJobState({
      ok: false,
      type: "error",
      ...payload,
    });

    expect(state.terminal).toBe(true);
    expect(state.interrupted).toBe(true);
    expect(state.failed).toBe(false);
    expect(state.recoverable).toBe(true);
    expect(state.retryable).toBe(true);
  });

  it("resolves error-kind-only interruption events before generic failures", () => {
    const outcome = resolveJobEventState({
      ok: false,
      type: "error",
      user_error_kind: "task_interrupted",
    }, null, {
      failed: "验证流程错误",
      interrupted: "验证流程已停止，结果未确认完成。",
    });

    expect(outcome.terminal).toBe(true);
    expect(outcome.kind).toBe("interrupted");
    expect(outcome.notifyType).toBe("warning");
    expect(outcome.nextStatus).toBe("stopped");
    expect(outcome.message).toBe("验证流程已停止，结果未确认完成。");
  });

  it("preserves warning completion outcomes for shared UI routing", () => {
    const outcome = resolveJobEventState({
      type: "complete",
      status: "completed_with_warnings",
      status_kind: "warning",
    }, null, { success: "验证流程已完成" });

    expect(outcome.terminal).toBe(true);
    expect(outcome.kind).toBe("success");
    expect(outcome.notifyType).toBe("warning");
    expect(outcome.nextStatus).toBe("completed_with_warnings");
    expect(outcome.message).toBe("验证流程已完成");
  });

  it("treats terminal warning status_kind as successful warning completion", () => {
    const outcome = resolveJobEventState({
      status: "running",
      status_kind: "warning",
      terminal: true,
    }, null, { success: "验证流程已完成" });

    expect(outcome.state.terminal).toBe(true);
    expect(outcome.state.warning).toBe(true);
    expect(outcome.state.successful).toBe(true);
    expect(outcome.kind).toBe("success");
    expect(outcome.notifyType).toBe("warning");
    expect(outcome.nextStatus).toBe("completed_with_warnings");
  });

  it("keeps unknown backend status messages out of terminal user copy", () => {
    expect(jobStatusMessage({
      status_message: "Traceback: private backend worker path /tmp/session",
      progress: {
        message: "raw backend worker detail",
      },
    }, "安全兜底文案")).toBe("安全兜底文案");
  });

  it("keeps unsafe structured backend messages out of terminal user copy", () => {
    expect(jobStatusMessage({
      user_error: {
        message: "auth failed for operator@example.test token=[placeholder]",
      },
    }, "安全兜底文案")).toBe("安全兜底文案");
    expect(jobStatusMessage({
      user_message: "Authorization: Bearer placeholder",
    }, "安全兜底文案")).toBe("安全兜底文案");
  });

  it("still maps known nested backend status messages to safe copy", () => {
    expect(jobStatusMessage({
      progress: {
        status_message: "HTTP 429: rate limited",
      },
    }, "安全兜底文案")).toBe("BRAIN 官方接口请求过于频繁，请稍后重试。");
  });
});
