/** ConfigPanel utilities — constants, types, helpers, form converters, validation.
 *
 *  Merges the previously fragmented utils/ subdirectory (constants.ts, types.ts,
 *  helpers.ts, formConverters.ts, validation.ts) into a single utils.ts entry.
 *  All exports are preserved for backward-compatible import paths. */
import type { ReactNode } from 'react';
import { isRecord, type BrainCredentials } from '@/types';

// ──────────────────────────────────────────────────────────────────────────
// constants — default configuration constants and patterns
// ──────────────────────────────────────────────────────────────────────────

export const MAX_CONFIG_TEXT_LENGTH = 128;
export const CONFIG_TEXT_PATTERN = /^[A-Za-z0-9_.:-]*$/;
export const DEFAULT_REGION_OPTIONS = ['USA', 'CHN', 'EUR', 'GLB'];
export const DEFAULT_UNIVERSE_OPTIONS = ['TOP3000', 'TOP1000', 'TOP500'];
export const DEFAULT_DELAY_OPTIONS = ['0', '1'];
export const DEFAULT_NEUTRALIZATION_OPTIONS = [
  'SUBINDUSTRY',
  'INDUSTRY',
  'SECTOR',
  'MARKET',
  'NONE',
];
export const DEFAULT_INSTRUMENT_TYPE_OPTIONS = ['EQUITY'];
export const DEFAULT_PASTEURIZATION_OPTIONS = ['ON', 'OFF'];
export const DEFAULT_UNIT_HANDLING_OPTIONS = ['VERIFY', 'RAW', 'NONE'];
export const DEFAULT_NAN_HANDLING_OPTIONS = ['ON', 'OFF'];
export const DEFAULT_LANGUAGE_OPTIONS = ['FASTEXPR'];
export const DEFAULT_ALPHA_TYPE_OPTIONS = ['REGULAR', 'POWER_POOL', 'ATOM', 'PYRAMID'];

// ──────────────────────────────────────────────────────────────────────────
// types — shared type definitions for ConfigPanel sub-components
// ──────────────────────────────────────────────────────────────────────────

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

// ──────────────────────────────────────────────────────────────────────────
// helpers — generic utility helpers
// ──────────────────────────────────────────────────────────────────────────

export function sanitizeConfigText(value: string): string {
  return value.replace(/[\x00-\x1F\x7F]/g, '').slice(0, MAX_CONFIG_TEXT_LENGTH);
}

export function normalizeSelectOptions(
  options: SelectOption[]
): Array<{ value: string; label: string }> {
  return options.map((option) =>
    typeof option === 'string' ? { value: option, label: option } : option
  );
}

export function datasetSelectOptions(
  schema: ConfigSchema | undefined,
  _currentDataset: string
): Array<{ value: string; label: string }> {
  const choices: Array<{ value: string; label: string }> = [];
  const rows = schema?.dataset_options || [];
  for (const row of rows) {
    const value = String(row.id || '').trim();
    if (!value) continue;
    const label = datasetOptionLabel(row, value);
    choices.push({ value, label });
  }
  for (const value of schema?.settings_options?.dataset?.map(String).filter(Boolean) || []) {
    if (!choices.some((choice) => choice.value === value)) {
      choices.push({ value, label: value });
    }
  }
  return choices;
}

export function datasetAllowedValues(schema: ConfigSchema | undefined): string[] {
  return datasetSelectOptions(schema, '').map((option) =>
    typeof option === 'string' ? option : option.value
  );
}

export function datasetOptionLabel(
  row: { name?: string; field_count?: number; label?: string },
  fallback: string
): string {
  if (row.label) return row.label;
  const name = row.name ? ` - ${row.name}` : '';
  const fieldCount = Number(row.field_count || 0);
  const count = Number.isFinite(fieldCount) && fieldCount > 0 ? `, ${fieldCount} fields` : '';
  return `${fallback}${name}${count}`;
}

export function allowedOptionValues(
  options: ConfigSchema['settings_options'] | undefined,
  key: string,
  fallback: string[]
): string[] {
  const values = options?.[key]?.map(String).filter(Boolean);
  return values?.length ? values : fallback;
}

export function isAllowedOption(
  options: ConfigSchema['settings_options'] | undefined,
  key: string,
  value: string,
  fallback: string[]
): boolean {
  return allowedOptionValues(options, key, fallback).includes(value);
}

export function isIntegerInRange(
  value: number,
  min: number,
  max = Number.POSITIVE_INFINITY
): boolean {
  return Number.isInteger(value) && value >= min && value <= max;
}

