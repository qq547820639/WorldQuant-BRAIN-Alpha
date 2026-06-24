import type { Scorecard } from "./scoring";

// ── Candidate Types ───────────────────────────────────────────────────────

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
  severity: "ERROR" | "WARNING";
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
  | "candidates"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed";
