import type { OverviewTone } from './constants';
import {
  firstPositiveNumber,
  formatClock,
  formatCount,
  formatDuration,
  numberField,
  resultNumberField,
} from './formatters';
import {
  contextCacheComplete,
  isSuccessfulSyncStatus,
  isTerminalSyncStatus,
  operationStatusMessage,
  syncContextStatus,
  syncStatusUpdatedAt,
} from './syncProgress';
import { phaseLabel, scanEtaDetail, syncStageMetric, syncScanPageSummary } from './syncStage';
import {
  cloudAlphaCacheReady,
  cloudAlphaCacheUpdatedAt,
} from './contextCache';
import { classifyJobState } from '@/helpers/runPayload';
import type { CloudAlphaCache, JobStatus } from '@/types';

export function syncDataTotal(syncStatus: JobStatus | null, cloudAlphaCache?: CloudAlphaCache) {
  const terminal = isTerminalSyncStatus(syncStatus);
  const successful = isSuccessfulSyncStatus(syncStatus);
  const scanned = firstPositiveNumber(
    numberField(syncStatus?.progress, 'scanned'),
    resultNumberField(syncStatus, 'scanned'),
    resultNumberField(syncStatus, 'count')
  );
  const reportedTotal = firstPositiveNumber(
    numberField(syncStatus?.progress, 'api_reported_total'),
    numberField(syncStatus?.progress, 'filter_window_count'),
    resultNumberField(syncStatus, 'api_reported_total'),
    resultNumberField(syncStatus, 'filter_window_count')
  );
  const completedCount = firstPositiveNumber(
    resultNumberField(syncStatus, 'count'),
    resultNumberField(syncStatus, 'scanned'),
    numberField(syncStatus?.progress, 'scanned')
  );
  if (successful && completedCount > 0) {
    const detail =
      reportedTotal > 0 && reportedTotal !== completedCount
        ? `本次同步实际保存 ${formatCount(completedCount)} 条；接口分页参考数 ${formatCount(reportedTotal)} 条仅用于分页边界判断。`
        : '本次同步实际保存数量；来自本地同步结果。';
    return {
      totalValue: formatCount(completedCount),
      totalDetail: detail,
      totalTone: 'success' as const,
    };
  }
  if (scanned > 0) {
    if (terminal && !successful) {
      return {
        totalValue: `已拉取 ${formatCount(scanned)}`,
        totalDetail: '本次未完成；结果未确认完成，官方分页参考值不作为完成判断。',
        totalTone: 'warning' as const,
      };
    }
    return {
      totalValue: `已拉取 ${formatCount(scanned)}`,
      totalDetail: terminal
        ? reportedTotal > 0
          ? `本次未完成；接口分页参考数 ${formatCount(reportedTotal)} 条仅用于分页边界判断，已拉取 ${formatCount(scanned)} 条。`
          : '本次未完成；接口分页参考数仍在确认。'
        : reportedTotal > 0
          ? `接口分页参考数 ${formatCount(reportedTotal)} 条，不是云端 Alpha 总量；${syncScanPageSummary(syncStatus)}`
          : '接口分页参考数仍在确认；会按官方分页继续读取。',
      totalTone: 'warning' as const,
    };
  }
  if (terminal && !successful) {
    return {
      totalValue: '-',
      totalDetail: '本次未完成；结果未确认完成，官方分页参考值不作为完成判断。',
      totalTone: 'warning' as const,
    };
  }
  if (reportedTotal > 0) {
    return {
      totalValue: `分页参考数 ${formatCount(reportedTotal)}`,
      totalDetail: '接口分页参考数；尚未完成实际同步确认，不是云端 Alpha 总量。',
      totalTone: 'neutral' as const,
    };
  }
  if (cloudAlphaCacheReady(cloudAlphaCache)) {
    const count = firstPositiveNumber(cloudAlphaCache?.count, cloudAlphaCache?.total);
    if (count <= 0) {
      return {
        totalValue: '本地快照可用',
        totalDetail: cloudAlphaCache?.is_stale
          ? '本地云端 Alpha 快照可用但已过期；精确数量请刷新云端快照。'
          : '本地云端 Alpha 快照已确认可用；精确数量由云端快照页加载。',
        totalTone: (cloudAlphaCache?.is_stale ? 'warning' : 'success') as OverviewTone,
      };
    }
    return {
      totalValue: `本地保存 ${formatCount(count)}`,
      totalDetail: cloudAlphaCache?.is_stale
        ? '本地云端 Alpha 快照可用但已过期；需要最新数据时点击开始刷新。'
        : '来自本地云端 Alpha 快照；后续登录默认直接使用该缓存。',
      totalTone: (cloudAlphaCache?.is_stale ? 'warning' : 'success') as OverviewTone,
    };
  }
  return {
    totalValue: '-',
    totalDetail: '等待云端 Alpha 同步；会先读取接口分页参考数，再按分页参数循环拉取。',
    totalTone: 'neutral' as const,
  };
}

