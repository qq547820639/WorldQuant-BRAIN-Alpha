import { readinessProductionGapLabel, readinessReasonLabel } from '@/helpers/readinessLabels';
import { BLOCKER_ACTION_MAP } from './constants';

export function blockerActionForReason(reason: string) {
  return (
    BLOCKER_ACTION_MAP[reason] || {
      label: '查看阻断详情',
      description: readinessReasonLabel(reason),
      view: 'quality_check',
      action_type: 'navigate',
    }
  );
}

export function blockerActionForProductionGap(finding: { code?: unknown; message?: unknown }) {
  const code = String(finding.code || finding.message || '').trim();
  if (code && BLOCKER_ACTION_MAP[code]) {
    return BLOCKER_ACTION_MAP[code];
  }
  return {
    label: '修复生产缺口',
    description: readinessProductionGapLabel(finding),
    view: 'candidates',
    action_type: 'navigate' as const,
  };
}

export function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return '0';
  return String(Math.max(0, Math.trunc(number)));
}
