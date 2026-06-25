/** Shared helpers for job monitoring — used by both useJobState hook and JobMonitor component */

import {
  apiErrorMessage,
  knownApiErrorMessage,
  type ApiErrorExperiencePayload,
} from '@/helpers/errorExperience';
import type { BrainCredentials, JobStatus, ProgressLifecycle, UnifiedProgress } from '@/types';
import { isRecord } from '@/types';

type JobStateInput = {
  error?: unknown;
  error_code?: unknown;
  user_error?: unknown;
  user_error_kind?: unknown;
  status?: unknown;
  status_kind?: unknown;
  status_code?: unknown;
  state_label?: unknown;
  terminal?: unknown;
  active?: unknown;
  interrupted?: unknown;
  status_message?: unknown;
  phase?: unknown;
  type?: unknown;
  ok?: unknown;
  recoverable?: unknown;
  retryable?: unknown;
  progress?: unknown;
  data?: unknown;
};
type JobStateProgressInput = Record<string, unknown> | object | null | undefined;

export type JobStateClassification = {
  status: string;
  statusKind: string;
  terminal: boolean;
  active: boolean;
  successful: boolean;
  warning: boolean;
  failed: boolean;
  interrupted: boolean;
  missing: boolean;
  recoverable: boolean;
  retryable: boolean;
};

export type JobEventResolution = {
  state: JobStateClassification;
  kind: 'progress' | 'failed' | 'interrupted' | 'success';
  terminal: boolean;
  message: string;
  notifyType: 'success' | 'error' | 'warning';
  nextStatus: 'running' | 'failed' | 'stopped' | 'completed' | 'completed_with_warnings';
};

export type JobEventMessageOptions = {
  failed?: string;
  interrupted?: string;
  success?: string;
};

const TERMINAL_STATUSES = new Set([
  'completed',
  'completed_with_warnings',
  'success',
  'done',
  'failed',
  'error',
  'watchdog_failed',
  'stopped',
  'cancelled',
  'canceled',
  'interrupted',
  'missing',
  'session_invalid',
]);
const SUCCESS_STATUSES = new Set(['completed', 'completed_with_warnings', 'success', 'done']);
const WARNING_STATUSES = new Set(['completed_with_warnings', 'warning']);
const FAILED_STATUSES = new Set(['failed', 'error', 'watchdog_failed']);
const INTERRUPTED_STATUSES = new Set(['stopped', 'cancelled', 'canceled', 'interrupted']);
const INTERRUPTED_ERROR_KINDS = new Set([
  'job_cancelled',
  'job_canceled',
  'task_cancelled',
  'task_canceled',
  'task_interrupted',
  'job_interrupted',
  'raw backend cancellation',
  'task cancelled',
  'task canceled',
]);
const MISSING_STATUSES = new Set([
  'missing',
  'job_not_found',
  'unknown_job',
  'unknown job',
  'unknown sync job',
  'session_invalid',
  'invalid local session',
  'session_expired',
]);
const ACTIVE_STATUSES = new Set(['queued', 'running', 'progress', 'loading', 'stopping']);
const TERMINAL_STATUS_KINDS = new Set(['success', 'warning', 'failed', 'interrupted', 'missing']);

/** Check if credentials are filled in.
 *  P1-13 fix: the original `||` chain actually made password-only count as
 *  "having credentials" (contrary to the comment).  Switched to explicit
 *  AND for username+password so the BRAIN API (which requires at minimum a
 *  username) rejects password-only entries.  Token-only auth is still
 *  supported as an alternative to username+password. */
export function hasCredentials(credentials?: BrainCredentials): boolean {
  return Boolean(
    (credentials?.username?.trim() && credentials?.password) || credentials?.token?.trim()
  );
}

/** Check if job status is in a terminal (completed) state */
export function isTerminalStatus(status: string | undefined): boolean {
  return classifyJobState({ status }).terminal;
}

export function isSuccessfulStatus(status: string | undefined): boolean {
  return classifyJobState({ status }).successful;
}

export function isInterruptedStatus(status: string | undefined): boolean {
  return classifyJobState({ status }).interrupted;
}

export function normalizedJobStatus(value: unknown): string {
  return String(value || '')
    .trim()
    .toLowerCase();
}

export function jobStatusValue(
  payload: JobStateInput | null | undefined,
  progress?: JobStateProgressInput
): string {
  const payloadProgress = record(payload?.progress);
  const payloadData = record(payload?.data);
  const explicitProgress = record(progress);
  return normalizedJobStatus(
    payload?.status ||
      explicitProgress.status ||
      explicitProgress.phase ||
      payload?.phase ||
      payloadProgress.status ||
      payloadProgress.phase ||
      payloadData.status ||
      payloadData.phase
  );
}

