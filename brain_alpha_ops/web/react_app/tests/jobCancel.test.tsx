import { describe, expect, it } from "vitest";
import { cancelResultEventMessage, cancelResultExperience } from "@/api/jobCancel";

describe("jobCancel result experience", () => {
  const messages = {
    confirmed: "已确认停止。",
    missing: "监控对象已找不到，请刷新。",
    unconfirmed: "取消未确认。",
  };

  it("keeps confirmed cancellations as retry-safe warnings", () => {
    const experience = cancelResultExperience({ ok: true }, messages);

    expect(experience).toMatchObject({
      confirmed: true,
      missing: false,
      notifyType: "warning",
      message: "已确认停止。",
    });
  });

  it("maps missing job cancellation responses to monitor-blocked warnings", () => {
    const experience = cancelResultExperience({
      ok: false,
      error_code: "JOB_NOT_FOUND",
      error: "unknown job",
    }, messages);

    expect(experience).toMatchObject({
      confirmed: false,
      missing: true,
      notifyType: "warning",
      message: "监控对象已找不到，请刷新。",
    });
    expect(cancelResultEventMessage({ ok: false, error_code: "JOB_NOT_FOUND" }))
      .toBe("本地监控对象已找不到，请刷新状态或重新启动流程。");
  });

  it("keeps generic cancel failures as unconfirmed errors", () => {
    const experience = cancelResultExperience({
      ok: false,
      error_code: "CANCEL_REQUEST_FAILED",
      error: "network failed",
    }, messages);

    expect(experience).toMatchObject({
      confirmed: false,
      missing: false,
      notifyType: "error",
      message: "取消未确认。",
    });
  });

  it("does not promote ok true semantic failures to confirmed stops", () => {
    const experience = cancelResultExperience({
      ok: true,
      status: "failed",
      error: "already terminal",
    }, messages);

    expect(experience).toMatchObject({
      confirmed: false,
      missing: false,
      notifyType: "error",
      message: "取消未确认。",
      progressPatch: {
        status: "failed",
        status_kind: "failed",
        terminal: true,
        retryable: true,
      },
    });
  });
});
