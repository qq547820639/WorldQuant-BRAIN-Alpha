/**
 * Core TypeScript type definitions for the BRAIN Alpha Ops web console.
 *
 * Merged from former per-domain modules (api / scoring / candidate / config /
 * cloud / ui / errors) plus the barrel type guards.  Kept as a single module
 * so consumers can import everything from '@/types' via the re-export in
 * index.ts.  Cross-module type references are resolved within this file.
 */

// ──────────────────────────────────────────────────────────────────────────
// API Response Types (former api.ts)
// ──────────────────────────────────────────────────────────────────────────

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

// ──────────────────────────────────────────────────────────────────────────
// Official Scoring Types (former scoring.ts)
// ──────────────────────────────────────────────────────────────────────────

export interface Scorecard {
  total_score: number;
  prior_score: number;
  empirical_score: number;
  checklist_score: number;
  decision_band: string;
  sharpe?: number;
  fitness?: number;
  turnover?: number;
  attribution?: ScoreAttribution[];
  /** Full attribution tree from backend build_attribution_tree() */
  attribution_tree?: AttributionNode | null;
  /** Three-layer weights: {"prior": 0.30, "empirical": 0.45, "checklist": 0.25} */
  layer_weights?: Record<string, number>;
  /** Prior layer detail: {score, dimensions, weights, source} */
  prior?: ScoreLayerDetail;
  /** Empirical layer detail: {score, items, hard_gate_failed, hard_gate_failures, status} */
  empirical?: ScoreLayerDetail;
  /** Submission checklist detail: {score, items} */
  submission_checklist?: ScoreLayerDetail;
  /** Score basis: "official_verified" or "local_prior" */
  score_basis?: string;
  /** Hard gate results for gate pass/fail display */
  hard_gates?: HardGateResult[];
  /** Top failures list for improvement hints */
  top_failures?: FailureItem[];
  /** Improvement hints for the candidate */
  improvement_hints?: string[];
  /** Local rank score (used when no official metrics) */
  local_rank_score?: number;
  /** Decision band override for thresholds */
  confidence?: ScoreConfidence;
  calibration?: Record<string, unknown>;
  settings_trace?: Record<string, unknown>;
  assistant_guidance_adjustment?: Record<string, unknown>;
}

/** Backend score layer detail — matches Python build_scorecard() output */
export interface ScoreLayerDetail {
  score: number;
  items?: ScoreLayerItem[];
  dimensions?: Record<string, number>;
  weights?: Record<string, number>;
  source?: string;
  status?: string;
  hard_gate_failed?: boolean;
  hard_gate_failures?: string[];
  delay?: number;
  threshold_source?: string;
  market_regime?: string;
  regime_adjustments?: Record<string, unknown>;
  margin_source?: string;
}

/** Score confidence estimate */
export interface ScoreConfidence {
  confidence_level: 'high' | 'medium' | 'low';
  item_count: number;
  passed_count: number;
  score_variance: number;
  score_dispersion: number;
  data_completeness: number;
  interpretation: string;
}

/** Hard gate result from empirical items with is_hard_gate=true */
export interface HardGateResult {
  name: string;
  passed: boolean;
  actual?: number | string | null;
  target?: number | string | null;
  direction?: string;
  explanation?: string;
}

export interface ScoreAttribution {
  dimension: string;
  score: number;
  weight: number;
  sub_items?: ScoreAttribution[];
}

export interface ScoringResult {
  alpha_id: string;
  expression: string;
  total_score: number;
  decision_band: string;
  passed_gate: boolean;
  evaluated_at?: string;
  prior?: ScoreLayer;
  empirical?: ScoreLayer;
  checklist?: ScoreLayer;
  layer_weights?: Record<string, number>;
  hard_gates?: OfficialGateResult[];
  soft_gates?: OfficialGateResult[];
  release_gate?: Record<string, unknown>;
  attribution_tree?: AttributionNode | null;
  top_failures?: FailureItem[];
  improvement_hints?: string[];
  api_output_deviation?: number;
  deviation_details?: string[];
  scoring_schema?: string;
  score_basis?: string;
  attribution_summary?: Record<string, unknown>;
}

export interface ScoreLayer {
  score?: number;
  raw_score?: number;
  weight?: number;
  max_points?: number;
  items?: ScoreLayerItem[];
  [key: string]: unknown;
}

export interface ScoreLayerItem {
  name?: string;
  passed?: boolean;
  points?: number;
  actual?: number | string | null;
  target?: number | string | null;
  direction?: string;
  meaning?: string;
  source?: string;
  is_hard_gate?: boolean;
}

