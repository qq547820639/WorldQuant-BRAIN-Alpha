import type { OfficialMetrics, QualityGate } from './candidate';

// ── Cloud / Snapshot Types ────────────────────────────────────────────────

export interface OfficialContextCache {
  ok?: boolean;
  fields_count?: number;
  operators_count?: number;
  datasets_count?: number;
  error?: string;
  manifest?: {
    complete?: boolean;
    is_stale?: boolean;
    missing_files?: string[];
    stale_files?: string[];
    invalid_files?: string[];
    record_counts?: Record<string, number>;
  };
  [key: string]: unknown;
}

export interface CloudAlphaCache {
  ok?: boolean;
  count?: number;
  total?: number;
  source?: string;
  is_stale?: boolean;
  loaded_at?: string;
  age_seconds?: number;
}

/** Phase state response from /api/phase_state */
export interface PhaseData {
  current_phase?: string;
  operation_mode?: 'cache_only' | 'connected' | 'needs_setup';
  connected: boolean;
  context_fresh: boolean;
  candidates_count: number;
  scored_count: number;
  readiness_passed: boolean;
  sync?: {
    in_progress?: boolean;
    scanned?: number;
    total?: number;
    elapsed_seconds?: number;
    stalled?: boolean;
  };
  official_context_cache?: OfficialContextCache;
  cloud_alpha_cache?: CloudAlphaCache;
  readiness?: {
    eligible_count?: number;
    ready?: boolean;
  };
  [key: string]: unknown;
}

export interface CloudAlphaSummary {
  source: string;
  count: number;
  submitted_count: number;
  passed_unsubmitted_count: number;
  failed_unsubmitted_count: number;
  is_stale: boolean;
  sample_alphas: CloudAlpha[];
}

/** Cloud alpha row that may come as a flat CloudAlpha or with a nested metrics object */
export type CloudAlphaWithMetrics = CloudAlpha & {
  id?: string;
  metrics?: {
    pass_fail?: string;
    sharpe?: number;
    fitness?: number;
    turnover?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
};

// ── Backtest Slot Types ──────────────────────────────────────────────────

export interface BacktestSlot {
  slot: number;
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  status?: string;
  lifecycle_status?: string;
  score?: number | null;
  poll_count?: number;
  progress_percent?: number;
  next_poll_seconds?: number;
  message?: string;
  expression?: string;
  family?: string;
  hypothesis?: string;
  official_metrics?: OfficialMetrics;
  gate?: QualityGate;
  status_board?: BacktestStatusBoard;
}

export interface BacktestSlotsResponse {
  ok: boolean;
  source?: string;
  slot_limit: number;
  active_count: number;
  slots: BacktestSlot[];
  updated_at?: string;
  queue_summary?: BacktestQueueSummary;
}

export interface BacktestStatusBoard {
  task_index?: number;
  alpha_id?: string;
  submitted_count?: number;
  completed_count?: number;
  failed_count?: number;
  passed_count?: number;
  not_passed_count?: number;
  pass_rate?: number;
}

export interface BacktestQueueSummary {
  schema_version?: string;
  source?: string;
  official_api_called?: boolean;
  official_slot_record_count?: number;
  candidate_path?: string;
  candidate_count?: number;
  returned_candidate_count?: number;
  slot_limit?: number;
  active_slot_count?: number;
  open_slot_count?: number;
  empty_slot_count?: number;
  local_valid_count?: number;
  above_simulation_score_count?: number;
  review_candidate_count?: number;
  blocked_candidate_count?: number;
  submit_evidence_blocking_count?: number;
  min_prior_score_for_official_simulation?: number;
  top_blocking_reasons?: { reason: string; count: number }[];
  top_submit_blocking_reasons?: { reason: string; count: number }[];
  next_action?: string;
}

// ── Submit Readiness Types ───────────────────────────────────────────────

export interface ReadinessReasonCount {
  reason: string;
  count: number;
}

export interface SubmitReadinessFinding {
  code?: string;
  message?: string;
}

export interface SubmitReadinessCandidate {
  alpha_id?: string;
  official_alpha_id?: string;
  lifecycle_status?: string;
  pass_fail?: string;
  score?: number | null;
  decision_band?: string;
  local_backtest_passed?: boolean | null;
  max_similarity?: number | null;
  risk_level?: string;
  blocking_reasons?: string[];
}

export interface SubmitReadinessResponse {
  ok: boolean;
  schema_version?: string;
  source?: string;
  authoritative_stop_rule?: string;
  validation_command?: string;
  official_api_called?: boolean;
  non_submit_flow?: boolean;
  real_submit_performed?: boolean;
  ready_to_submit?: boolean;
  submit_ready_claim_allowed?: boolean;
  ledger_ready_to_submit?: boolean;
  job_family_ready_to_submit?: boolean;
  candidate_count?: number;
  ledger_candidate_count?: number;
  job_family_candidate_count?: number;
  eligible_count?: number;
  ledger_eligible_count?: number;
  job_family_eligible_count?: number;
  latest_job_id?: string;
  latest_job_status?: string;
  threshold_summary?: Record<string, unknown>;
  summary_counts?: {
    official_validation_passed?: number;
    officially_simulated?: number;
    submission_ready?: number;
    submitted_this_run?: number;
  };
  max_similarity?: number | null;
  job_family_max_similarity?: number | null;
  top_blocking_reasons?: ReadinessReasonCount[];
  top_family_blocking_reasons?: ReadinessReasonCount[];
  findings?: SubmitReadinessFinding[];
  production_gaps?: SubmitReadinessFinding[];
  best_candidate?: SubmitReadinessCandidate;
  required_next_steps?: string[];
  error?: string;
}

export interface CloudAlpha {
  alpha_id: string;
  status: string;
  expression: string;
  pass_fail: string;
  sharpe: number;
  fitness: number;
  turnover: number;
  [key: string]: unknown;
}

export interface ResearchMemorySummary {
  total_candidates: number;
  families: FamilyStat[];
  fields: FieldStat[];
  operators: OperatorStat[];
  failure_patterns: FailurePattern[];
}

export interface FamilyStat {
  name: string;
  count: number;
  success_rate: number;
  avg_score: number;
  avg_sharpe: number;
}

export interface FieldStat {
  name: string;
  count: number;
  success_rate: number;
  avg_sharpe: number;
}

export interface OperatorStat {
  name: string;
  count: number;
  success_rate: number;
}

export interface FailurePattern {
  reason: string;
  count: number;
}
