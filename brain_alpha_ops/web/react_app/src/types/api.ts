import type { OfficialContextCache } from './cloud';

// ── API Response Types ────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  ok: boolean;
  error_code?: string;
  error?: string;
  user_error?: ApiUserError;
  user_error_kind?: string;
  user_message?: string;
  next_action?: string;
  recoverable?: boolean;
  retryable?: boolean;
  data?: T;
}

export interface ApiUserError {
  kind?: string;
  title?: string;
  message?: string;
  impact?: string;
  suggested_action?: string;
  action_label?: string;
  next_action?: string;
  severity?: string;
  recoverable?: boolean;
  retryable?: boolean;
  detail?: string;
}

export interface JobStatus {
  job_id: string;
  task_id?: string;
  status:
    | 'idle'
    | 'queued'
    | 'running'
    | 'stopping'
    | 'stopped'
    | 'completed'
    | 'completed_with_warnings'
    | 'failed'
    | 'cancelled'
    | 'missing';
  ok?: boolean;
  phase?: string;
  cycle?: number;
  max_cycles?: number;
  started_at?: string;
  percent_complete?: number | null;
  eta_seconds?: number;
  status_message?: string;
  result?: unknown;
  error?: string;
  user_error?: ApiUserError;
  user_error_kind?: string;
  user_message?: string;
  status_kind?:
    | 'active'
    | 'success'
    | 'warning'
    | 'failed'
    | 'interrupted'
    | 'missing'
    | 'idle'
    | 'unknown';
  state_label?: string;
  terminal?: boolean;
  active?: boolean;
  interrupted?: boolean;
  recoverable?: boolean;
  retryable?: boolean;
  next_action?: string;
  progress?: JobProgress;
  official_context_cache?: OfficialContextCache;
  sync_history?: SyncHistoryItem[];
  sync_history_error?: string;
}

export interface SyncHistoryItem {
  job_id: string;
  task_id?: string;
  status: string;
  phase?: string;
  status_message?: string;
  updated_at?: number;
  updated_at_ms?: number;
  context_only?: boolean;
  scanned?: number;
  total?: number;
  api_reported_total?: number;
  filter_window_count?: number;
  added?: number;
  updated?: number;
  skipped?: number;
  failed?: number;
}

export interface JobProgress {
  task_id?: string;
  job_id?: string;
  phase?: string;
  phase_label?: string;
  status?: string;
  status_message?: string;
  message?: string;
  percent?: number;
  percent_complete?: number;
  eta_seconds?: number;
  eta_deadline_at_ms?: number;
  elapsed_seconds?: number;
  candidates_generated?: number;
  candidates_passed?: number;
  backtests_completed?: number;
  backtests_pending?: number;
  submissions?: number;
  done?: number;
  current?: number;
  total?: number;
  checked?: number;
  submitted?: number;
  failed?: number;
  scanned?: number;
  current_alpha_id?: string;
  [key: string]: unknown;
}

export type ProgressLifecycle = 'idle' | 'loading' | 'progress' | 'success' | 'error';

export interface UnifiedProgress {
  task_id?: string;
  job_id?: string;
  operation?: string;
  phase?: string;
  phase_label?: string;
  status_code?: string;
  status_kind?: string;
  status?: string;
  terminal?: boolean;
  active?: boolean;
  interrupted?: boolean;
  recoverable?: boolean;
  retryable?: boolean;
  status_message?: string;
  message?: string;
  error_code?: string;
  user_error?: ApiUserError;
  user_error_kind?: string;
  user_message?: string;
  next_action?: string;
  percent?: number | null;
  percent_complete?: number | null;
  eta_seconds?: number | null;
  eta_deadline_at_ms?: number | null;
  done?: number;
  checked?: number;
  submitted?: number;
  scanned?: number;
  total?: number;
  api_reported_total?: number;
  filter_window_count?: number;
  remaining_items?: number;
  has_more?: boolean;
  pagination_complete?: boolean;
  pagination_target?: string;
  stop_reason?: string;
  page_number?: number;
  pages_fetched?: number;
  expected_pages?: number;
  page_size?: number;
  page_limit?: number;
  offset?: number;
  next_offset?: number;
  new_unique_items?: number;
  unique_items?: number;
  confirming_total_boundary?: boolean;
  indeterminate?: boolean | null;
  open_ended?: boolean | null;
  error?: string;
}

// ── SSE Event Types ───────────────────────────────────────────────────────

export interface SSEEvent {
  type?:
    | 'progress'
    | 'candidate'
    | 'backtest'
    | 'submission'
    | 'error'
    | 'complete'
    | 'heartbeat'
    | 'stream_timeout';
  ok?: boolean;
  job_id?: string;
  task_id?: string;
  status?: string;
  status_kind?: JobStatus['status_kind'];
  state_label?: string;
  terminal?: boolean;
  active?: boolean;
  interrupted?: boolean;
  recoverable?: boolean;
  retryable?: boolean;
  user_error?: ApiUserError;
  user_error_kind?: string;
  user_message?: string;
  next_action?: string;
  phase?: string;
  percent_complete?: number | null;
  eta_seconds?: number;
  status_message?: string;
  progress?: JobProgress;
  result?: unknown;
  error?: string;
  data?: Record<string, unknown>;
}

/** SSE event data payload for candidate/submission events */
export interface SSECandidateEventData {
  alpha_id?: string | number;
  score?: number | string;
  [key: string]: unknown;
}

/** Production result summary embedded in JobStatus.result */
export interface ProductionResultSummary {
  official_validation_attempted?: number;
  official_validation_passed?: number;
  officially_simulated?: number;
  backtests_submitted?: number;
  submitted_this_run?: number;
  auto_submitted?: number;
  [key: string]: unknown;
}

/** Trend API response from /api/trends */
export interface TrendApiResponse {
  ok: boolean;
  data?: Array<{
    date?: string;
    candidates?: number;
    submissions?: number;
    [key: string]: unknown;
  }>;
}
