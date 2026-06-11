import type { ApiResponse } from "@/types";
import { csrfHeaders } from "@/utils/csrf";

export type CancelReason =
  | "sse_exhausted"
  | "status_failed"
  | "watchdog_failed"
  | "ambiguous_state";

export interface CancelJobOptions {
  jobId: string;
  reason: CancelReason;
  message: string;
}

const JOB_CANCEL_ENDPOINT = "/api/cancel" as const;

export async function requestJobCancel({
  jobId,
  reason,
  message,
}: CancelJobOptions): Promise<ApiResponse> {
  const body = JSON.stringify({
    job_id: jobId,
    task_id: jobId,
    reason,
    message,
    source: "web",
  });
  return callCancelEndpoint(JOB_CANCEL_ENDPOINT, body);
}

export function isCancelConfirmed(result: ApiResponse | null | undefined): boolean {
  return result?.ok === true;
}

export function cancelResultEventMessage(result: ApiResponse | null | undefined): string {
  return isCancelConfirmed(result)
    ? "已确认后台停止状态不明确的流程。"
    : "已请求自动中断，但后台取消未确认。";
}

async function callCancelEndpoint(endpoint: typeof JOB_CANCEL_ENDPOINT, body: string): Promise<ApiResponse> {
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...csrfHeaders(),
      },
      body,
    });
    const json = await response.json() as ApiResponse;
    return { ...json, ok: json.ok !== false && !json.error && !json.error_code };
  } catch (err) {
    if (process.env.NODE_ENV === "development") {
      console.error("jobCancel: network error for", endpoint, err);
    }
    return {
      ok: false,
      error_code: "CANCEL_REQUEST_FAILED",
      error: "自动中断请求未确认，请刷新状态或稍后重试。",
    };
  }
}
