/** Shared utilities for SnapshotPanel sub-components. */

import { knownApiErrorMessage } from '@/helpers/errorExperience';
import { isRecord } from '@/types';

export const MAX_FILTER_LENGTH = 200;
export const RAW_SNAPSHOT_TEXT_PATTERN =
  /(?:raw\s+backend|raw_backend|RAW_BACKEND|SESSION_INVALID|session_invalid|invalid local session|unknown sync job|unknown job|csrf[_-]?token|session[_-]?id|access[_-]?token|refresh[_-]?token|password|passwd|pwd|set[_-]?cookie|cookie|authorization|client[_-]?secret|api[_-]?key)/i;
export const LOCAL_SNAPSHOT_PATH_PATTERN =
  /(?:\/Users\/|\/Volumes\/|\/private\/tmp\/|\/tmp\/|[A-Za-z]:\\|run_history\.json|Traceback|File\s+")/i;

export const SNAPSHOT_STATUS_LABELS: Record<string, string> = {
  active: '活跃',
  analytics: '趋势',
  blocked: '已阻断',
  cancelled: '已取消',
  canceled: '已取消',
  completed: '已完成',
  complete: '已完成',
  delta: '变化',
  done: '已完成',
  error: '错误',
  fail: '失败',
  failed: '失败',
  false: '未通过',
  missing: '缺失',
  pass: '通过',
  passed: '通过',
  pending: '等待中',
  production: '生产中',
  queued: '排队中',
  ready: '就绪',
  recorded: '已记录',
  rejected: '已拒绝',
  resume_available: '可续跑',
  review: '复核中',
  running: '运行中',
  stale: '需刷新',
  stopped: '已停止',
  submitted: '已提交',
  success: '成功',
  true: '通过',
  unknown: '状态待确认',
  warn: '警告',
  warning: '警告',
};

export type SnapshotRow = {
  id: string;
  kind: string;
  title: string;
  status: string;
  metric: string;
  detail: string;
  timestamp: string;
};

export type SnapshotMetric = {
  label: string;
  value: string;
};

export function text(value: unknown): string {
  if (value === undefined || value === null) return '';
  return String(value);
}

export function record(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function truthy(value: unknown): boolean {
  return value === true || value === 'true' || value === 'True' || value === 1 || value === '1';
}

export function safeSnapshotDisplayText(value: unknown, fallback: string): string {
  const raw = text(value).trim();
  if (!raw) return '';
  if (
    knownApiErrorMessage(raw) ||
    RAW_SNAPSHOT_TEXT_PATTERN.test(raw) ||
    LOCAL_SNAPSHOT_PATH_PATTERN.test(raw)
  )
    return fallback;
  return raw;
}

export function snapshotStatusLabel(value: unknown): string {
  const raw = text(value).trim();
  if (!raw) return '';
  const known = knownApiErrorMessage(raw);
  if (known) return known;
  if (RAW_SNAPSHOT_TEXT_PATTERN.test(raw)) return '状态待确认';
  const normalized = raw.toLowerCase();
  return SNAPSHOT_STATUS_LABELS[normalized] || '状态待确认';
}

export function safeSnapshotDetail(value: unknown): string {
  const raw = text(value).trim();
  if (!raw) return '';
  const known = knownApiErrorMessage(raw);
  if (known) return known;
  if (RAW_SNAPSHOT_TEXT_PATTERN.test(raw) || LOCAL_SNAPSHOT_PATH_PATTERN.test(raw))
    return '详情待确认';
  return raw;
}

export function statusBadge(status: string): string {
  const normalized = status.toLowerCase();
  if (
    [
      'ready',
      'pass',
      'passed',
      'true',
      'submitted',
      'production',
      '就绪',
      '通过',
      '已提交',
      '生产中',
      '成功',
      '已完成',
      '活跃',
      '可续跑',
    ].some((item) => normalized.includes(item))
  )
    return 'badge badge-positive';
  if (
    [
      'fail',
      'false',
      'missing',
      'blocked',
      'error',
      'rejected',
      '失败',
      '未通过',
      '缺失',
      '阻断',
      '错误',
      '已拒绝',
    ].some((item) => normalized.includes(item))
  )
    return 'badge badge-negative';
  if (
    ['warn', 'stale', 'caution', 'unknown', '警告', '需刷新', '需注意', '状态待确认'].some((item) =>
      normalized.includes(item)
    )
  )
    return 'badge badge-warning';
  return 'badge badge-neutral';
}

export function isSnapshotPassStatus(status: string): boolean {
  return ['pass', 'passed', 'ready', 'true', '通过', '成功', '已完成', '就绪'].includes(
    status.trim().toLowerCase()
  );
}

export function metricText(label: string, value: unknown): string {
  if (value === undefined || value === null || value === '') return '';
  if (typeof value === 'number')
    return `${label}:${Number.isInteger(value) ? value : value.toFixed(3)}`;
  const parsed = Number(value);
  if (Number.isFinite(parsed) && String(value).trim() !== '')
    return `${label}:${Number.isInteger(parsed) ? parsed : parsed.toFixed(3)}`;
  return `${label}:${text(value)}`;
}

export function ratioText(numerator: unknown, denominator: unknown): string {
  return `${countText(numerator)}/${countText(denominator)}`;
}

export function countText(value: unknown): string {
  if (value === undefined || value === null || value === '') return '0';
  const parsed = Number(value);
  if (Number.isFinite(parsed))
    return String(Number.isInteger(parsed) ? parsed : Number(parsed.toFixed(3)));
  return safeSnapshotDisplayText(value, '0') || '0';
}

export function sanitizeTextInput(value: string, maxLength: number): string {
  return value.replace(/[\x00-\x1F\x7F]/g, '').slice(0, maxLength);
}

export function formatOptionalNumber(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return '-';
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(3);
}

export function formatLocalBacktestStatus(value: unknown, hasEvidence: boolean): string {
  if (!hasEvidence) return '-';
  if (value === true) return '通过';
  if (value === false) return '未通过';
  return '-';
}

export type SnapshotPayload = Record<string, unknown>;

export function compactJoin(values: string[]): string {
  return values.filter(Boolean).join(' ');
}

export function rowId(row: SnapshotPayload, fallback: string): string {
  return text(
    row.alpha_id ||
      row.official_alpha_id ||
      row.simulation_id ||
      row.id ||
      row.checkpoint_id ||
      row.knowledge_id ||
      row.entry_id ||
      row.run_id ||
      row.prompt_digest ||
      row.expression_fingerprint ||
      fallback
  );
}

export function dedupeSnapshotRows(rows: SnapshotRow[]): SnapshotRow[] {
  const seen = new Set<string>();
  const result: SnapshotRow[] = [];
  for (const row of rows) {
    const key = `${row.kind}:${row.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(row);
  }
  return result;
}

export function dedupeRows(rows: unknown[]): SnapshotPayload[] {
  const seen = new Set<string>();
  const result: SnapshotPayload[] = [];
  for (const item of rows.map(record)) {
    const key = rowId(item, text(result.length));
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

export function namedRows(kind: string, rows: unknown[], titleKey: string): SnapshotRow[] {
  return rows.map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `${kind}_${index}`),
      kind,
      title: text(row[titleKey] || row.name || row.reason || row.id || `${kind}_${index + 1}`),
      status: text(row.status || row.pass_fail || row.ok),
      metric: compactJoin([
        metricText('count', row.count ?? row.record_count),
        metricText('rate', row.success_rate ?? row.failure_rate),
        metricText('score', row.avg_score ?? row.max_score ?? row.score),
      ]),
      detail: text(
        row.detail ||
          row.summary ||
          row.body ||
          row.expression ||
          row.expression_canonical ||
          row.error
      ),
      timestamp: text(row.timestamp || row.updated_at || row.created_at),
    };
  });
}

export function signalRows(kind: string, rows: unknown[], status: string): SnapshotRow[] {
  return rows.map((item, index) => ({
    id: `${kind}_${index}`,
    kind,
    title: `${kind}_${index + 1}`,
    status,
    metric: '',
    detail: text(item),
    timestamp: '',
  }));
}

export function rowText(row: SnapshotRow): string {
  return [
    safeSnapshotDisplayText(row.id, ''),
    displayKind(row.kind),
    row.title,
    row.status,
    row.metric,
    row.detail,
    row.timestamp,
  ]
    .join(' ')
    .toLowerCase();
}

export function displayKind(kind: string): string {
  const labels: Record<string, string> = {
    checkpoint: '续跑记录',
    history: '历史记录',
    comparison: '对比',
    analytics: '趋势',
    lifecycle: '生命周期',
    replay_audit: '回放审计',
    replay_decision: '决策审计',
    replay_scientific: '科学审计',
  };
  return labels[kind] || safeSnapshotDisplayText(kind, '类型待确认') || '类型待确认';
}

export function normalizeSnapshotRow(row: SnapshotRow): SnapshotRow {
  return {
    ...row,
    title: safeSnapshotDisplayText(row.title || row.id, '记录待确认'),
    status: snapshotStatusLabel(row.status),
    metric: safeSnapshotDisplayText(row.metric, '指标待确认'),
    detail: safeSnapshotDetail(row.detail),
    timestamp: safeSnapshotDisplayText(row.timestamp, '时间待确认'),
  };
}

export function defaultMetrics(payload: SnapshotPayload, rows: SnapshotRow[]): SnapshotMetric[] {
  return [
    { label: '行数', value: String(rows.length) },
    { label: '来源', value: text(payload.source || '快照') },
    { label: '版本', value: text(payload.schema_version || '-') },
    { label: '状态', value: payload.ok === false ? '错误' : '就绪' },
  ];
}
