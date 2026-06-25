/** Shared type definitions for ConfigPanel sub-components. */

import type { ReactNode } from 'react';

export type SelectOption = string | { value: string; label: string };

export interface PartialConfig {
  environment?: string;
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
  settings?: {
    instrumentType?: string;
    region?: string;
    universe?: string;
    delay?: number;
    decay?: number;
    neutralization?: string;
    dataset?: string;
    truncation?: number;
    pasteurization?: string;
    unitHandling?: string;
    nanHandling?: string;
    language?: string;
    type?: string;
  };
  budget?: {
    max_candidates_per_cycle?: number;
    max_cycles?: number;
    retained_alpha_pool_size?: number;
    official_backtest_batch_size?: number;
    require_cloud_sync?: boolean;
  };
  thresholds?: {
    min_sharpe?: number;
    min_fitness?: number;
    min_turnover?: number;
    platform_max_turnover?: number;
    max_self_correlation?: number;
    max_weight_concentration?: number;
  };
  scoring?: {
    prior_layer_weight?: number;
    empirical_layer_weight?: number;
    checklist_layer_weight?: number;
    market_regime?: string;
  };
  ops?: {
    settings?: PartialConfig['settings'];
    budget?: PartialConfig['budget'];
    thresholds?: PartialConfig['thresholds'];
    scoring?: PartialConfig['scoring'];
  };
}

export interface ConfigForm {
  environment: string;
  autoSubmit: boolean;
  instrumentType: string;
  region: string;
  universe: string;
  delay: number;
  decay: number;
  neutralization: string;
  dataset: string;
  pasteurization: string;
  unitHandling: string;
  nanHandling: string;
  language: string;
  alphaType: string;
  candidates: number;
  cycles: number;
  poolSize: number;
  backtestBatchSize: number;
  requireCloudSync: boolean;
  minSharpe: number;
  minFitness: number;
  minTurnover: number;
  platformMaxTurnover: number;
  maxSelfCorrelation: number;
  maxWeightConcentration: number;
}

export interface ConfigSchema {
  settings_options?: Record<string, Array<string | number>>;
  dataset_options?: Array<{
    id: string;
    name?: string;
    field_count?: number;
    category?: string;
    label?: string;
  }>;
  scoring?: Record<string, unknown>;
  scoring_weights?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ConfigSectionProps {
  title: string;
  description?: string;
  children: ReactNode;
}

export interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export interface PasswordFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export interface NumberFieldProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}

export interface SelectFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  disabled?: boolean;
}

export interface CheckboxFieldProps {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}

export interface ConfigValueProps {
  label: string;
  value: unknown;
}