export function parseNumber(value: string): number {
  return value.trim() ? Number(value) : Number.NaN;
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

export function stringValue(value: unknown, fallback: string): string {
  return typeof value === 'string' ? value : fallback;
}

export function numberValue(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function booleanValue(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

// ──────────────────────────────────────────────────────────────────────────
// formConverters — form <-> Config conversion functions
// ──────────────────────────────────────────────────────────────────────────

export function payloadFromForm(form: ConfigForm): Record<string, unknown> {
  return {
    settings: {
      instrumentType: form.instrumentType,
      region: form.region,
      universe: form.universe,
      delay: form.delay,
      decay: form.decay,
      neutralization: form.neutralization,
      dataset: form.dataset,
      pasteurization: form.pasteurization,
      unitHandling: form.unitHandling,
      nanHandling: form.nanHandling,
      language: form.language,
      type: form.alphaType,
    },
    budget: {
      max_candidates_per_cycle: form.candidates,
      max_cycles: form.cycles,
      retained_alpha_pool_size: form.poolSize,
      official_backtest_batch_size: form.backtestBatchSize,
      require_cloud_sync: form.requireCloudSync,
    },
    thresholds: {
      min_sharpe: form.minSharpe,
      min_fitness: form.minFitness,
      min_turnover: form.minTurnover,
      platform_max_turnover: form.platformMaxTurnover,
      max_self_correlation: form.maxSelfCorrelation,
      max_weight_concentration: form.maxWeightConcentration,
    },
  };
}

export function formFromConfig(config: PartialConfig | null): ConfigForm {
  if (!config) {
    return {
      environment: '',
      autoSubmit: false,
      instrumentType: 'EQUITY',
      region: 'USA',
      universe: 'TOP3000',
      delay: 1,
      decay: 10,
      neutralization: 'SUBINDUSTRY',
      dataset: '',
      pasteurization: 'ON',
      unitHandling: 'VERIFY',
      nanHandling: 'ON',
      language: 'FASTEXPR',
      alphaType: 'REGULAR',
      candidates: 20,
      cycles: 10,
      poolSize: 10,
      backtestBatchSize: 3,
      requireCloudSync: false,
      minSharpe: 1.25,
      minFitness: 1.0,
      minTurnover: 0.01,
      platformMaxTurnover: 0.7,
      maxSelfCorrelation: 0.7,
      maxWeightConcentration: 0.1,
    };
  }
  const ops = config.ops || {};
  const settings = ops.settings || config.settings || {};
  const budget = ops.budget || config.budget || {};
  const thresholds = ops.thresholds || config.thresholds || {};
  return {
    environment: '',
    autoSubmit: booleanValue(config.autoSubmit, false),
    instrumentType: stringValue(settings.instrumentType, 'EQUITY'),
    region: stringValue(settings.region, 'USA'),
    universe: stringValue(settings.universe, 'TOP3000'),
    delay: numberValue(settings.delay, 1),
    decay: numberValue(settings.decay, 10),
    neutralization: stringValue(settings.neutralization, 'SUBINDUSTRY'),
    dataset: stringValue(settings.dataset, ''),
    pasteurization: stringValue(settings.pasteurization, 'ON'),
    unitHandling: stringValue(settings.unitHandling, 'VERIFY'),
    nanHandling: stringValue(settings.nanHandling, 'ON'),
    language: stringValue(settings.language, 'FASTEXPR'),
    alphaType: stringValue(settings.type, 'REGULAR'),
    candidates: numberValue(budget.max_candidates_per_cycle, 20),
    cycles: numberValue(budget.max_cycles, 10),
    poolSize: numberValue(budget.retained_alpha_pool_size, 10),
    backtestBatchSize: numberValue(budget.official_backtest_batch_size, 3),
    requireCloudSync: booleanValue(budget.require_cloud_sync, false),
    minSharpe: numberValue(thresholds.min_sharpe, 1.25),
    minFitness: numberValue(thresholds.min_fitness, 1.0),
    minTurnover: numberValue(thresholds.min_turnover, 0.01),
    platformMaxTurnover: numberValue(thresholds.platform_max_turnover, 0.7),
    maxSelfCorrelation: numberValue(thresholds.max_self_correlation, 0.7),
    maxWeightConcentration: numberValue(thresholds.max_weight_concentration, 0.1),
  };
}

export function formFromImport(imported: Record<string, unknown>, current: ConfigForm): ConfigForm {
  const root = asRecord(imported) || {};
  const source = asRecord(root.config) || root;
  if (asRecord(source.ops)) {
    return formFromConfig({
      environment: String(
        (source.environment as string | number | boolean | null | undefined) || 'production'
      ),
      ops: asRecord(source.ops) || {},
      settings: asRecord(source.settings) || {},
      budget: asRecord(source.budget) || {},
      thresholds: asRecord(source.thresholds) || {},
      scoring: asRecord(source.scoring) || undefined,
      autoSubmit: false,
      maxWeightConcentration: numberValue(
        source.maxWeightConcentration,
        current.maxWeightConcentration
      ),
    } as unknown as PartialConfig);
  }
  const settings = asRecord(source.settings) || {};
  const budget = asRecord(source.budget) || {};
  const thresholds = asRecord(source.thresholds) || {};
  return {
    ...current,
    instrumentType: stringValue(settings.instrumentType, current.instrumentType),
    region: stringValue(settings.region, current.region),
    universe: stringValue(settings.universe, current.universe),
    delay: numberValue(settings.delay, current.delay),
    decay: numberValue(settings.decay, current.decay),
    neutralization: stringValue(settings.neutralization, current.neutralization),
    dataset: stringValue(settings.dataset, current.dataset),
    pasteurization: stringValue(settings.pasteurization, current.pasteurization),
    unitHandling: stringValue(settings.unitHandling, current.unitHandling),
    nanHandling: stringValue(settings.nanHandling, current.nanHandling),
    language: stringValue(settings.language, current.language),
    alphaType: stringValue(settings.type, current.alphaType),
    candidates: numberValue(budget.max_candidates_per_cycle, current.candidates),
    cycles: numberValue(budget.max_cycles, current.cycles),
    poolSize: numberValue(budget.retained_alpha_pool_size, current.poolSize),
    backtestBatchSize: numberValue(budget.official_backtest_batch_size, current.backtestBatchSize),
    requireCloudSync: booleanValue(budget.require_cloud_sync, current.requireCloudSync),
    minSharpe: numberValue(thresholds.min_sharpe, current.minSharpe),
    minFitness: numberValue(thresholds.min_fitness, current.minFitness),
    minTurnover: numberValue(thresholds.min_turnover, current.minTurnover),
    platformMaxTurnover: numberValue(thresholds.platform_max_turnover, current.platformMaxTurnover),
    maxSelfCorrelation: numberValue(thresholds.max_self_correlation, current.maxSelfCorrelation),
    maxWeightConcentration: numberValue(
      thresholds.max_weight_concentration,
      current.maxWeightConcentration
    ),
  };
}

// ──────────────────────────────────────────────────────────────────────────
// validation — form validation and credentials payload helpers
// ──────────────────────────────────────────────────────────────────────────

export function validateForm(form: ConfigForm, schema: ConfigSchema | undefined): string | null {
  if (form.dataset.length > MAX_CONFIG_TEXT_LENGTH)
    return `数据集长度不能超过 ${MAX_CONFIG_TEXT_LENGTH} 个字符。`;
  if (!CONFIG_TEXT_PATTERN.test(form.dataset))
    return '数据集只能包含字母、数字、下划线、短横线、点或冒号。';
  if (!isIntegerInRange(form.delay, 0, 1)) return '延迟值必须为 0 或 1';
  if (!isIntegerInRange(form.candidates, 1, 1000)) return '候选数必须在 1-1000 之间';
  if (!isIntegerInRange(form.cycles, 1, 1000)) return '周期数必须在 1-1000 之间';
  if (!isIntegerInRange(form.poolSize, 1, 1000)) return '池大小必须在 1-1000 之间';
  if (!isIntegerInRange(form.backtestBatchSize, 1, 100)) return '回测批次大小必须在 1-100 之间';
  if (!isAllowedOption(schema?.settings_options, 'region', form.region, DEFAULT_REGION_OPTIONS))
    return '不支持的区域。';
  if (
    !isAllowedOption(schema?.settings_options, 'universe', form.universe, DEFAULT_UNIVERSE_OPTIONS)
  )
    return '不支持的股票池。';
  if (
    !isAllowedOption(
      schema?.settings_options,
      'neutralization',
      form.neutralization,
      DEFAULT_NEUTRALIZATION_OPTIONS
    )
  )
    return '不支持的中性化方式。';
  if (schema?.dataset_options?.length && !datasetAllowedValues(schema).includes(form.dataset))
    return '不支持的数据集，请从下拉列表选择。';
  return null;
}

export function credentialsPayload(credentials: BrainCredentials): Record<string, string> {
  const payload: Record<string, string> = {};
  const username = credentials.username?.trim() || '';
  const password = credentials.password || '';
  const token = credentials.token?.trim() || '';
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}
