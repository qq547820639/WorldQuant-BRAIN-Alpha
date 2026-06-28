import { ACTIVE_SYNC_JOB_ID_KEY, OPERATION_REQUEST_TIMEOUT_MS } from './constants';
import type { OperationLogEntry } from './constants';
import type { BrainCredentials, JobStatus } from '@/types';
import { isRecord } from '@/types';

export function formatClock(date = new Date()): string {
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((value) => String(value).padStart(2, '0'))
    .join(':');
}

export function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return '0s';
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.round(totalSeconds % 60);
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function formatCount(value: number): string {
  return Math.max(0, Math.trunc(value)).toLocaleString('zh-CN');
}

export function firstPositiveFloat(...values: number[]): number {
  return values.find((value) => Number.isFinite(value) && value > 0) || 0;
}

export function shortOperationId(value: string): string {
  const text = String(value || '').trim();
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}

export function credentialsPayload(credentials?: BrainCredentials): Record<string, string> {
  const payload: Record<string, string> = {};
  const username = credentials?.username.trim() || '';
  const password = credentials?.password || '';
  const token = credentials?.token.trim() || '';
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}

export function hasPageCredentials(credentials?: BrainCredentials): boolean {
  return Boolean(
    credentials?.username?.trim() || credentials?.password || credentials?.token?.trim()
  );
}

export function saveStoredSyncJobId(jobId: string): void {
  const value = String(jobId || '').trim();
  if (value) {
    try {
      sessionStorage.setItem(ACTIVE_SYNC_JOB_ID_KEY, value);
    } catch {
      console.warn('OfficialOperations: non-critical operation skipped');
    }
  }
}

export function loadStoredSyncJobId(): string {
  try {
    return String(sessionStorage.getItem(ACTIVE_SYNC_JOB_ID_KEY) || '').trim();
  } catch {
    return '';
  }
}

export function clearStoredSyncJobId(): void {
  try {
    sessionStorage.removeItem(ACTIVE_SYNC_JOB_ID_KEY);
  } catch {
    console.warn('OfficialOperations: non-critical operation skipped');
  }
}

export function logTone(tone: OperationLogEntry['tone']): string {
  if (tone === 'success') return 'text-positive';
  if (tone === 'warning') return 'text-warning';
  if (tone === 'error') return 'text-negative';
  return 'text-text-secondary';
}

export function logDotTone(tone: OperationLogEntry['tone']): string {
  if (tone === 'success') return 'status-dot status-dot-active';
  if (tone === 'warning') return 'status-dot status-dot-warning';
  if (tone === 'error') return 'status-dot status-dot-error';
  return 'status-dot status-dot-idle';
}

export function operationFailureMessage(result: unknown, fallback: string): string {
  if (!result) return fallback;
  const error = isRecord(result) ? result.error : undefined;
  if (typeof error === 'string' && error.trim()) return error.trim();
  return fallback;
}

export function requestDeadline(): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OPERATION_REQUEST_TIMEOUT_MS);
  return {
    signal: controller.signal,
    clear: () => clearTimeout(timer),
  };
}

export function checkResultCount(
  payload: { count?: number; items?: unknown; checks?: unknown } | null
): number {
  if (!payload) return 0;
  const direct = Number(payload.count);
  if (Number.isFinite(direct) && direct >= 0) return direct;
  if (Array.isArray(payload.items)) return payload.items.length;
  if (Array.isArray(payload.checks)) return payload.checks.length;
  return 0;
}

export function resultNumberField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!isRecord(result)) return 0;
  const value = Number(result[field]);
  return Number.isFinite(value) ? value : 0;
}

export function resultStringField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!isRecord(result)) return '';
  return String((result[field] as string | number | boolean | null | undefined) || '');
}

export function firstPositiveNumber(...values: Array<number | null | undefined>) {
  const value = values.find((item) => Number.isFinite(item) && Number(item) > 0);
  return Number.isFinite(value) ? Number(value) : 0;
}

export function numberField(source: Record<string, unknown> | undefined, field: string) {
  const value = Number(source?.[field]);
  return Number.isFinite(value) ? value : 0;
}

export function stringField(source: Record<string, unknown> | undefined, field: string) {
  const value = source?.[field];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

export function booleanField(source: Record<string, unknown> | undefined, field: string) {
  const value = source?.[field];
  return typeof value === 'boolean' ? value : undefined;
}