export function classifyJobState(
  payload: JobStateInput | null | undefined,
  progress?: JobStateProgressInput
): JobStateClassification {
  const status = jobStatusValue(payload, progress);
  const payloadProgress = record(payload?.progress);
  const payloadData = record(payload?.data);
  const explicitProgress = record(progress);
  const payloadUserError = record(payload?.user_error);
  const explicitProgressUserError = record(explicitProgress.user_error);
  const payloadProgressUserError = record(payloadProgress.user_error);
  const payloadDataUserError = record(payloadData.user_error);
  const errorKinds = normalizedKindValues(
    payload?.status_code,
    payload?.error_code,
    payload?.user_error_kind,
    payloadUserError.kind,
    payload?.error,
    explicitProgress.status_code,
    explicitProgress.error_code,
    explicitProgress.user_error_kind,
    explicitProgressUserError.kind,
    explicitProgress.error,
    payloadProgress.status_code,
    payloadProgress.error_code,
    payloadProgress.user_error_kind,
    payloadProgressUserError.kind,
    payloadProgress.error,
    payloadData.status_code,
    payloadData.error_code,
    payloadData.user_error_kind,
    payloadDataUserError.kind,
    payloadData.error
  );
  const statusKind = normalizedJobStatus(
    payload?.status_kind ||
      explicitProgress.status_kind ||
      payloadProgress.status_kind ||
      payloadData.status_kind
  );
  const phase = normalizedJobStatus(
    payload?.phase ||
      payload?.status_code ||
      explicitProgress.phase ||
      explicitProgress.status_code ||
      payloadProgress.phase ||
      payloadProgress.status_code ||
      payloadData.phase ||
      payloadData.status_code
  );
  const type = normalizedJobStatus(payload?.type);
  const terminalFlag = truthyField(
    payload?.terminal,
    explicitProgress.terminal,
    payloadProgress.terminal,
    payloadData.terminal
  );
  const activeFlag = truthyField(
    payload?.active,
    explicitProgress.active,
    payloadProgress.active,
    payloadData.active
  );
  const interruptedFlag = truthyField(
    payload?.interrupted,
    explicitProgress.interrupted,
    payloadProgress.interrupted,
    payloadData.interrupted
  );
  const interrupted =
    interruptedFlag ||
    statusKind === 'interrupted' ||
    INTERRUPTED_STATUSES.has(status) ||
    INTERRUPTED_STATUSES.has(phase) ||
    errorKinds.some(isInterruptedKind);
  const missing =
    statusKind === 'missing' ||
    MISSING_STATUSES.has(status) ||
    MISSING_STATUSES.has(phase) ||
    errorKinds.some((value) => MISSING_STATUSES.has(value));
  const failed =
    statusKind === 'failed' ||
    FAILED_STATUSES.has(status) ||
    FAILED_STATUSES.has(phase) ||
    ((payload?.ok === false || type === 'error') && !interrupted && !missing);
  const warning = statusKind === 'warning' || WARNING_STATUSES.has(status);
  const successful =
    statusKind === 'success' || SUCCESS_STATUSES.has(status) || statusKind === 'warning';
  const terminal =
    terminalFlag ||
    TERMINAL_STATUSES.has(status) ||
    TERMINAL_STATUS_KINDS.has(statusKind) ||
    failed ||
    interrupted ||
    missing;
  const active =
    activeFlag ||
    (!terminal && (statusKind === 'active' || ACTIVE_STATUSES.has(status) || type === 'progress'));
  return {
    status,
    statusKind,
    terminal,
    active,
    successful,
    warning,
    failed,
    interrupted,
    missing,
    recoverable:
      truthyField(
        payload?.recoverable,
        payloadUserError.recoverable,
        explicitProgress.recoverable,
        explicitProgressUserError.recoverable,
        payloadProgress.recoverable,
        payloadProgressUserError.recoverable,
        payloadData.recoverable,
        payloadDataUserError.recoverable
      ) ||
      interrupted ||
      missing,
    retryable:
      truthyField(
        payload?.retryable,
        payloadUserError.retryable,
        explicitProgress.retryable,
        explicitProgressUserError.retryable,
        payloadProgress.retryable,
        payloadProgressUserError.retryable,
        payloadData.retryable,
        payloadDataUserError.retryable
      ) ||
      failed ||
      interrupted ||
      missing,
  };
}

