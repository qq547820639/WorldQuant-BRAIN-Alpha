import type { Candidate } from '@/types';
import { safeDisplayErrorMessage } from '@/helpers/errorExperience';

export function isSubmissionReadyCandidate(candidate: Candidate) {
  const status = String(candidate.lifecycle_status || '').toLowerCase();
  return (
    status === 'submission_ready' ||
    candidate.quality_diagnosis?.submission_ready === true ||
    (candidate.gate as { submission_ready?: unknown } | undefined)?.submission_ready === true
  );
}

export function cloudTotal(
  payload: { count?: number; total?: number; summary?: Record<string, unknown> } | null
) {
  const summary = payload?.summary || {};
  const value =
    payload?.count ?? payload?.total ?? summary.count ?? summary.total ?? summary.total_count;
  if (value == null) return '-';
  const primitive = value as string | number | boolean;
  return String(primitive);
}

export function labeledError(label: string, error: string | null) {
  if (!error) return '';
  return `${label}: ${userFacingError(error)}`;
}

export function userFacingError(error: string) {
  return safeDisplayErrorMessage(error, '状态读取失败，请重试或检查服务状态。');
}
