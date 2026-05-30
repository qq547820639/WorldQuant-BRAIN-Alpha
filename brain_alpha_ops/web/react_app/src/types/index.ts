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
  | "dashboard"
  | "candidates"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed"
  | "cloud"
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
