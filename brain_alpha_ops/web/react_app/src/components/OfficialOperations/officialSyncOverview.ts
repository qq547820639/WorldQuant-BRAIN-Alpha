/** OfficialOperations sync data overview and operation progress derivation. */

import { classifyJobState } from '@/helpers/runPayload';
import type {
  CloudAlphaCache,
  JobStatus,
  ProgressLifecycle,
  SubmitReadinessResponse,
  UnifiedProgress,
} from '@/types';
import {
  booleanField,
  checkResultCount,
  firstPositiveNumber,
  formatClock,
  formatCount,
  formatDuration,
  numberField,
  operationFailureMessage,
  resultNumberField,
  stringField,
} from './officialOperationsCore';
import type { OperationMode, OverviewTone } from './officialOperationsCore';
import {
  boundedProgressPercent,
  cloudAlphaCacheReady,
  cloudAlphaCacheUpdatedAt,
  contextCacheComplete,
  isSuccessfulSyncStatus,
  isTerminalSyncStatus,
  normalizedProgressPercent,
  operationStatusMessage,
  phaseLabel,
  scanEtaDetail,
  syncContextStatus,
  syncStatusUpdatedAt,
  syncScanPageSummary,
  syncStageMetric,
} from './officialSyncProgress';

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

function userErrorField(source: Record<string, unknown> | undefined) {
  const value = source?.user_error;
  return value && typeof value === 'object' ? (value as UnifiedProgress['user_error']) : undefined;
}

export function operationProgress(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  readiness: SubmitReadinessResponse | null,
  checks: { count?: number; items?: unknown; checks?: unknown } | null
): UnifiedProgress {
  if (mode === 'context_refresh') {
    const stage = syncStageMetric(syncStatus);
    const terminal = isTerminalSyncStatus(syncStatus);
    const successful = isSuccessfulSyncStatus(syncStatus);
    const terminalFailure = terminal && !successful;
    const scanStillRunning = stage.kind === 'scan' && !terminal;
    const hasStageTotal = stage.total > 0;
    const syncProgress = syncStatus?.progress;
    const stagePercent = terminalFailure
      ? null
      : stage.total > 0
        ? boundedProgressPercent((stage.current / stage.total) * 100, terminal)
        : terminal
          ? normalizedProgressPercent(syncStatus)
          : null;
    return {
      operation: scanStillRunning ? 'sync_alphas' : undefined,
      status_code: scanStillRunning ? 'SCAN' : stringField(syncProgress, 'status_code'),
      status: syncStatus?.status,
      status_kind: syncStatus?.status_kind || stringField(syncProgress, 'status_kind'),
      terminal: syncStatus?.terminal ?? booleanField(syncProgress, 'terminal'),
      active: syncStatus?.active ?? booleanField(syncProgress, 'active'),
      interrupted: syncStatus?.interrupted ?? booleanField(syncProgress, 'interrupted'),
      recoverable: syncStatus?.recoverable ?? booleanField(syncProgress, 'recoverable'),
      retryable: syncStatus?.retryable ?? booleanField(syncProgress, 'retryable'),
      error: syncStatus?.error || stringField(syncProgress, 'error'),
      error_code: stringField(syncProgress, 'error_code'),
      user_error: syncStatus?.user_error || userErrorField(syncProgress),
      user_error_kind: syncStatus?.user_error_kind || stringField(syncProgress, 'user_error_kind'),
      user_message: syncStatus?.user_message || stringField(syncProgress, 'user_message'),
      next_action: syncStatus?.next_action || stringField(syncProgress, 'next_action'),
      phase: scanStillRunning
        ? 'scan'
        : syncStatus?.phase || syncStatus?.progress?.phase || 'context_refresh',
      phase_label: phaseLabel(syncStatus),
      status_message: operationStatusMessage(syncStatus),
      percent_complete: scanStillRunning ? null : stagePercent,
      eta_seconds: terminalFailure ? null : stage.etaSeconds || null,
      eta_deadline_at_ms:
        stage.kind === 'scan' || terminalFailure || !hasStageTotal
          ? null
          : firstPositiveNumber(
              numberField(syncStatus?.progress, 'eta_deadline_at_ms'),
              resultNumberField(syncStatus, 'eta_deadline_at_ms')
            ) || null,
      done: stage.kind === 'scan' ? undefined : stage.current || undefined,
      scanned: stage.kind === 'scan' && !terminalFailure ? stage.current : undefined,
      total: stage.kind === 'scan' || terminalFailure || stage.total <= 0 ? undefined : stage.total,
      api_reported_total: numberField(syncStatus?.progress, 'api_reported_total') || undefined,
      remaining_items: numberField(syncStatus?.progress, 'remaining_items') || undefined,
      has_more:
        typeof syncStatus?.progress?.has_more === 'boolean'
          ? syncStatus.progress.has_more
          : undefined,
      pagination_complete:
        typeof syncStatus?.progress?.pagination_complete === 'boolean'
          ? syncStatus.progress.pagination_complete
          : undefined,
      pagination_target:
        typeof syncStatus?.progress?.pagination_target === 'string'
          ? syncStatus.progress.pagination_target
          : undefined,
      stop_reason:
        typeof syncStatus?.progress?.stop_reason === 'string'
          ? syncStatus.progress.stop_reason
          : undefined,
      page_number: stage.pageNumber || undefined,
      pages_fetched: stage.pageNumber || undefined,
      expected_pages: stage.expectedPages || undefined,
      page_size: stage.pageSize || undefined,
      page_limit: stage.pageLimit || undefined,
      next_offset: stage.nextOffset || undefined,
      new_unique_items: stage.newUniqueItems || undefined,
      unique_items: stage.uniqueItems || undefined,
      confirming_total_boundary: stage.confirmingTotalBoundary || undefined,
      indeterminate: scanStillRunning || undefined,
      open_ended: scanStillRunning || undefined,
      job_id: syncStatus?.job_id,
      task_id: syncStatus?.task_id,
    };
  }
  if (mode === 'readiness') {
    return {
      phase: 'submit_readiness',
      phase_label: '阻断复核',
      status_message: readiness
        ? `阻断复核 ${readiness.eligible_count ?? 0} / 候选 ${readiness.candidate_count ?? 0}`
        : '正在读取提交前阻断复核证据。',
      percent_complete: readiness ? 100 : 35,
      checked: readiness?.candidate_count ?? 0,
      total: readiness?.candidate_count ?? 0,
    };
  }
  if (mode === 'checks') {
    const count = checkResultCount(checks);
    return {
      phase: 'check_results',
      phase_label: '检查结果',
      status_message: checks ? `已加载 ${count} 条检查结果。` : '正在读取检查结果。',
      percent_complete: checks ? 100 : 35,
      checked: count,
      total: count,
    };
  }
  return {
    phase: 'idle',
    phase_label: '等待操作',
    status_message: '选择一个操作后，系统会在这里展示真实进度。',
    percent_complete: 0,
  };
}