export interface OfficialGateResult {
  gate_name: string;
  passed: boolean;
  check_items?: OfficialGateCheckItem[];
  failed_items?: string[];
  threshold_source?: string;
  notes?: string[];
}

export interface OfficialGateCheckItem {
  name: string;
  passed: boolean;
  actual?: number | string | null;
  target?: number | string | null;
  direction?: string;
  meaning?: string;
  source?: string;
}

export interface AttributionNode {
  name: string;
  score: number;
  weight: number;
  contribution?: number;
  explanation?: string;
  historical_trend?: string;
  children?: AttributionNode[];
}

export interface ScoringAttributionResponse {
  ok: boolean;
  attribution?: AttributionNode | null;
  attribution_summary?: Record<string, unknown>;
  hard_gates?: OfficialGateResult[];
  soft_gates?: OfficialGateResult[];
  top_failures?: FailureItem[];
  improvement_hints?: string[];
}

export interface FailureItem {
  item?: string;
  reason?: string;
  severity?: string;
}

// ── Workstream D4.1: Structured GateDecision / Attribution / Audit export ──

/** Mirrors backend GateDecisionService action constants. */
export type GateDecisionActionLiteral =
  | 'enter_official_simulation_queue'
  | 'continue_optimization'
  | 'discard_archive'
  | 'enter_human_confirmation';

/** Evidence snapshot from gate sources used to derive the decision. */
export interface GateEvidence {
  hard_gate_failed?: string[];
  anti_overfit_recommendation?: string;
  anti_overfit_passed?: boolean;
  has_official_metrics?: boolean;
  release_status?: string;
  gate_submission_ready?: boolean;
}

/** A single triggered rule contributing to the decision (audit-trail entry). */
export interface TriggeredRule {
  source?: string;
  rule?: string;
  severity?: string;
  reason?: string;
  actual?: number | string | null;
  expected?: number | string | null;
  score?: number | null;
}

/** Candidate snapshot included in the gate-decision payload. */
export interface GateDecisionCandidateSnapshot {
  alpha_id?: string;
  lifecycle_status?: string;
  total_score?: number;
  decision_band?: string;
  has_official_metrics?: boolean;
  gate_submission_ready?: boolean;
  gate_hard_blocked?: boolean;
}

/** POST /api/scoring/gate_decision response payload. */
export interface GateDecisionPayload {
  ok: boolean;
  action: GateDecisionActionLiteral;
  reason: string;
  target_state: string;
  alpha_id?: string;
  schema_version?: string;
  gate_evidence?: GateEvidence;
  triggered_rules?: TriggeredRule[];
  next_action_hint?: string;
  release_gate?: Record<string, unknown>;
  candidate_snapshot?: GateDecisionCandidateSnapshot;
  error?: string;
  error_code?: string;
}

/** One dimension aggregate (mirrors backend DimensionSummary.to_dict). */
export interface MultiAttributionDimension {
  dimension: string;
  value: string;
  count: number;
  avg_score: number;
  pass_count: number;
  fail_count: number;
  top_failures: string[];
}

/** POST /api/scoring/multi_attribution response payload. */
export interface MultiAttributionPayload {
  ok: boolean;
  schema_version?: string;
  multi_attribution?: {
    schema_version: string;
    dimensions: {
      by_gate: MultiAttributionDimension[];
      by_metric: MultiAttributionDimension[];
      by_dataset: MultiAttributionDimension[];
      by_region: MultiAttributionDimension[];
      by_time: MultiAttributionDimension[];
    };
    total_scorecards: number;
  };
  error?: string;
  error_code?: string;
}

/** A single replayable audit-trail entry (mirrors audit_trail/export.py). */
export interface AuditExportEntry {
  export_schema?: string;
  entry_id?: string;
  alpha_id?: string;
  event_type?: string;
  written_at?: string;
  source_file?: string;
  scoring_version?: string;
  gate_version?: string;
  capability_version?: string;
  sim_config?: Record<string, unknown>;
  result_summary?: Record<string, unknown>;
  change_record?: Record<string, unknown>;
  details?: Record<string, unknown>;
}

/** GET /api/audit/export response payload. */
export interface AuditExportResponse {
  ok: boolean;
  schema_version?: string;
  alpha_id?: string;
  entry_count: number;
  entries: AuditExportEntry[];
  error?: string;
  error_code?: string;
}

// ──────────────────────────────────────────────────────────────────────────
// Candidate Types (former candidate.ts)
// ──────────────────────────────────────────────────────────────────────────

