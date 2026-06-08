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

const PRODUCTION_VALIDATION_STOP_ENDPOINT = "/api/production-validation/stop" as const;

export async function requestJobCancel({
  jobId,
  reason,
  message,
}: CancelJobOptions): Promise<ApiResponse | null> {
  const body = JSON.stringify({
    job_id: jobId,
    task_id: jobId,
    reason,
    message,
    source: "web",
  });
  return callCancelEndpoint(PRODUCTION_VALIDATION_STOP_ENDPOINT, body);
}

async function callCancelEndpoint(endpoint: typeof PRODUCTION_VALIDATION_STOP_ENDPOINT, body: string) {
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
    return null;
  }
}
