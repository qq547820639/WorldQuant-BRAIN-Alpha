import type { Candidate } from '@/types';
import { isRecord } from '@/types';
import type { CandidateCheckResult } from './types';
import { MIN_TARGET_POOL_SIZE, MAX_TARGET_POOL_SIZE } from './constants';

export function record(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function candidateText(value: unknown) {
  return String((value as string | number | boolean | null | undefined) || '');
}

export function candidateIdentity(candidate: Candidate) {
  return candidateIds(candidate)[0] || '';
}

export function candidateIds(
  candidate:
    | Pick<Candidate, 'alpha_id' | 'official_alpha_id' | 'simulation_id'>
    | CandidateCheckResult
) {
  return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
}

export function candidateCreatedAt(candidate: Candidate) {
  return new Date(candidate.created_at || candidate.updated_at || 0).getTime();
}

export function mostCommon(values: unknown[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    const text = candidateText(value);
    if (!text) continue;
    counts.set(text, (counts.get(text) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || '';
}

export function clampTargetPoolSize(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return MIN_TARGET_POOL_SIZE;
  return Math.min(Math.max(Math.trunc(parsed), MIN_TARGET_POOL_SIZE), MAX_TARGET_POOL_SIZE);
}

export function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, '').slice(0, maxLength);
}

export function numericResultField(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.trunc(number)) : 0;
}