export function progressState(
  mode: OperationMode,
  syncRunning: boolean,
  syncStatus: JobStatus | null,
  readinessLoading: boolean,
  checksLoading: boolean,
  error: string | null
): ProgressLifecycle {
  if (error) return 'error';
  if (syncRunning || readinessLoading || checksLoading) return 'progress';
  const syncState = classifyJobState(syncStatus);
  if (
    mode === 'context_refresh' &&
    (syncState.failed || syncState.missing || syncState.interrupted)
  )
    return 'error';
  if (mode !== 'idle') return 'success';
  return 'idle';
}

export function currentModeError(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  errors: {
    syncStart: string | null;
    syncStatus: string | null;
    readiness: string | null;
    checks: string | null;
  }
) {
  if (mode === 'context_refresh') {
    const syncState = classifyJobState(syncStatus);
    const stopped = syncState.interrupted;
    const recoverableMessage = stopped
      ? syncStatus?.progress?.status_message ||
        syncStatus?.status_message ||
        '官方上下文刷新已停止，可重新刷新。'
      : '';
    if (syncStatus && (syncState.failed || syncState.missing || syncState.interrupted)) {
      return (
        operationFailureMessage(syncStatus, '') ||
        operationFailureMessage(errors.syncStart || errors.syncStatus || recoverableMessage, '')
      );
    }
    return operationFailureMessage(
      syncStatus?.error || errors.syncStart || errors.syncStatus || recoverableMessage,
      ''
    );
  }
  if (mode === 'readiness') return operationFailureMessage(errors.readiness, '');
  if (mode === 'checks') return operationFailureMessage(errors.checks, '');
  return null;
}