export function syncDataOverview(
  syncStatus: JobStatus | null,
  syncRunning: boolean,
  cloudAlphaCache?: CloudAlphaCache
) {
  const localCacheReady =
    !syncRunning &&
    cloudAlphaCacheReady(cloudAlphaCache) &&
    contextCacheComplete(syncStatus?.official_context_cache);
  const statusValue = syncRunning ? '同步中' : syncContextStatus(syncStatus);
  const stage = syncStageMetric(syncStatus);
  const statusDetail = localCacheReady
    ? '本地云端 Alpha 快照与官方能力集缓存已通过完整性校验；需要最新数据时可手动刷新。'
    : syncStatus
      ? `${phaseLabel(syncStatus)}: ${operationStatusMessage(syncStatus)}`
      : '等待启动云端 Alpha 同步。';
  let statusTone: OverviewTone = 'neutral';
  if (syncRunning) statusTone = 'warning';
  else if (localCacheReady) statusTone = 'success';
  else if (isSuccessfulSyncStatus(syncStatus)) statusTone = 'success';
  else if (classifyJobState(syncStatus).failed || classifyJobState(syncStatus).missing)
    statusTone = 'warning';
  const updatedAt = syncStatusUpdatedAt(syncStatus) || cloudAlphaCacheUpdatedAt(cloudAlphaCache);
  const total = syncDataTotal(syncStatus, cloudAlphaCache);

  const hasLiveMetrics = syncRunning && (stage.current > 0 || stage.elapsedSeconds > 0);
  const scanIndeterminate = syncRunning && stage.kind === 'scan';
  const scanHasTotal = stage.kind === 'scan' && stage.total > 0;
  const etaValue = scanIndeterminate
    ? scanHasTotal
      ? '分页继续确认'
      : '等待分页参考数'
    : stage.etaSeconds > 0
      ? formatDuration(stage.etaSeconds)
      : stage.elapsedSeconds > 0
        ? '计算中...'
        : '-';
  const etaDetail = scanIndeterminate
    ? scanEtaDetail(stage)
    : stage.etaSeconds > 0
      ? stage.total > 0
        ? `预计 ${formatDuration(stage.etaSeconds)} 后完成${stage.label}（${formatCount(stage.current)} / ${formatCount(stage.total)} ${stage.unit}）。`
        : `预计 ${formatDuration(stage.etaSeconds)} 后完成${stage.label}。`
      : stage.elapsedSeconds > 0
        ? `已用时 ${formatDuration(stage.elapsedSeconds)}，正在刷新${stage.label}，剩余时间计算中。`
        : `等待${stage.label}进度更新。`;
  const rateValue =
    stage.ratePerSecond > 0 ? `${stage.ratePerSecond.toFixed(1)} ${stage.rateUnit}` : '-';
  const rateDetail =
    stage.current > 0 && stage.elapsedSeconds > 0
      ? `${stage.label}已处理 ${formatCount(stage.current)} ${stage.unit}，历时 ${formatDuration(stage.elapsedSeconds)}。`
      : `${stage.rateLabel}来自当前阶段的官方 API 进度反馈。`;

  return {
    statusValue,
    statusDetail,
    statusTone,
    updatedAtValue: updatedAt ? formatClock(updatedAt) : '-',
    updatedAtDetail: updatedAt
      ? localCacheReady
        ? '来自本地云端 Alpha 快照。'
        : '来自本次同步进度。'
      : '暂无同步更新时间。',
    ...total,
    hasLiveMetrics,
    etaLabel: stage.kind === 'scan' ? '分页进度' : '阶段估算',
    etaValue,
    etaDetail,
    rateLabel: stage.rateLabel,
    rateValue,
    rateDetail,
  };
}
