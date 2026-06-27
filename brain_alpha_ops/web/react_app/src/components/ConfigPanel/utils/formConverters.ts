/** Form <-> Config conversion functions for ConfigPanel. */

import type { ConfigForm, PartialConfig } from './types';
import { asRecord, booleanValue, numberValue, stringValue } from './helpers';

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
    candidates: form.candidates,
    cycles: form.cycles,
    poolSize: form.poolSize,
    backtestBatchSize: form.backtestBatchSize,
    requireCloudSync: form.requireCloudSync,
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
      environment: String(source.environment || 'production'),
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
    } as unknown);
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
