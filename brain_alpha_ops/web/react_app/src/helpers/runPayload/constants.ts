/** Status classification constants for job monitoring. */

export const TERMINAL_STATUSES = new Set([
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
export const SUCCESS_STATUSES = new Set([
  'completed',
  'completed_with_warnings',
  'success',
  'done',
]);
export const WARNING_STATUSES = new Set(['completed_with_warnings', 'warning']);
export const FAILED_STATUSES = new Set(['failed', 'error', 'watchdog_failed']);
export const INTERRUPTED_STATUSES = new Set(['stopped', 'cancelled', 'canceled', 'interrupted']);
export const INTERRUPTED_ERROR_KINDS = new Set([
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
export const MISSING_STATUSES = new Set([
  'missing',
  'job_not_found',
  'unknown_job',
  'unknown job',
  'unknown sync job',
  'session_invalid',
  'invalid local session',
  'session_expired',
]);
export const ACTIVE_STATUSES = new Set(['queued', 'running', 'progress', 'loading', 'stopping']);
export const TERMINAL_STATUS_KINDS = new Set([
  'success',
  'warning',
  'failed',
  'interrupted',
  'missing',
]);
