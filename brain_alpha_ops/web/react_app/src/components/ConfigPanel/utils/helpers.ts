/** Generic utility helpers for ConfigPanel. */

import { isRecord } from '@/types';
import { MAX_CONFIG_TEXT_LENGTH } from './constants';
import type { ConfigSchema, SelectOption } from './types';

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
