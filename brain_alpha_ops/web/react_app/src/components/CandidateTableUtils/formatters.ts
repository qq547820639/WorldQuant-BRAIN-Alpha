import type { Candidate, SSEEvent } from '@/types';
import { RAW_UNSAFE_DISPLAY_TEXT_PATTERN } from '@/helpers/errorExperience';
import type { CandidateCheckResult, SimulationResultSummary, CandidateQueueView } from './types';
import { candidateText, record, numericResultField } from './base';
import {
  candidateSubmissionReady,
  candidateHasLocalBlockingQuality,
  candidateNeedsOptimization,
  candidateLocalValid,
  candidateRetainedPoolEligible,
  checkResultForCandidate,
} from './quality';

export function safeCandidateDisplayText(value: unknown, fallback: string) {
  const text = candidateText(value).trim();
  if (!text) return fallback;
  return RAW_UNSAFE_DISPLAY_TEXT_PATTERN.test(text) ? fallback : text;
}

export function candidateQualityBadge(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (candidateSubmissionReady(candidate)) {
    return { label: '达标', tone: 'badge-positive', title: '符合提交前质量复核条件' };
  }
  if (candidateHasLocalBlockingQuality(candidate)) {
    return { label: '阻断', tone: 'badge-negative', title: candidateBlockerText(candidate) };
  }
  if (diagnosis.qualified) {
    return { label: '待确认', tone: 'badge-warning', title: '质量达标，但仍有提交前阻断需要处理' };
  }
  if (candidateNeedsOptimization(candidate)) {
    return { label: '需优化', tone: 'badge-warning', title: candidateBlockerText(candidate) };
  }
  if (candidateLocalValid(candidate) || candidateRetainedPoolEligible(candidate)) {
    return { label: '可推进', tone: 'badge-warning', title: '本地候选可继续补证据或挑战主池排序' };
  }
  return { label: '未验证', tone: 'badge-neutral', title: '缺少质量诊断' };
}

export function candidateBlockerText(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  const primary = record(diagnosis.primary_reason);
  const primaryText = candidateText(primary.message || primary.code || primary.category);
  if (primaryText) return primaryText;
  const decisionEvidence = candidateDecisionEvidenceText(candidate);
  if (decisionEvidence) return decisionEvidence;
  if ((diagnosis.blocking_reasons || []).length)
    return (diagnosis.blocking_reasons || []).join('; ');
  if ((candidate.local_quality?.reasons || []).length)
    return candidate.local_quality?.reasons?.join('; ') || '';
  if ((candidate.gate?.failed_reasons || []).length)
    return candidate.gate?.failed_reasons?.join('; ') || '';
  if (candidate.local_quality?.passed === false) return 'local_quality_failed';
  if (!candidate.quality_diagnosis) return 'missing_quality_diagnosis';
  return '-';
}

export function candidateDecisionEvidenceText(candidate: Candidate) {
  const evidence = candidate.production_decision?.decision_evidence;
  const lifecycleRisk = evidence?.lifecycle_risk;
  if (lifecycleRisk?.reason_code) {
    const status = candidateText(
      lifecycleRisk.latest_status || lifecycleRisk.latest_status_category
    ).trim();
    const action = candidateText(lifecycleRisk.action_hint) === 'archive' ? '归档' : '返工优化';
    return `历史证据: ${status || lifecycleRisk.reason_code}，需先${action}`;
  }
  const auditReasons =
    evidence?.scientific_audit_policy_reasons || evidence?.hard_blocking_reasons || [];
  if (auditReasons.length) {
    return `科学审计阻断: ${auditReasons.join('; ')}`;
  }
  if (candidate.production_decision?.reason && candidate.production_decision.action === 'archive') {
    return candidate.production_decision.reason;
  }
  return '';
}

export function candidateOutputSummary(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  if (config.local_only === true) return '本地输出';
  if (config.official_api_called === true) return '官方证据';
  if (config.allow_submit === false) return '禁止提交';
  return config.alpha_type || candidate.decision_band || '-';
}

export function candidateOutputDetail(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  const settings = record(config.settings);
  const dataset = config.dataset_id || candidate.dataset_id || settings.dataset;
  const alphaType = config.alpha_type || settings.type;
  const official = config.official_api_called === true ? 'official_called' : 'official_not_called';
  return [
    dataset ? `dataset:${dataset as string | number | boolean}` : '',
    alphaType ? `type:${alphaType as string | number | boolean}` : '',
    official,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function candidateQualitySearchText(candidate: Candidate) {
  return [
    candidateBlockerText(candidate),
    candidateOutputSummary(candidate),
    candidateOutputDetail(candidate),
    candidate.official_alpha_id,
    candidate.simulation_id,
    candidate.dataset_id,
  ]
    .filter(Boolean)
    .join(' ');
}

export function officialEvidenceText(
  candidate: Candidate,
  checkResults: Map<string, CandidateCheckResult>
) {
  const result = checkResultForCandidate(candidate, checkResults);
  if (result) {
    const status =
      result.status || (result.submittable ? 'submittable' : result.passed ? 'passed' : 'blocked');
    const stale = result.is_stale ? ' · stale' : '';
    return `${candidateText(result.official_alpha_id || candidate.official_alpha_id || 'official:-')} · ${status}${stale}`;
  }
  return candidateText(candidate.official_alpha_id || 'official:-');
}

export function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (
    normalized.includes('submitted') ||
    normalized.includes('completed') ||
    normalized.includes('candidate_pool_retained')
  )
    return 'badge-positive';
  if (
    normalized.includes('failed') ||
    normalized.includes('blocked') ||
    normalized.includes('rejected')
  )
    return 'badge-negative';
  if (
    normalized.includes('validat') ||
    normalized.includes('simulat') ||
    normalized.includes('running')
  )
    return 'badge-warning';
  return 'badge-neutral';
}

export function simulationResultSummary(event: SSEEvent): SimulationResultSummary {
  const result = record(event.result);
  const progress = record(event.progress);
  const data = record(progress.data);
  return {
    completed: numericResultField(result.completed ?? data.completed),
    failed: numericResultField(result.failed ?? data.failed),
    total: numericResultField(result.total ?? data.total),
  };
}

export function simulationCompletionMessage(result: SimulationResultSummary) {
  const total = result.total > 0 ? `，共 ${result.total} 个` : '';
  return `BRAIN模拟完成: ${result.completed} 成功, ${result.failed} 失败${total}`;
}

export function queueViewLabel(viewMode: CandidateQueueView) {
  const labels: Record<CandidateQueueView, string> = {
    candidates: '全部候选',
    pending_backtest: '等待回测',
    running_backtest: '回测中',
    backtest_rework: '需返工',
    passed: '已达标',
    submittable: '复核预检',
    submitted: '已提交',
    failed: '失败/阻断',
  };
  return labels[viewMode];
}
