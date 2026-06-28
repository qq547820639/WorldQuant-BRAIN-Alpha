import type { ApiResponse, UnifiedProgress } from '@/types';
import { classifyJobState } from '@/helpers/runPayload';
import { csrfHeaders } from '@/utils/csrf';

export type CancelReason =
  | 'sse_exhausted'
  | 'status_failed'
  | 'watchdog_failed'
  | 'ambiguous_state';

export interface CancelJobOptions {
  jobId: string;
  reason: CancelReason;
  message: string;
}

export interface CancelResultMessages {
  confirmed: string;
  missing: string;
  unconfirmed: string;
}

export interface CancelResultExperience {
  confirmed: boolean;
  missing: boolean;
  notifyType: 'warning' | 'error';
  message: string;
  progressPatch: Partial<UnifiedProgress>;
}

const JOB_CANCEL_ENDPOINT = '/api/cancel' as const;

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
    source: 'web',
  });
  return callCancelEndpoint(JOB_CANCEL_ENDPOINT, body);
}

export function isCancelConfirmed(result: ApiResponse | null | undefined): boolean {
  return result?.ok === true;
}

export function cancelResultEventMessage(result: ApiResponse | null | undefined): string {
  return cancelResultExperience(result, {
    confirmed: '已确认后台停止状态不明确的流程。',
    missing: '本地监控对象已找不到，请刷新状态或重新启动流程。',
    unconfirmed: '已请求自动中断，但后台取消未确认。',
  }).message;
}

export function cancelResultExperience(
  result: ApiResponse | null | undefined,
  messages: CancelResultMessages
): CancelResultExperience {
  const state = classifyJobState(result);
  if (state.missing) {
    return {
      confirmed: false,
      missing: true,
      notifyType: 'warning',
      message: messages.missing,
      progressPatch: {
        status: 'missing',
        status_kind: 'missing',
        terminal: true,
        recoverable: true,
        retryable: true,
      },
    };
  }
  if (isCancelConfirmed(result) && !state.failed) {
    return {
      confirmed: true,
      missing: false,
      notifyType: 'warning',
      message: messages.confirmed,
      progressPatch: {
        status: 'stopped',
        status_kind: 'interrupted',
        terminal: true,
        interrupted: true,
        recoverable: true,
        retryable: true,
      },
    };
  }
  return {
    confirmed: false,
    missing: false,
    notifyType: 'error',
    message: messages.unconfirmed,
    progressPatch: {
      status: 'failed',
      status_kind: 'failed',
      terminal: true,
      retryable: true,
    },
  };
}

// Match useApi's DEFAULT_REQUEST_TIMEOUT_MS (10 min) so cancel round-trips are
// not prematurely aborted relative to other API calls.
const CANCEL_REQUEST_TIMEOUT_MS = 600000;

async function callCancelEndpoint(
  endpoint: typeof JOB_CANCEL_ENDPOINT,
  body: string
): Promise<ApiResponse> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), CANCEL_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...csrfHeaders(),
      },
      body,
      signal: controller.signal,
    });
    // Response status check: on non-2xx, prefer a structured error payload
    // from the body; fall back to an HTTP status message.
    if (!response.ok) {
      const errorJson = await safeParseCancelJson(response);
      if (errorJson) {
        return { ...errorJson, ok: false };
      }
      return {
        ok: false,
        error_code: 'CANCEL_REQUEST_FAILED',
        error: `自动中断请求失败 (HTTP ${response.status}: ${response.statusText})。`,
      };
    }
    const json = await safeParseCancelJson(response);
    if (!json) {
      return {
        ok: false,
        error_code: 'CANCEL_REQUEST_FAILED',
        error: '自动中断响应解析失败，请刷新状态或稍后重试。',
      };
    }
    return { ...json, ok: json.ok !== false && !json.error && !json.error_code };
  } catch (err) {
    if (process.env.NODE_ENV === 'development') {
      console.error('jobCancel: network error for', endpoint, err);
    }
    const aborted =
      typeof DOMException !== 'undefined' &&
      err instanceof DOMException &&
      err.name === 'AbortError';
    return {
      ok: false,
      error_code: 'CANCEL_REQUEST_FAILED',
      error: aborted
        ? '自动中断请求超时，请刷新状态或稍后重试。'
        : '自动中断请求未确认，请刷新状态或稍后重试。',
    };
  } finally {
    window.clearTimeout(timeout);
  }
}

async function safeParseCancelJson(response: Response): Promise<ApiResponse | null> {
  try {
    return (await response.json()) as ApiResponse;
  } catch {
    return null;
  }
}
