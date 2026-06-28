/** Job status classification functions. */

import type { ProgressLifecycle, UnifiedProgress } from '@/types';
import {
  ACTIVE_STATUSES,
  FAILED_STATUSES,
  INTERRUPTED_ERROR_KINDS,
  INTERRUPTED_STATUSES,
  MISSING_STATUSES,
  SUCCESS_STATUSES,
  TERMINAL_STATUSES,
  TERMINAL_STATUS_KINDS,
  WARNING_STATUSES,
} from './constants';
import { record, truthyField } from './internalHelpers';
import type { JobStateClassification, JobStateInput, JobStateProgressInput } from './types';

export function normalizedJobStatus(value: unknown): string {
  return String((value as string | number | boolean | null | undefined) || '')
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

function normalizedKindValues(...values: unknown[]): string[] {
  return values.map(normalizedJobStatus).filter(Boolean);
}

function isInterruptedKind(value: string): boolean {
  return INTERRUPTED_STATUSES.has(value) || INTERRUPTED_ERROR_KINDS.has(value);
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

export function isTerminalStatus(status: string | undefined): boolean {
  return classifyJobState({ status }).terminal;
}

export function isSuccessfulStatus(status: string | undefined): boolean {
  return classifyJobState({ status }).successful;
}

export function isInterruptedStatus(status: string | undefined): boolean {
  return classifyJobState({ status }).interrupted;
}
