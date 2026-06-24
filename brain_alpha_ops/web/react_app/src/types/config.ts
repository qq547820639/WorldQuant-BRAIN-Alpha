// ── Pipeline / Run Types ──────────────────────────────────────────────────

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
