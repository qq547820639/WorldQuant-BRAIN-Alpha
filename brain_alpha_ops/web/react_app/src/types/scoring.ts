// ── Official Scoring Types ───────────────────────────────────────────────

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
  confidence_level: "high" | "medium" | "low";
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
