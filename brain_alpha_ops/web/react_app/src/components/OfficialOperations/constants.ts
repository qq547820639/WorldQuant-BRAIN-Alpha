export const POLL_INTERVAL_MS = 2000;
export const SYNC_STATUS_FAILURE_LIMIT = 3;
export const SYNC_PROGRESS_STALL_WARNING_MS = 30_000;
export const SYNC_PROGRESS_STALL_STOP_MS = 90_000;
export const OPERATION_REQUEST_TIMEOUT_MS = 10000;
export const STOP_RETRY_AFTER_MS = 60_000;
export const MAX_LOG_ROWS = 80;
export const ACTIVE_SYNC_JOB_ID_KEY = 'brain_alpha_active_sync_job_id';

export interface OperationLogEntry {
  time: string;
  tone: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

export type OperationMode = 'idle' | 'context_refresh' | 'readiness' | 'checks';
export type OverviewTone = 'success' | 'warning' | 'neutral';
export type SyncStageKind = 'scan' | 'fields' | 'operators' | 'datasets' | 'other';
export type SyncRange = '3d' | '7d' | 'recent' | '6months' | 'all';

export interface SyncStageMetric {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  etaSeconds: number;
  ratePerSecond: number;
  pageNumber: number;
  expectedPages: number;
  pageSize: number;
  pageLimit: number;
  nextOffset: number;
  newUniqueItems: number;
  uniqueItems: number;
  confirmingTotalBoundary: boolean;
}

export interface SyncProgressMonitorState {
  jobId: string;
  signature: string;
  sinceMs: number;
  warned: boolean;
  interrupting: boolean;
}
