/** Shared type definitions for job monitoring helpers. */

export type JobStateInput = {
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

export type JobStateProgressInput = Record<string, unknown> | object | null | undefined;

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
