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
  status: "idle" | "running" | "completed" | "failed" | "cancelled";
  phase: string;
  cycle: number;
  max_cycles: number;
  started_at: string;
  progress?: JobProgress;
}

export interface JobProgress {
  candidates_generated: number;
  candidates_passed: number;
  backtests_completed: number;
  backtests_pending: number;
  submissions: number;
  elapsed_seconds: number;
}

// ── Candidate Types ───────────────────────────────────────────────────────

export interface Candidate {
  alpha_id: string;
  official_alpha_id?: string;
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

// ── Pipeline / Run Types ──────────────────────────────────────────────────

export interface RunConfig {
  environment: string;
  auto_submit: boolean;
  settings: BrainSettings;
  budget: BudgetConfig;
  thresholds: ThresholdConfig;
  scoring: ScoringConfig;
}

export interface BrainSettings {
  region: string;
  universe: string;
  delay: number;
  decay: number;
  neutralization: string;
  dataset?: string;
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
  type: "progress" | "candidate" | "backtest" | "submission" | "error" | "complete";
  data: Record<string, unknown>;
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

export type TabId = "dashboard" | "candidates" | "scoring" | "submission" | "config" | "knowledge";

export interface Toast {
  id: string;
  type: "success" | "error" | "warning" | "info";
  message: string;
  duration_ms?: number;
}