export interface Candidate {
  alpha_id: string;
  official_alpha_id?: string;
  simulation_id?: string;
  expression: string;
  family: string;
  hypothesis: string;
  lifecycle_status: string;
  status?: string;
  blocking_reasons?: string[];
  scorecard?: Scorecard;
  official_metrics?: OfficialMetrics;
  gate?: QualityGate;
  decision_band?: string;
  data_fields?: string[];
  operators?: string[];
  source_tags?: string[];
  parent_id?: string;
  mutation_type?: string;
  dataset_id?: string;
  local_quality?: LocalQuality;
  alpha_output_config?: AlphaOutputConfig;
  quality_diagnosis?: QualityDiagnosis;
  production_decision?: CandidateProductionDecision;
  decision_action?: string;
  decision_reason?: string;
  extra_fields?: CandidateExtraFields;
  scientific_audit?: CandidateScientificAudit;
  official_context_proof?: Record<string, unknown>;
  expression_delta?: Record<string, unknown>;
  optimization_explanation?: CandidateOptimizationExplanation;
  submission?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface AlphaLifecycleRecord {
  schema_version?: string;
  timestamp?: string;
  run_id?: string;
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  stage?: string;
  status?: string;
  status_category?: string;
  expression?: string;
  expression_digest?: string;
  note?: string;
  correlation_id?: string;
  source?: string;
  decision_action?: string;
  decision_band?: string;
  lifecycle_status?: string;
  family?: string;
  dataset_id?: string;
  score?: number;
}

export interface AlphaLifecycleTrace {
  trace_key?: string;
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  expression_digest?: string;
  latest_stage?: string;
  latest_status?: string;
  status_category?: string;
  event_count?: number;
  first_event_at?: string;
  latest_event_at?: string;
  stages?: string[];
  blocked?: boolean;
  failed?: boolean;
  passed?: boolean;
  submitted?: boolean;
  last_note?: string;
  next_action?: string;
}

export interface AlphaLifecycleHistoryResponse {
  ok: boolean;
  schema_version?: string;
  source?: string;
  official_api_called?: boolean;
  submit_allowed?: boolean;
  filters?: Record<string, unknown>;
  records?: AlphaLifecycleRecord[];
  items?: AlphaLifecycleRecord[];
  count?: number;
  returned_count?: number;
  total_count?: number;
  total?: number;
  complete?: boolean;
  display_limit?: number;
  summary?: {
    record_count?: number;
    alpha_count?: number;
    latest_event_at?: string;
    by_stage?: Record<string, number>;
    by_status_category?: Record<string, number>;
    blocked_count?: number;
    failed_count?: number;
    passed_count?: number;
    submitted_count?: number;
    replay_ready?: boolean;
  };
  alpha_traces?: AlphaLifecycleTrace[];
}

export interface CandidateExtraFields {
  production_decision?: CandidateProductionDecision;
  scientific_audit?: CandidateScientificAudit;
  official_context_proof?: Record<string, unknown>;
  expression_delta?: Record<string, unknown>;
  optimization_explanation?: CandidateOptimizationExplanation;
  [key: string]: unknown;
}

export interface CandidateOptimizationExplanation {
  schema_version?: string;
  source?: string;
  local_only?: boolean;
  official_api_called?: boolean;
  submit_allowed?: boolean;
  parent?: {
    alpha_id?: string;
    decision_action?: string;
    failed_dimensions?: string[];
    blocking_reasons?: string[];
    score?: number | null;
  };
  mutation?: {
    mode?: string;
    reason?: string;
    parent_failure?: string;
    rank_input_index?: number | null;
    search_score?: number | null;
    optimizer_trace?: {
      schema_version?: string;
      failed_dimension?: string;
      selected_strategy?: string;
      strategy_order?: string[];
      strategy_index?: number | null;
      suggested_modes?: string[];
      official_api_called?: boolean;
      submit_allowed?: boolean;
    };
  };
  expression_change?: {
    schema_version?: string;
    changed?: boolean;
    fields_added?: string[];
    fields_removed?: string[];
    operators_added?: string[];
    operators_removed?: string[];
    windows_added?: number[];
    windows_removed?: number[];
  };
  official_context?: {
    schema_version?: string;
    source?: string;
    passed?: boolean;
    official_api_called?: boolean;
    reasons?: string[];
    missing_fields?: string[];
    missing_operators?: string[];
    dataset_mismatches?: string[];
    dataset_id?: string;
    checked_fields?: string[];
  };
  decision?: {
    action?: string;
    next_state?: string;
    blocking?: boolean;
    decision_band?: string;
    score?: number | null;
  };
  next_action?: string;
}

export interface CandidateScientificAudit {
  schema_version?: string;
  operation?: string;
  source?: string;
  explainability?: {
    official_context_proof?: Record<string, unknown>;
    expression_delta?: Record<string, unknown>;
    optimization_explanation?: CandidateOptimizationExplanation;
  };
  evidence?: Record<string, unknown>;
  anti_overfit?: Record<string, unknown>;
  safety_boundary?: Record<string, unknown>;
  events?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface CandidateProductionDecision {
  schema_version?: string;
  action?: string;
  next_state?: string;
  reason?: string;
  blocking?: boolean;
  score?: number;
  decision_band?: string;
  reason_codes?: string[];
  source?: string;
  official_api_called?: boolean;
  submit_allowed?: boolean;
  decision_evidence?: CandidateDecisionEvidence;
}

export interface CandidateDecisionEvidence {
  schema_version?: string;
  source?: string;
  local_only?: boolean;
  official_api_called?: boolean;
  submit_allowed?: boolean;
  hard_blocking_reasons?: string[];
  scientific_audit_policy_reasons?: string[];
  lifecycle_risk?: {
    schema_version?: string;
    source?: string;
    local_only?: boolean;
    official_api_called?: boolean;
    submit_allowed?: boolean;
    matched_event_count?: number;
    matched_by?: string;
    latest_stage?: string;
    latest_status?: string;
    latest_status_category?: string;
    latest_event_at?: string;
    action_hint?: string;
    blocking?: boolean;
    reason_code?: string;
  };
}

export interface LocalQuality {
  score?: number;
  threshold?: number;
  passed?: boolean;
  reasons?: string[];
  warnings?: string[];
  local_backtest?: Record<string, unknown>;
  local_backtest_support?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface AlphaOutputConfig {
  schema_version?: string;
  local_only?: boolean;
  official_api_called?: boolean;
  allow_submit?: boolean;
  alpha_type?: string;
  dataset_id?: string;
  settings?: Record<string, unknown>;
  platform_payload?: Record<string, unknown>;
  generation?: Record<string, unknown>;
  local_gate?: Record<string, unknown>;
  official_thresholds?: Record<string, unknown>;
  submission_policy?: Record<string, unknown>;
  qualified_alpha_definition?: Record<string, string[]>;
  [key: string]: unknown;
}

export interface AlphaQualityReason {
  code?: string;
  category?: string;
  severity?: string;
  message?: string;
  field?: string;
  expected?: unknown;
  value?: unknown;
  [key: string]: unknown;
}

export interface QualityDiagnosis {
  schema_version?: string;
  qualified?: boolean;
  submission_ready?: boolean;
  local_candidate_valid?: boolean;
  status?: string;
  status_label?: string;
  primary_reason?: AlphaQualityReason | null;
  blocking_reasons?: string[];
  warning_reasons?: string[];
  reason_counts?: Record<string, number>;
  category_counts?: Record<string, number>;
  reasons?: AlphaQualityReason[];
  missing_fields?: string[];
  format_checks?: Record<string, unknown>;
  numeric_bounds?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface OfficialMetrics {
  sharpe: number;
  fitness: number;
  turnover: number;
  returns: number;
  drawdown: number;
  correlation: number;
  self_correlation?: number;
  self_correlation_status?: string;
  weight_concentration: number;
  sub_universe_sharpe?: number;
  margin?: number;
  pass_fail?: string;
}

export interface QualityGate {
  passed: boolean;
  status: string;
  submission_ready?: boolean;
  failed_reasons?: string[];
  failed_checks?: GateCheck[];
}

export interface GateCheck {
  name: string;
  passed: boolean;
  detail: string;
  severity: 'ERROR' | 'WARNING';
}

export interface CandidateCheckResult {
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  status?: string;
  passed?: boolean;
  submittable?: boolean;
  is_stale?: boolean;
  score?: number;
  failed_reasons?: string[];
  checked_at?: string;
  [key: string]: unknown;
}

export interface CandidateWorkflowPlan {
  producer?: { deficit?: number };
  validator?: Record<string, unknown>;
  rework?: Record<string, unknown>;
  review?: Record<string, unknown>;
  [key: string]: unknown;
}

export type CandidateListMeta = {
  returned: number;
  total: number;
  [key: string]: unknown;
};

export type CandidateQueueView =
  | 'candidates'
  | 'pending_backtest'
  | 'running_backtest'
  | 'backtest_rework'
  | 'passed'
  | 'submittable'
  | 'submitted'
  | 'failed';

// ──────────────────────────────────────────────────────────────────────────
// Pipeline / Run Types (former config.ts)
// ──────────────────────────────────────────────────────────────────────────

export interface RunConfig {
  environment: string;
  auto_submit?: boolean;
  autoSubmit?: boolean;
  credentials?: {
    username?: string;
    password?: string;
    token?: string;
    username_env?: string;
    password_env?: string;
    token_env?: string;
    managed_credentials_available?: boolean;
  };
  settings?: BrainSettings;
  budget?: BudgetConfig;
  thresholds?: ThresholdConfig;
  scoring?: ScoringConfig;
  ops?: {
    settings?: BrainSettings;
    budget?: BudgetConfig;
    thresholds?: ThresholdConfig;
    scoring?: ScoringConfig;
  };
}

export interface BrainSettings {
  instrumentType?: string;
  region: string;
  universe: string;
  delay: number;
  decay: number;
  neutralization: string;
  dataset?: string;
  truncation?: number;
  pasteurization?: string;
  unitHandling?: string;
  nanHandling?: string;
  language?: string;
  type?: string;
}

export interface BudgetConfig {
  max_candidates_per_cycle: number;
  max_cycles: number;
  retained_alpha_pool_size: number;
  official_backtest_batch_size: number;
  require_cloud_sync: boolean;
}

export interface ThresholdConfig {
  min_sharpe: number;
  min_fitness: number;
  min_turnover: number;
  platform_max_turnover: number;
  max_self_correlation: number;
  max_weight_concentration: number;
}

export interface ScoringConfig {
  prior_layer_weight: number;
  empirical_layer_weight: number;
  checklist_layer_weight: number;
  market_regime: string;
}

export interface BrainCredentials {
  username: string;
  password: string;
  token: string;
}

// ──────────────────────────────────────────────────────────────────────────
// Cloud / Snapshot Types (former cloud.ts)
// ──────────────────────────────────────────────────────────────────────────

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

// ──────────────────────────────────────────────────────────────────────────
// UI State Types (former ui.ts)
// ──────────────────────────────────────────────────────────────────────────

export type TabId =
  | 'candidates'
  | 'official_backtests'
  | 'quality_check'
  | 'submission_confirm'
  | 'checkpoint_status'
  | 'cloud'
  | 'dashboard'
  | 'pending_backtest'
  | 'running_backtest'
  | 'backtest_rework'
  | 'passed'
  | 'submittable'
  | 'submitted'
  | 'failed'
  | 'lifecycle'
  | 'research_memory'
  | 'research_knowledge'
  | 'research_observability'
  | 'prompt_runs'
  | 'sqlite_indexes'
  | 'robustness'
  | 'scoring'
  | 'submission'
  | 'config'
  | 'knowledge';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration_ms?: number;
  action_label?: string;
  on_action?: () => void;
  secondary_action_label?: string;
  on_secondary_action?: () => void;
}

// ── Phase Navigation Types (UI Design System v3.0) ─────────────────────

export type PhaseId = 'connect' | 'discover' | 'evaluate' | 'ready';
export type PhaseStatus =
  | 'locked'
  | 'pending'
  | 'active'
  | 'complete'
  | 'blocked'
  | 'loading'
  | 'error'
  | 'ready';

export interface PhaseGroup {
  id: PhaseId;
  label: string;
  status: PhaseStatus;
  items: PhaseNavItem[];
  expanded: boolean;
  unlockCondition: string;
}

export interface PhaseNavItem {
  id: CardViewId;
  label: string;
  icon: string;
  badge?: string | number;
  badgeTone?: 'neutral' | 'positive' | 'warning' | 'info';
}

export interface PhaseState {
  currentPhase: PhaseId;
  phases: Record<PhaseId, PhaseGroup>;
  overallProgress: number; // 0-4 steps completed
}

export interface StepGuideItem {
  id: string;
  label: string;
  status: 'complete' | 'active' | 'pending';
  phase: PhaseId;
}

/**
 * Card-based navigation view identifier.
 * A subset of TabId used by the StateCards detail view routing.
 */
export type CardViewId =
  | 'official_operations'
  | 'dashboard'
  | 'candidates'
  | 'official_backtests'
  | 'scoring'
  | 'quality_check'
  | 'submission_confirm'
  | 'config'
  | 'checkpoint_status'
  | 'cloud'
  | 'robustness';

// ── Aliases & additional shared types ────────────────────────────────────

export type PhaseApiStatus = PhaseStatus;

export interface LifecycleMetric {
  label: string;
  value: string | number;
  tone?: 'positive' | 'negative' | 'warning' | 'info' | 'neutral';
  [key: string]: unknown;
}

export interface LifecycleMetricProps {
  metric: LifecycleMetric;
  [key: string]: unknown;
}

export interface LifecycleReplayPanelProps {
  alphaId?: string;
  [key: string]: unknown;
}

export interface QualitySummaryData {
  ready?: number;
  retained?: string;
  promotable?: number;
  rework?: number;
  blocked?: number;
  outputMode?: string;
  [key: string]: unknown;
}

// ──────────────────────────────────────────────────────────────────────────
// Actionable error types & frontend classification (former errors.ts)
// (Workstream E3)
//
// Mirrors the backend ``brain_alpha_ops.error_catalog`` module so that
// API error payloads carrying an ``actionable`` field can be rendered
// uniformly by ``<ActionableError>``.  ``classifyError`` provides a
// frontend-side fallback when an error has no actionable payload
// attached (e.g. thrown by client code, network layer, or a backend
// route that has not yet been migrated).
//
// Keep this section stdlib-only relative to the rest of the codebase: it
// is imported from many places and should not pull heavy dependencies.
// ──────────────────────────────────────────────────────────────────────────

// ── Backend payload shapes ────────────────────────────────────────────────

/** The 11 error kinds defined in the spec. */
export type ErrorKind =
  | 'login_expired'
  | 'cache_unavailable'
  | 'official_rate_limited'
  | 'simulation_concurrency_exceeded'
  | 'dataset_missing'
  | 'field_non_compliant'
  | 'expression_invalid'
  | 'network_timeout'
  | 'task_cancelled'
  | 'queue_blocked'
  | 'local_service_unavailable';

/** Severity colors map to ErrorCard's existing severity config. */
export type ErrorSeverity = 'error' | 'warning' | 'info';

/**
 * Structured actionable error payload (matches the dict returned by
 * ``brain_alpha_ops.error_catalog.build_actionable_error``).
 */
export interface ActionableErrorPayload {
  kind: ErrorKind;
  cause: string;
  impact_scope: string;
  suggested_action: string;
  /** Handler id the frontend dispatches on click (see RECOVERY_ACTION_LABELS). */
  recovery_action_id: string;
  /** Frontend route/handler id the user can click (e.g. "/config"). */
  recovery_url: string;
  /** i18n catalog key (e.g. "error.login_expired"). */
  i18n_key: string;
  severity: ErrorSeverity;
  context?: Record<string, unknown>;
}

/** A backend error response that carries an actionable payload. */
export interface ActionableErrorResponse {
  ok?: boolean;
  error?: string;
  error_code?: string;
  actionable?: ActionableErrorPayload;
  [key: string]: unknown;
}

// ── Type guards ───────────────────────────────────────────────────────────

export function isActionableErrorPayload(value: unknown): value is ActionableErrorPayload {
  if (typeof value !== 'object' || value === null) return false;
  const rec = value as Record<string, unknown>;
  return (
    typeof rec.kind === 'string' &&
    typeof rec.cause === 'string' &&
    typeof rec.impact_scope === 'string' &&
    typeof rec.suggested_action === 'string' &&
    typeof rec.recovery_action_id === 'string' &&
    typeof rec.recovery_url === 'string' &&
    typeof rec.i18n_key === 'string' &&
    typeof rec.severity === 'string'
  );
}

export function isActionableErrorResponse(value: unknown): value is ActionableErrorResponse {
  if (typeof value !== 'object' || value === null) return false;
  const rec = value as Record<string, unknown>;
  return isActionableErrorPayload(rec.actionable);
}

// ── Recovery action labels (mirrors backend recovery_action_id values) ────

export const RECOVERY_ACTION_LABELS: Record<string, string> = {
  reconnect_session: '重新连接',
  refresh_cache: '刷新缓存',
  review_official_slots: '查看回测队列',
  check_config: '检查配置',
  fix_expression: '前往候选管理',
  wait_and_retry: '稍后重试',
  resume_or_restart: '恢复或重启',
  restart_flow: '重启服务',
};

/** Human-readable Chinese label for a recovery_action_id. */
export function recoveryActionLabel(actionId: string | undefined): string | null {
  if (!actionId) return null;
  return RECOVERY_ACTION_LABELS[actionId] ?? null;
}

// ── Frontend classification (fallback when no actionable payload) ────────

const ERROR_KIND_KEYWORDS: Array<{ kind: ErrorKind; needles: string[] }> = [
  {
    kind: 'simulation_concurrency_exceeded',
    needles: ['concurrent_simulation_limit_exceeded', 'concurrent simulation limit'],
  },
  {
    kind: 'official_rate_limited',
    needles: ['rate_limited', 'rate limit', 'too many requests', '429'],
  },
  {
    kind: 'login_expired',
    needles: [
      'auth_token_expired',
      'session_expired',
      'session_invalid',
      'unauthorized',
      'forbidden',
      'invalid_credentials',
      'auth_invalid',
      '401',
      '403',
    ],
  },
  {
    kind: 'cache_unavailable',
    needles: [
      'cache_unavailable',
      'official_fields_empty',
      'official_operators_empty',
      'context_refresh_failed',
      'jsondecodeerror',
      'json decode',
    ],
  },
  {
    kind: 'dataset_missing',
    needles: ['dataset_not_found', 'dataset_not_in_official_context', 'unknown dataset'],
  },
  {
    kind: 'field_non_compliant',
    needles: ['field_not_supported', 'field_non_compliant', 'validation_failed'],
  },
  {
    kind: 'expression_invalid',
    needles: [
      'expression_empty',
      'expression_unbalanced_parens',
      'expression_unknown_operator',
      'expression_null_bytes',
      'expression_invalid',
      'syntax error',
      'unknown operator',
    ],
  },
  {
    kind: 'network_timeout',
    needles: [
      'timed out',
      'timeout',
      'incompleteread',
      'incomplete read',
      'remote end closed',
      'connection reset',
      'connection aborted',
      '408',
      '504',
    ],
  },
  {
    kind: 'task_cancelled',
    needles: [
      'task_cancelled',
      'raw backend cancellation',
      'job cancelled',
      'aborted',
      'aborterror',
    ],
  },
  {
    kind: 'queue_blocked',
    needles: ['queue_blocked', 'jobs_full', 'queue full', 'max concurrent active jobs'],
  },
  {
    kind: 'local_service_unavailable',
    needles: [
      'connection refused',
      'service unavailable',
      'local service',
      'web server not running',
      'health check failed',
      '503',
    ],
  },
];

/**
 * Classify a frontend error (Error / response object / string) into an
 * ErrorKind.  Used as a fallback when the backend did not attach an
 * ``actionable`` payload.  Mirrors the backend classify_exception()
 * resolution: substring match against message + known status codes.
 *
 * Returns ``'network_timeout'`` as the least-misleading fallback when
 * nothing matches (avoids implying user fault or system-down).
 */
export function classifyError(err: unknown): ErrorKind {
  if (err == null) return 'network_timeout';

  // Status code shortcut (number or numeric string).
  const status =
    typeof err === 'number'
      ? err
      : typeof err === 'object' &&
          err !== null &&
          typeof (err as { status_code?: unknown }).status_code === 'number'
        ? (err as { status_code: number }).status_code
        : null;
  if (status !== null) {
    if (status === 401 || status === 403) return 'login_expired';
    if (status === 429) return 'official_rate_limited';
    if (status === 408 || status === 504) return 'network_timeout';
    if (status === 503) return 'local_service_unavailable';
  }

  const text = stringifyError(err).toLowerCase();
  if (!text) return 'network_timeout';

  // DOMException/AbortError → task_cancelled (user-initiated cancel).
  if (
    typeof DOMException !== 'undefined' &&
    err instanceof DOMException &&
    err.name === 'AbortError'
  ) {
    return 'task_cancelled';
  }

  for (const rule of ERROR_KIND_KEYWORDS) {
    for (const needle of rule.needles) {
      if (text.includes(needle)) return rule.kind;
    }
  }
  return 'network_timeout';
}

function stringifyError(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err instanceof Error) {
    const code = (err as { code?: string }).code;
    return [code || '', err.message || '', err.name || ''].join(' ');
  }
  if (typeof err === 'object' && err !== null) {
    const rec = err as Record<string, unknown>;
    const parts: string[] = [];
    for (const key of [
      'error_code',
      'error',
      'message',
      'status',
      'status_code',
      'user_error_kind',
    ]) {
      const value = rec[key];
      if (typeof value === 'string' && value) parts.push(value);
    }
    return parts.join(' ');
  }
  return String((err as string | number | boolean | null | undefined) || '');
}

// ── Builder (frontend-side fallback payload) ─────────────────────────────

/**
 * Minimal recovery_url mapping for kinds.  Mirrors the backend
 * ``RECOVERY_URLS`` dict so the frontend can render a recovery entry
 * even when only a kind is known (no full payload from backend).
 */
export const ERROR_KIND_RECOVERY_URL: Record<ErrorKind, string> = {
  login_expired: '/config',
  cache_unavailable: '/operations/refresh',
  official_rate_limited: '/backtests',
  simulation_concurrency_exceeded: '/backtests',
  dataset_missing: '/config',
  field_non_compliant: '/config',
  expression_invalid: '/candidates',
  network_timeout: '/backtests',
  task_cancelled: '/dashboard',
  queue_blocked: '/backtests',
  local_service_unavailable: '/dashboard',
};

/** Default Chinese cause/suggested_action text per kind (compact mirror of catalog). */
const FALLBACK_TEXT: Record<ErrorKind, { cause: string; action: string; severity: ErrorSeverity }> =
  {
    login_expired: {
      cause: '登录会话已失效或凭据过期。',
      action: '请前往系统配置重新测试连接。',
      severity: 'error',
    },
    cache_unavailable: {
      cause: '本地能力集缓存不可用。',
      action: '请在官方操作入口刷新官方能力集。',
      severity: 'warning',
    },
    official_rate_limited: {
      cause: 'BRAIN 官方接口限流（429）。',
      action: '请稍后重试或查看回测队列。',
      severity: 'warning',
    },
    simulation_concurrency_exceeded: {
      cause: 'BRAIN 回测并发槽位已满。',
      action: '请等待已有回测完成后再提交。',
      severity: 'warning',
    },
    dataset_missing: {
      cause: '指定的 Dataset 不在能力集中。',
      action: '请在系统配置中选择可用 Dataset。',
      severity: 'error',
    },
    field_non_compliant: {
      cause: '字段/参数不符合 BRAIN 平台规则。',
      action: '请检查字段名与取值范围。',
      severity: 'error',
    },
    expression_invalid: {
      cause: '表达式语法非法或包含未知算子。',
      action: '请在候选管理修正表达式后重试。',
      severity: 'error',
    },
    network_timeout: {
      cause: '网络请求超时。',
      action: '请稍后重试或检查网络状态。',
      severity: 'warning',
    },
    task_cancelled: {
      cause: '任务已取消。',
      action: '可在运行总览查看任务状态。',
      severity: 'info',
    },
    queue_blocked: {
      cause: '官方模拟队列阻塞。',
      action: '请在回测监控查看队列状态。',
      severity: 'warning',
    },
    local_service_unavailable: {
      cause: '本地 Web 服务未启动。',
      action: '请让维护者启动本地 Web 服务。',
      severity: 'error',
    },
  };

/** Recovery action id per kind (mirrors backend recovery_action_id). */
const RECOVERY_ACTION_ID: Record<ErrorKind, string> = {
  login_expired: 'reconnect_session',
  cache_unavailable: 'refresh_cache',
  official_rate_limited: 'review_official_slots',
  simulation_concurrency_exceeded: 'review_official_slots',
  dataset_missing: 'check_config',
  field_non_compliant: 'check_config',
  expression_invalid: 'fix_expression',
  network_timeout: 'wait_and_retry',
  task_cancelled: 'resume_or_restart',
  queue_blocked: 'review_official_slots',
  local_service_unavailable: 'restart_flow',
};

/**
 * Build an ActionableErrorPayload on the frontend side when the backend
 * did not provide one.  The text comes from FALLBACK_TEXT; the
 * ``context`` field is filled with whatever was supplied.
 */
export function buildActionableError(
  kind: ErrorKind,
  context?: Record<string, unknown>
): ActionableErrorPayload {
  const fallback = FALLBACK_TEXT[kind];
  return {
    kind,
    cause: fallback.cause,
    impact_scope: '',
    suggested_action: fallback.action,
    recovery_action_id: RECOVERY_ACTION_ID[kind],
    recovery_url: ERROR_KIND_RECOVERY_URL[kind],
    i18n_key: `error.${kind}`,
    severity: fallback.severity,
    context: context ?? {},
  };
}

// ──────────────────────────────────────────────────────────────────────────
// Type Guards (former index.ts)
// ──────────────────────────────────────────────────────────────────────────

/** Narrow unknown JSON to a plain object (not null, not array). */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** Narrow SSE event.data to SSECandidateEventData. */
export function isSSECandidateData(data: unknown): data is SSECandidateEventData {
  return isRecord(data);
}
