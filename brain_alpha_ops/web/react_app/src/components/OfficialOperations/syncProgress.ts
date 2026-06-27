import { apiErrorMessage } from '@/helpers/errorExperience';
import { classifyJobState, jobStatusMessage } from '@/helpers/runPayload';
import type { JobStatus, OfficialContextCache } from '@/types';
import { firstPositiveNumber, formatCount, numberField, resultNumberField } from './formatters';
import { readableBackendText } from './errorMessages';
import { syncScanPageSummary, syncStageCode } from './syncStage';

export function syncProgressMonitorSignature(result: JobStatus): string {
  const progress = result?.progress || {};
  return [
    progress.phase || '',
    progress.status_code || '',
    progress.percent_complete ?? '',
    progress.scanned ?? '',
    progress.added ?? '',
    progress.skipped ?? '',
    progress.failed ?? '',
  ].join('|');
}

export function isTerminalSyncStatus(result: JobStatus | null): boolean {
  if (!result) return false;
  const status = String(result?.status || '').toLowerCase();
  return ['completed', 'failed', 'stopped', 'error'].includes(status);
}

export function isSuccessfulSyncStatus(status: JobStatus | null) {
  return classifyJobState(status).successful;
}

export function isRunningScanStatus(status: JobStatus | null) {
  return !isTerminalSyncStatus(status) && syncStageCode(status) === 'SCAN';
}

export function runningScanStatusMessage(status: JobStatus | null) {
  if (!isRunningScanStatus(status)) return '';
  const scanned = numberField(status?.progress, 'scanned');
  const apiTotal = firstPositiveNumber(
    numberField(status?.progress, 'api_reported_total'),
    numberField(status?.progress, 'filter_window_count')
  );
  if (scanned <= 0)
    return '正在扫描云端 Alpha，等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。';
  if (apiTotal > 0) {
    return `已拉取 ${formatCount(scanned)} 条云端 Alpha；接口分页参考数 ${formatCount(apiTotal)} 条，不是云端 Alpha 总量，会继续按分页自动确认边界；${syncScanPageSummary(status)}`;
  }
  return `已拉取 ${formatCount(scanned)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

export function normalizedProgressPercent(status: JobStatus | null) {
  const terminal = isTerminalSyncStatus(status);
  const raw =
    status?.progress?.percent_complete ?? status?.progress?.percent ?? status?.percent_complete;
  const value = Number(raw);
  if (Number.isFinite(value)) return boundedProgressPercent(value, terminal);
  const scanned = numberField(status?.progress, 'scanned');
  const total = numberField(status?.progress, 'total');
  if (total > 0) return boundedProgressPercent((scanned / total) * 100, terminal);
  if (terminal) return 100;
  if (status?.status === 'running') return 35;
  return 0;
}

export function boundedProgressPercent(value: number, terminal: boolean) {
  const upperBound = terminal ? 100 : 99;
  return Math.max(0, Math.min(upperBound, value));
}

export function syncStatusUpdatedAt(status: JobStatus | null) {
  const progressUpdated = numberField(status?.progress, 'updated_at_ms');
  if (progressUpdated > 0) return new Date(progressUpdated);
  const resultUpdated = resultNumberField(status, 'updated_at_ms');
  if (resultUpdated > 0) return new Date(resultUpdated);
  const startedAt = Date.parse(String(status?.started_at || ''));
  if (Number.isFinite(startedAt)) return new Date(startedAt);
  return status ? new Date() : null;
}

export function syncContextStatus(status: JobStatus | null): string {
  if (!status) return '待启动';
  const cache = status?.official_context_cache;
  if (cache?.complete) return '已缓存';
  if (cache?.in_progress) return '同步中';
  return '待刷新';
}

export function contextCacheComplete(cache?: Record<string, unknown>): boolean {
  return Boolean(cache?.complete);
}

export function syncStatusForDisplay(
  status: JobStatus | null,
  officialContextCache?: OfficialContextCache
): JobStatus | null {
  const cache = status?.official_context_cache || officialContextCache;
  if (status) {
    return cache && status.official_context_cache !== cache
      ? { ...status, official_context_cache: cache }
      : status;
  }
  if (!cache) return null;
  return {
    job_id: '',
    task_id: '',
    status: 'idle',
    phase: 'local_cache',
    progress: {
      phase: 'local_cache',
      status_code: contextCacheComplete(cache) ? 'LOCAL_CACHE' : 'LOCAL_CACHE_INVALID',
      status_message: contextCacheComplete(cache)
        ? '本地官方上下文缓存已加载。'
        : '本地官方上下文缓存完整性未通过，需要手动刷新。',
    },
    official_context_cache: cache,
  };
}

export function operationStatusMessage(status: JobStatus | null) {
  if (!status) return '尚未启动。';
  const scanMessage = runningScanStatusMessage(status);
  if (scanMessage) return scanMessage;
  const state = classifyJobState(status);
  const apiMessage = apiErrorMessage(status, '');
  if (apiMessage) return readableBackendText(apiMessage) || apiMessage;
  if (state.interrupted) return '官方上下文刷新已停止，结果未确认完成。';
  if (state.failed || state.missing) return '官方上下文刷新失败，请稍后重试或重新启动流程。';
  const sharedMessage = jobStatusMessage(status, '');
  const readableSharedMessage = readableBackendText(sharedMessage);
  if (readableSharedMessage) return readableSharedMessage;
  const message =
    status.progress?.status_message ||
    status.status_message ||
    status.error ||
    `当前状态: ${status.status || '未知'}`;
  const readableMessage = readableBackendText(message);
  if (readableMessage) return readableMessage;
  if (state.active || status.status === 'running')
    return '官方上下文刷新正在运行，等待下一次状态更新。';
  return '官方上下文状态暂不明确，请刷新状态或重新启动流程。';
}
