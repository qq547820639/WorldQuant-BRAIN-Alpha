import type { BacktestSlotsResponse, Candidate, CardViewId } from '@/types';
import { backtestActiveCount, backtestSlotLimit } from '@/utils/backtestSlots';
import { cloudTotal, isSubmissionReadyCandidate } from './helpers';

export interface CheckpointStatusSummary {
  checkpoint_count?: number;
  history_count?: number;
  resume_available?: boolean;
}

export interface CandidatesSnapshot {
  candidates?: Candidate[];
  items?: Candidate[];
  ready_count?: number;
  total?: number;
  returned_count?: number;
  total_count?: number;
}

export interface ConfigSnapshot {
  config?: { environment?: string; credentials?: { managed_credentials_available?: boolean } };
}

export interface CloudSnapshot {
  count?: number;
  total?: number;
  summary?: Record<string, unknown>;
}

export interface StateCardsMetrics {
  candidates: { total: number; label: string };
  official_backtests: string;
  quality_check: { ready: number; label: string };
  submission_confirm: { eligible: string; caption: string; label: string };
  checkpoint_status: { history: number; label: string };
  config: { environment: string; label: string };
  cloud: { total: string; label: string };
}

interface BuildParams {
  candidatesData: CandidatesSnapshot | null;
  slotsData: BacktestSlotsResponse | null;
  configData: ConfigSnapshot | null;
  cloudData: CloudSnapshot | null;
  checkpointData: CheckpointStatusSummary | null;
}

export function buildStateCardsMetrics({
  candidatesData,
  slotsData,
  configData,
  cloudData,
  checkpointData,
}: BuildParams): StateCardsMetrics {
  const candidates = candidatesData?.candidates || candidatesData?.items || [];
  const slotLimit = backtestSlotLimit(slotsData);
  const activeSlots = backtestActiveCount(slotsData);
  const qualityCount =
    candidatesData?.ready_count ?? candidates.filter(isSubmissionReadyCandidate).length;
  const cloudCount = cloudTotal(cloudData);

  return {
    candidates: {
      total: candidatesData?.total ?? candidates.length,
      label: '候选总数',
    },
    official_backtests: `${activeSlots}/${slotLimit}`,
    quality_check: {
      ready: qualityCount,
      label: '达标数量',
    },
    submission_confirm: {
      eligible: '打开',
      caption: '提交审计',
      label: '提交审计',
    },
    checkpoint_status: {
      history: checkpointData?.history_count ?? 0,
      label: '历史记录',
    },
    config: {
      environment: configData?.config?.environment || '-',
      label: '运行环境',
    },
    cloud: {
      total: cloudCount,
      label: '云端缓存',
    },
  };
}

export function getMetricValue(metrics: StateCardsMetrics, id: CardViewId): string {
  switch (id) {
    case 'official_operations':
      return 'Web';
    case 'candidates':
      return String(metrics.candidates.total);
    case 'dashboard':
      return '本地';
    case 'official_backtests':
      return metrics.official_backtests;
    case 'scoring':
      return String(metrics.quality_check.ready);
    case 'quality_check':
      return String(metrics.quality_check.ready);
    case 'submission_confirm':
      return String(metrics.submission_confirm.eligible);
    case 'checkpoint_status':
      return String(metrics.checkpoint_status.history);
    case 'config':
      return metrics.config.environment;
    case 'cloud':
      return metrics.cloud.total;
    default:
      return '-';
  }
}

export function getMetricLabel(metrics: StateCardsMetrics, id: CardViewId): string {
  switch (id) {
    case 'official_operations':
      return '用户入口';
    case 'candidates':
      return metrics.candidates.label;
    case 'dashboard':
      return '本地服务';
    case 'official_backtests':
      return '回测槽位';
    case 'scoring':
      return '可评分候选';
    case 'quality_check':
      return metrics.quality_check.label;
    case 'submission_confirm':
      return metrics.submission_confirm.label;
    case 'checkpoint_status':
      return metrics.checkpoint_status.label;
    case 'config':
      return metrics.config.label;
    case 'cloud':
      return metrics.cloud.label;
    default:
      return '';
  }
}
