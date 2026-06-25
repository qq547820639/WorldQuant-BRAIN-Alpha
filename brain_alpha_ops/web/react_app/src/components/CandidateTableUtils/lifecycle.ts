import type { Candidate, AlphaLifecycleTrace } from '@/types';
import { candidateText, candidateIds } from './base';

export function lifecycleTracesForCandidates(
  traces: AlphaLifecycleTrace[],
  candidates: Candidate[],
  filter: string
) {
  const candidateIdSet = new Set<string>();
  for (const candidate of candidates) {
    candidateIds(candidate).forEach((id) => candidateIdSet.add(id));
  }
  const normalizedFilter = filter.trim().toLowerCase();
  return traces.filter((trace) => {
    const identities = lifecycleTraceIds(trace);
    const matchesCandidate =
      candidateIdSet.size === 0 || identities.some((id) => candidateIdSet.has(id));
    if (!matchesCandidate) return false;
    if (!normalizedFilter) return true;
    return lifecycleTraceSearchText(trace).includes(normalizedFilter);
  });
}

export function lifecycleTraceIds(trace: AlphaLifecycleTrace) {
  return [trace.alpha_id, trace.official_alpha_id, trace.simulation_id, trace.trace_key]
    .map((value) => candidateText(value).trim())
    .filter(Boolean);
}

export function lifecycleTraceSearchText(trace: AlphaLifecycleTrace) {
  return [
    ...lifecycleTraceIds(trace),
    trace.latest_stage,
    trace.latest_status,
    trace.status_category,
    trace.last_note,
    trace.next_action,
    trace.expression_digest,
    ...(trace.stages || []),
  ]
    .map((value) => candidateText(value).toLowerCase())
    .join(' ');
}

export function lifecycleStatusBadgeClass(trace: AlphaLifecycleTrace) {
  const category = candidateText(trace.status_category).toLowerCase();
  if (category === 'blocked') return 'badge-negative';
  if (category === 'failed') return 'badge-negative';
  if (category === 'submitted') return 'badge-positive';
  if (category === 'passed') return 'badge-positive';
  if (trace.submitted) return 'badge-positive';
  if (trace.passed) return 'badge-positive';
  if (trace.blocked || trace.failed) return 'badge-negative';
  return 'badge-neutral';
}

export function lifecycleStatusLabel(trace: AlphaLifecycleTrace) {
  const category = candidateText(trace.status_category).toLowerCase();
  if (category === 'blocked') return '阻断';
  if (category === 'failed') return '失败';
  if (category === 'submitted') return '已提交';
  if (category === 'passed') return '通过';
  if (trace.submitted) return '已提交';
  if (trace.passed) return '通过';
  if (trace.blocked) return '阻断';
  if (trace.failed) return '失败';
  return category || '记录';
}

export function lifecycleNextActionLabel(action: unknown) {
  const normalized = candidateText(action);
  const labels: Record<string, string> = {
    collect_official_identity: '补官方ID',
    continue_validation: '继续验证',
    monitor_official_result: '监控结果',
    optimize_or_archive: '优化/归档',
    review_blockers: '复核阻断',
  };
  return labels[normalized] || normalized || '继续审查';
}

export function safeLifecycleNote(value: unknown) {
  const text = candidateText(value).trim();
  if (!text) return '';
  return text
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[redacted]')
    .replace(
      /\b(username|account|email|password|passwd|pwd|token|auth_token|access_token|csrf_token|stream_token|session_id|cookie)\b\s*[:=]\s*[^,\s;]+/gi,
      '[redacted]'
    )
    .replace(/\b(csrf-secret|session-secret|auth-secret|access-secret)\b/gi, '[redacted]')
    .replace(
      /\b(password|passwd|pwd|auth[_ -]?token|access[_ -]?token|csrf[_ -]?token|stream[_ -]?token|session[_ -]?id|cookie|secret)\b/gi,
      '[redacted]'
    )
    .slice(0, 180);
}

export function lifecycleTraceTitle(trace: AlphaLifecycleTrace) {
  return lifecycleTraceIds(trace).join(' / ') || trace.expression_digest || '';
}

export function shortLifecycleTraceId(trace: AlphaLifecycleTrace) {
  const raw = lifecycleTraceIds(trace)[0] || trace.expression_digest || 'unknown';
  return raw.length > 24 ? `${raw.slice(0, 24)}...` : raw;
}
