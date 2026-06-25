import {
  readinessNextActionLabel,
  readinessProductionGapLabel,
  readinessReasonLabel,
} from '@/helpers/readinessLabels';

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
