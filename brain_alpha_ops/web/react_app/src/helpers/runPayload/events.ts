/** Job event resolution and status messaging. */

import {
  apiErrorMessage,
  knownApiErrorMessage,
  type ApiErrorExperiencePayload,
} from '@/helpers/errorExperience';
import { classifyJobState, normalizedJobStatus } from './classify';
import { record, textField } from './internalHelpers';
import type {
  JobEventMessageOptions,
  JobEventResolution,
  JobStateInput,
  JobStateProgressInput,
} from './types';

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
