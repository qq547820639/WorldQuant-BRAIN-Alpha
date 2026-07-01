/** Form validation and credentials payload helpers. */

import type { BrainCredentials } from '@/types';
import {
  CONFIG_TEXT_PATTERN,
  DEFAULT_NEUTRALIZATION_OPTIONS,
  DEFAULT_REGION_OPTIONS,
  DEFAULT_UNIVERSE_OPTIONS,
  MAX_CONFIG_TEXT_LENGTH,
} from './constants';
import { datasetAllowedValues, isAllowedOption, isIntegerInRange } from './helpers';
import type { ConfigForm, ConfigSchema } from './types';

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