export function classifyProgressState(
  state: ProgressLifecycle,
  progress?: UnifiedProgress | null
): JobStateClassification {
  const progressState = classifyJobState(null, progress);
  if (
    progressState.failed ||
    progressState.interrupted ||
    progressState.missing ||
    progressState.successful ||
    progressState.warning
  ) {
    return progressState;
  }
  const lifecyclePayload: JobStateInput = {};
  if (state === 'success') lifecyclePayload.status = 'completed';
  else if (state === 'error') {
    lifecyclePayload.type = 'error';
  } else if (state === 'loading' || state === 'progress') {
    lifecyclePayload.type = 'progress';
  } else if (state === 'idle') {
    lifecyclePayload.status = 'idle';
  }
  return classifyJobState(lifecyclePayload, progress);
}

export function jobStatusMessage(
  payload: JobStateInput | null | undefined,
  fallback: string
): string {
  const userFacing = apiErrorMessage(payload as ApiErrorExperiencePayload, '');
  if (userFacing) return userFacing;
  const progress = record(payload?.progress);
  const data = record(payload?.data);
  const nestedUserFacing = apiErrorMessage(progress, '') || apiErrorMessage(data, '');
  if (nestedUserFacing) return nestedUserFacing;
  const message = textField(
    payload?.status_message ||
      progress.status_message ||
      progress.message ||
      data.status_message ||
      data.message
  );
  return knownApiErrorMessage(message) || fallback;
}

export function resolveJobEventState(
  event: JobStateInput | null | undefined,
  progress?: JobStateProgressInput,
  messages: JobEventMessageOptions = {}
): JobEventResolution {
  const state = classifyJobState(event, progress);
  const eventType = normalizedJobStatus(event?.type);
  const terminal = state.terminal || eventType === 'complete' || eventType === 'error';
  const defaultSuccessMessage = messages.success || '流程已完成';
  if (!terminal) {
    return {
      state,
      kind: 'progress',
      terminal: false,
      message: '',
      notifyType: 'success',
      nextStatus: 'running',
    };
  }
  if (state.interrupted) {
    return {
      state,
      kind: 'interrupted',
      terminal: true,
      message: jobStatusMessage(event, messages.interrupted || '流程已停止，结果未确认完成。'),
      notifyType: 'warning',
      nextStatus: 'stopped',
    };
  }
  if (state.failed || state.missing || eventType === 'error') {
    return {
      state,
      kind: 'failed',
      terminal: true,
      message: jobStatusMessage(event, messages.failed || '流程失败。'),
      notifyType: 'error',
      nextStatus: 'failed',
    };
  }
  return {
    state,
    kind: 'success',
    terminal: true,
    message: jobStatusMessage(event, defaultSuccessMessage),
    notifyType: state.warning ? 'warning' : 'success',
    nextStatus: state.warning ? 'completed_with_warnings' : 'completed',
  };
}

function record(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function textField(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function truthyField(...values: unknown[]): boolean {
  return values.some((value) => value === true);
}

function normalizedKindValues(...values: unknown[]): string[] {
  return values.map(normalizedJobStatus).filter(Boolean);
}

function isInterruptedKind(value: string): boolean {
  return INTERRUPTED_STATUSES.has(value) || INTERRUPTED_ERROR_KINDS.has(value);
}

/** Build the request payload for /api/run */
export function buildRunPayload(
  resume: boolean,
  credentials?: BrainCredentials
): Record<string, string | boolean> {
  const payload: Record<string, string | boolean> = resume
    ? { resume: true, autoSubmit: false, auto_submit: false }
    : { autoSubmit: false, auto_submit: false };
  if (credentials?.username?.trim()) payload.username = credentials.username.trim();
  if (credentials?.password) payload.password = credentials.password;
  if (credentials?.token?.trim()) payload.token = credentials.token.trim();
  return payload;
}

/** Type guard: check if an unknown value is a valid JobStatus */
export function isJobStatus(value: unknown): value is JobStatus {
  if (!isRecord(value)) return false;
  return (
    typeof value.status === 'string' ||
    typeof value.job_id === 'string' ||
    typeof value.phase === 'string'
  );
}

/** Extract jobId from an API response with various possible shapes */
export function extractJobId(result: unknown): string {
  if (!isRecord(result)) return '';
  return String(result.job_id || result.task_id || '');
}

/** Format a validation ID for compact display */
export function shortValidationId(value: string): string {
  const text = String(value || '').trim();
  return text.length <= 12 ? text : `${text.slice(0, 6)}...${text.slice(-4)}`;
}
