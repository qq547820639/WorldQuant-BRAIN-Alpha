/** OfficialOperations core: constants, types, formatters, error messages, readiness labels. */

import { knownApiErrorMessage } from '@/helpers/errorExperience';
import {
  readinessNextActionLabel,
  readinessProductionGapLabel,
  readinessReasonLabel,
} from '@/helpers/readinessLabels';
import type { BrainCredentials, JobStatus } from '@/types';
import { isRecord } from '@/types';

export const POLL_INTERVAL_MS = 2000;
export const SYNC_STATUS_FAILURE_LIMIT = 3;
export const SYNC_PROGRESS_STALL_WARNING_MS = 30_000;
export const SYNC_PROGRESS_STALL_STOP_MS = 90_000;
export const OPERATION_REQUEST_TIMEOUT_MS = 10000;
export const STOP_RETRY_AFTER_MS = 60_000;
export const MAX_LOG_ROWS = 80;
export const ACTIVE_SYNC_JOB_ID_KEY = 'brain_alpha_active_sync_job_id';

export interface OperationLogEntry {
  time: string;
  tone: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

export type OperationMode = 'idle' | 'context_refresh' | 'readiness' | 'checks';
export type OverviewTone = 'success' | 'warning' | 'neutral';
export type SyncStageKind = 'scan' | 'fields' | 'operators' | 'datasets' | 'other';
export type SyncRange = '3d' | '7d' | 'recent' | '6months' | 'all';

export interface SyncStageMetric {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  etaSeconds: number;
  ratePerSecond: number;
  pageNumber: number;
  expectedPages: number;
  pageSize: number;
  pageLimit: number;
  nextOffset: number;
  newUniqueItems: number;
  uniqueItems: number;
  confirmingTotalBoundary: boolean;
}

export interface SyncProgressMonitorState {
  jobId: string;
  signature: string;
  sinceMs: number;
  warned: boolean;
  interrupting: boolean;
}

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

export function isSessionInvalidResult(
  result: ({ ok?: boolean; error_code?: string; error?: string } & Partial<JobStatus>) | null
) {
  if (!result || result.ok !== false) return false;
  const errorCode = String(result.error_code || '').toUpperCase();
  const error = String(result.error || '').toLowerCase();
  return (
    errorCode === 'SESSION_INVALID' ||
    error.includes('session_invalid') ||
    error.includes('invalid local session')
  );
}

export function syncHistoryReadErrorTitle(raw: unknown) {
  return readableBackendText(raw) || '同步历史读取受限，无法展示原始错误详情。';
}

export function readableBackendText(raw: unknown) {
  const value = String((raw as string | number | boolean | null | undefined) || '').trim();
  const sharedMessage = knownApiErrorMessage(value);
  if (sharedMessage) return sharedMessage;
  const fieldRefreshMatch = value.match(/^Updating official fields cache:\s*(.+)$/);
  if (fieldRefreshMatch) return `正在刷新官方字段缓存: ${fieldRefreshMatch[1]}`;
  const operatorRefreshMatch = value.match(/^Updating official operators cache:\s*(.+)$/);
  if (operatorRefreshMatch) return `正在刷新官方算子缓存: ${operatorRefreshMatch[1]}`;
  const labels: Record<string, string> = {
    'Official context refreshed.': '官方上下文已刷新。',
    'candidate family lacks official simulation metrics': '候选族缺少官方仿真指标',
    'official context timeout': '官方上下文刷新超时，请稍后重试。',
    'unknown sync job': '找不到本次同步任务，请重新启动刷新。',
    'unknown job': '找不到本次任务，请重新启动流程。',
    JOB_NOT_FOUND: '找不到本次任务，请重新启动流程。',
    SESSION_INVALID:
      '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。',
    'invalid local session':
      '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。',
    OFFICIAL_CONTEXT_REFRESH_TIMEOUT: '官方上下文刷新超时，请稍后重试。',
  };
  if (labels[value]) return labels[value];
  if (isAllowedOfficialStatusText(value)) return value;
  return null;
}

function isAllowedOfficialStatusText(value: string) {
  if (!value) return false;
  return [
    /^官方上下文已刷新/,
    /^官方上下文刷新/,
    /^官方上下文刷新已停止/,
    /^正在刷新官方字段缓存/,
    /^正在刷新官方算子缓存/,
    /^云端同步完成/,
    /^连续读取刷新状态失败/,
    /^用户已停止本次官方上下文刷新/,
  ].some((pattern) => pattern.test(value));
}

export function countTitle(label: string, total: number) {
  return total > 0 ? `${label}（共 ${total}）` : label;
}

export function reasonCountText(row: { reason: string; count: number }) {
  return `${readinessReasonLabel(row.reason)} (${row.count})`;
}

export function findingText(row: { code?: string; message?: string }) {
  return readinessProductionGapLabel(row);
}

export function riskLevelLabel(level: string) {
  const normalized = String(level || '').toLowerCase();
  const labels: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低',
  };
  return labels[normalized] || (normalized ? '风险待确认' : '-');
}

export function actionStepLabel(step: string) {
  return readinessNextActionLabel(step);
}

export function formatOptionalNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(3);
}

export function formatLocalBacktestStatus(value: unknown, hasEvidence: boolean) {
  if (!hasEvidence) return '-';
  if (value === true) return '通过';
  if (value === false) return '未通过';
  return '-';
}
