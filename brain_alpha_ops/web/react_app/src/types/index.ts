/** Core TypeScript type definitions for the BRAIN Alpha Ops web console. */

// ── API Response Types ────────────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  ok: boolean;
  error_code?: string;
  error?: string;
  data?: T;
}

export interface JobStatus {
  job_id: string;
  task_id?: string;
  status: "idle" | "running" | "completed" | "failed" | "cancelled";
  phase?: string;
  cycle?: number;
  max_cycles?: number;
  started_at?: string;
  percent_complete?: number | null;
  eta_seconds?: number;
  status_message?: string;
  result?: unknown;
  error?: string;
  progress?: JobProgress;
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

export type ProgressLifecycle = "idle" | "loading" | "progress" | "success" | "error";

export interface UnifiedProgress {
  task_id?: string;
  job_id?: string;
  phase?: string;
  phase_label?: string;
  status?: string;
  status_message?: string;
  message?: string;
  percent?: number | null;
  percent_complete?: number | null;
  eta_seconds?: number | null;
  done?: number;
  checked?: number;
  submitted?: number;
  scanned?: number;
  total?: number;
  error?: string;
}

// ── Candidate Types ───────────────────────────────────────────────────────

export interface Candidate {
  alpha_id: string;
  official_alpha_id?: string;
  simulation_id?: string;
  expression: string;
  family: string;
  hypothesis: string;
  lifecycle_status: string;
  scorecard?: Scorecard;
  official_metrics?: OfficialMetrics;
  gate?: QualityGate;
  decision_band?: string;
  data_fields?: string[];
  operators?: string[];
  source_tags?: string[];
  dataset_id?: string;
  local_quality?: LocalQuality;
  alpha_output_config?: AlphaOutputConfig;
  quality_diagnosis?: QualityDiagnosis;
  submission?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
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

export interface Scorecard {
  total_score: number;
  prior_score: number;
  empirical_score: number;
  checklist_score: number;
  decision_band: string;
  attribution?: ScoreAttribution[];
}

export interface ScoreAttribution {
  dimension: string;
  score: number;
  weight: number;
  sub_items?: ScoreAttribution[];
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
  failed_reasons?: string[];
  failed_checks?: GateCheck[];
}

export interface GateCheck {
  name: string;
  passed: boolean;
  detail: string;
  severity: "ERROR" | "WARNING";
}

// ── Official Scoring Types ───────────────────────────────────────────────

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

// ── Pipeline / Run Types ──────────────────────────────────────────────────

export interface RunConfig {
  environment: string;
  auto_submit: boolean;
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

// ── SSE Event Types ───────────────────────────────────────────────────────

export interface SSEEvent {
  type?: "progress" | "candidate" | "backtest" | "submission" | "error" | "complete";
  ok?: boolean;
  job_id?: string;
  task_id?: string;
  status?: string;
  phase?: string;
  percent_complete?: number | null;
  eta_seconds?: number;
  status_message?: string;
  progress?: JobProgress;
  result?: unknown;
  error?: string;
  data?: Record<string, unknown>;
}

// ── Cloud / Snapshot Types ────────────────────────────────────────────────

export interface CloudAlphaSummary {
  source: string;
  count: number;
  submitted_count: number;
  passed_unsubmitted_count: number;
  failed_unsubmitted_count: number;
  is_stale: boolean;
  sample_alphas: CloudAlpha[];
}

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
  official_api_called?: boolean;
  ready_to_submit?: boolean;
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

// ── UI State Types ────────────────────────────────────────────────────────

export type TabId =
  | "candidates"
  | "official_backtests"
  | "quality_check"
  | "submission_confirm"
  | "checkpoint_status"
  | "cloud"
  | "dashboard"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed"
  | "lifecycle"
  | "research_memory"
  | "research_knowledge"
  | "research_observability"
  | "prompt_runs"
  | "sqlite_indexes"
  | "robustness"
  | "scoring"
  | "submission"
  | "config"
  | "knowledge";

export interface Toast {
  id: string;
  type: "success" | "error" | "warning" | "info";
  message: string;
  duration_ms?: number;
  action_label?: string;
  on_action?: () => void;
}

/**
 * Card-based navigation view identifier.
 * A subset of TabId used by the StateCards detail view routing.
 */
export type CardViewId =
  | "candidates"
  | "official_backtests"
  | "quality_check"
  | "submission_confirm"
  | "config"
  | "checkpoint_status"
  | "cloud";
