/** OfficialOperations sync stage metrics, progress monitoring, and context cache helpers. */

import { apiErrorMessage } from '@/helpers/errorExperience';
import { classifyJobState, jobStatusMessage } from '@/helpers/runPayload';
import type { CloudAlphaCache, JobStatus, OfficialContextCache } from '@/types';
import { isRecord } from '@/types';
import {
  firstPositiveFloat,
  firstPositiveNumber,
  formatCount,
  numberField,
  resultNumberField,
  resultStringField,
  readableBackendText,
} from './officialOperationsCore';
import type { SyncStageKind, SyncStageMetric } from './officialOperationsCore';

export function syncStageCode(status: JobStatus | null) {
  return String(
    (status?.progress?.status_code as string | number | boolean | null | undefined) ||
      status?.phase ||
      status?.progress?.phase ||
      'context_refresh'
  ).toUpperCase();
}

export function phaseLabel(status: JobStatus | null) {
  const code = String(
    (status?.progress?.status_code as string | number | boolean | null | undefined) ||
      status?.phase ||
      status?.progress?.phase ||
      'context_refresh'
  );
  const normalizedCode = code.toUpperCase();
  const labels: Record<string, string> = {
    AUTH: '认证',
    SCAN: '扫描云端',
    MERGE: '合并快照',
    CONTEXT_FIELDS: '刷新字段',
    CONTEXT_OPERATORS: '刷新算子',
    CONTEXT_DATASETS: '刷新数据集',
    CONTEXT_FAILED: '上下文失败',
    CONTEXT_REFRESH: '刷新上下文',
    REFRESH_CONTEXT: '刷新上下文',
    LOCAL_CACHE: '本地缓存',
    LOCAL_CACHE_INVALID: '缓存需刷新',
    SESSION_INVALID: '需要重新连接',
    COMPLETED: '完成',
    COMPLETED_WITH_WARNINGS: '带警告完成',
    QUEUED: '已排队',
    RUNNING: '运行中',
    STOPPED: '已停止',
    FAILED: '失败',
  };
  return labels[normalizedCode] || '当前阶段';
}

export function syncStageMetric(status: JobStatus | null): SyncStageMetric {
  const progress = status?.progress;
  const code = syncStageCode(status);
  const elapsedSeconds = firstPositiveNumber(
    numberField(progress, 'elapsed_seconds'),
    resultNumberField(status, 'elapsed_seconds')
  );
  if (code === 'SCAN') {
    return buildSyncStageMetric({
      kind: 'scan',
      label: '云端 Alpha 扫描',
      rateLabel: '扫描速率',
      unit: '条云端 Alpha',
      rateUnit: '条/秒',
      current: firstPositiveNumber(
        numberField(progress, 'scanned'),
        resultNumberField(status, 'scanned')
      ),
      total: firstPositiveNumber(
        numberField(progress, 'api_reported_total'),
        numberField(progress, 'filter_window_count'),
        resultNumberField(status, 'api_reported_total'),
        resultNumberField(status, 'filter_window_count')
      ),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === 'CONTEXT_FIELDS') {
    return buildSyncStageMetric({
      kind: 'fields',
      label: '官方字段缓存',
      rateLabel: '字段刷新速率',
      unit: '个官方字段',
      rateUnit: '个/秒',
      current: firstPositiveNumber(
        numberField(progress, 'fields_count'),
        resultNumberField(status, 'fields_count')
      ),
      total: firstPositiveNumber(
        numberField(progress, 'fields_total'),
        resultNumberField(status, 'fields_total')
      ),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === 'CONTEXT_OPERATORS') {
    return buildSyncStageMetric({
      kind: 'operators',
      label: '官方算子缓存',
      rateLabel: '算子刷新速率',
      unit: '个官方算子',
      rateUnit: '个/秒',
      current: firstPositiveNumber(
        numberField(progress, 'operators_count'),
        resultNumberField(status, 'operators_count')
      ),
      total: firstPositiveNumber(
        numberField(progress, 'operators_total'),
        resultNumberField(status, 'operators_total')
      ),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === 'CONTEXT_DATASETS') {
    return buildSyncStageMetric({
      kind: 'datasets',
      label: '官方数据集缓存',
      rateLabel: '数据集刷新速率',
      unit: '个官方数据集',
      rateUnit: '个/秒',
      current: firstPositiveNumber(
        numberField(progress, 'datasets_count'),
        resultNumberField(status, 'datasets_count')
      ),
      total: firstPositiveNumber(
        numberField(progress, 'datasets_total'),
        resultNumberField(status, 'datasets_total')
      ),
      elapsedSeconds,
      progress,
      status,
    });
  }
  return buildSyncStageMetric({
    kind: 'other',
    label: '当前阶段',
    rateLabel: '处理速率',
    unit: '项',
    rateUnit: '项/秒',
    current: 0,
    total: 0,
    elapsedSeconds,
    progress,
    status,
  });
}

function buildSyncStageMetric({
  kind,
  label,
  rateLabel,
  unit,
  rateUnit,
  current,
  total,
  elapsedSeconds,
  progress,
  status,
}: {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  progress?: Record<string, unknown>;
  status: JobStatus | null;
}): SyncStageMetric {
  const etaSeconds =
    kind !== 'scan' && current > 0 && total > current
      ? firstPositiveNumber(
          numberField(progress, 'eta_seconds'),
          resultNumberField(status, 'eta_seconds')
        )
      : 0;
  const reportedRate = firstPositiveFloat(
    numberField(progress, 'rate_per_second'),
    resultNumberField(status, 'rate_per_second')
  );
  const derivedRate = current > 0 && elapsedSeconds > 0 ? current / elapsedSeconds : 0;
  return {
    kind,
    label,
    rateLabel,
    unit,
    rateUnit,
    current: Math.max(0, Math.trunc(current || 0)),
    total: Math.max(0, Math.trunc(total || 0)),
    elapsedSeconds,
    etaSeconds,
    ratePerSecond: firstPositiveFloat(reportedRate, derivedRate),
    pageNumber: firstPositiveNumber(
      numberField(progress, 'pages_fetched'),
      numberField(progress, 'page_number')
    ),
    expectedPages: firstPositiveNumber(numberField(progress, 'expected_pages')),
    pageSize: firstPositiveNumber(numberField(progress, 'page_size')),
    pageLimit: firstPositiveNumber(numberField(progress, 'page_limit')),
    nextOffset: firstPositiveNumber(numberField(progress, 'next_offset')),
    newUniqueItems: firstPositiveNumber(numberField(progress, 'new_unique_items')),
    uniqueItems: firstPositiveNumber(numberField(progress, 'unique_items')),
    confirmingTotalBoundary: Boolean(progress?.confirming_total_boundary),
  };
}

export function syncScanPageSummary(status: JobStatus | null) {
  return syncStagePageSummary(syncStageMetric(status));
}

function scanEtaDetail(stage: SyncStageMetric) {
  if (stage.current <= 0) {
    return '正在扫描云端 Alpha；等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。';
  }
  if (stage.total > 0) {
    return `接口分页参考数 ${formatCount(stage.total)} 条；${syncStagePageSummary(stage)}`;
  }
  return `已拉取 ${formatCount(stage.current)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

function syncStagePageSummary(stage: SyncStageMetric) {
  const page =
    stage.pageNumber > 0 ? `当前第 ${formatCount(stage.pageNumber)} 页` : '分页页码确认中';
  const parts = [page];
  if (stage.pageSize > 0) parts.push(`本页 ${formatCount(stage.pageSize)} 条`);
  if (stage.pageLimit > 0) parts.push(`分页参数 ${formatCount(stage.pageLimit)} 条/页`);
  if (stage.nextOffset > 0) parts.push(syncNextOffsetLabel(stage.nextOffset, stage.total));
  if (stage.newUniqueItems > 0) parts.push(`本页新增 ${formatCount(stage.newUniqueItems)} 条`);
  if (stage.uniqueItems > 0) parts.push(`已确认唯一 ${formatCount(stage.uniqueItems)} 条`);
  if (stage.confirmingTotalBoundary) parts.push('本页已满，继续确认下一页');
  return parts.join('；');
}

function syncNextOffsetLabel(nextOffset: number, filterWindowCount: number) {
  if (filterWindowCount > 0 && nextOffset >= filterWindowCount) {
    return '下一请求确认分页边界';
  }
  return '下一轮继续拉取';
}

export { scanEtaDetail, syncStagePageSummary };

export function syncProgressMonitorSignature(result: JobStatus): string {
  const progress = result?.progress || {};
  return [
    progress.phase || '',
    String((progress.status_code as string | number | boolean | null | undefined) || ''),
    progress.percent_complete ?? '',
    progress.scanned ?? '',
    String((progress.added as string | number | boolean | null | undefined) ?? ''),
    String((progress.skipped as string | number | boolean | null | undefined) ?? ''),
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

export function cloudAlphaCacheReady(cache: CloudAlphaCache | undefined) {
  if (!cache?.ok) return false;
  const count = firstPositiveNumber(cache.count, cache.total);
  return count > 0 || (cache.count == null && cache.total == null);
}

export function cloudAlphaCacheUpdatedAt(cache: CloudAlphaCache | undefined) {
  const loadedAt = Date.parse(String(cache?.loaded_at || ''));
  return Number.isFinite(loadedAt) ? new Date(loadedAt) : null;
}

export function contextSummaryNumber(status: JobStatus | null, field: string) {
  return firstPositiveNumber(
    contextCacheNumber(status?.official_context_cache, field),
    numberField(status?.progress, field),
    resultNumberField(status, field)
  );
}

export function contextCacheNumber(cache: OfficialContextCache | undefined, field: string) {
  if (!contextCacheComplete(cache)) return 0;
  return firstPositiveNumber(
    isRecord(cache) ? numberField(cache, field) : 0,
    contextCacheManifestRecordCount(cache, field)
  );
}

function contextCacheManifestRecordCount(cache: OfficialContextCache | undefined, field: string) {
  const filename = {
    fields_count: 'official_fields.json',
    operators_count: 'official_operators.json',
    datasets_count: 'official_datasets.json',
  }[field];
  return filename ? numberField(cache?.manifest?.record_counts, filename) : 0;
}

export function fieldFromProgress(status: JobStatus | null, field: string) {
  const fromProgress = numberField(status?.progress, field);
  if (fromProgress > 0) return String(fromProgress);
  const result = isRecord(status?.result) ? status.result : undefined;
  const fromResult = Number(result?.[field]);
  if (Number.isFinite(fromResult) && fromResult > 0) return String(fromResult);
  const fromCache = contextCacheNumber(status?.official_context_cache, field);
  return fromCache > 0 ? String(fromCache) : '-';
}

export function contextSummaryField(status: JobStatus | null, field: string) {
  const value = contextSummaryNumber(status, field);
  return value > 0 ? String(value) : '-';
}

export function officialContextSummaryMessage(status: JobStatus | null) {
  const cache = status?.official_context_cache;
  const cacheCounts = {
    fields: contextCacheNumber(cache, 'fields_count'),
    operators: contextCacheNumber(cache, 'operators_count'),
    datasets: contextCacheNumber(cache, 'datasets_count'),
  };
  const displayCounts = {
    fields: contextSummaryNumber(status, 'fields_count'),
    operators: contextSummaryNumber(status, 'operators_count'),
    datasets: contextSummaryNumber(status, 'datasets_count'),
  };
  const hasCache = cacheCounts.fields > 0 || cacheCounts.operators > 0 || cacheCounts.datasets > 0;
  const hasDisplayCounts =
    displayCounts.fields > 0 || displayCounts.operators > 0 || displayCounts.datasets > 0;
  const cacheError = typeof cache?.error === 'string' ? cache.error.trim() : '';
  const cacheCompleteVal = contextCacheComplete(cache);
  const statusMessage = status ? operationStatusMessage(status) : '尚未启动官方上下文刷新。';
  if (cacheError && !hasCache) {
    return `${statusMessage} 本地官方上下文缓存摘要读取失败，请点击开始刷新或稍后重试。`;
  }
  if (cache && !cacheCompleteVal && !hasDisplayCounts) {
    const invalid = cache.manifest?.invalid_files?.length
      ? `异常文件: ${cache.manifest.invalid_files.join('、')}`
      : '缓存文件数量或校验和不一致';
    return `${statusMessage} 本地官方上下文缓存完整性未通过，已停止加载展示；请点击开始刷新。${invalid}。`;
  }
  if (!hasCache && !hasDisplayCounts) return statusMessage;
  const stale = Boolean(cache?.manifest?.is_stale);
  const cacheLabel = stale ? '本地缓存存在但需要刷新' : '本地缓存可用';
  const countSourceLabel = cacheCompleteVal ? cacheLabel : '本次刷新结果';
  const counts = cacheCompleteVal ? cacheCounts : displayCounts;
  const cacheText = `${countSourceLabel}: 字段 ${formatCount(counts.fields)}，算子 ${formatCount(counts.operators)}，数据集 ${formatCount(counts.datasets)}`;
  const statusText = String(status?.status || '');
  const state = classifyJobState(status);
  if (state.failed || state.interrupted) {
    return `最近刷新未完成: ${statusMessage}；${cacheText}。`;
  }
  if (!status || statusText === 'idle') return `${statusMessage} ${cacheText}。`;
  return `${statusMessage} ${cacheText}。`;
}

export function officialContextInlineSummary(status: JobStatus | null) {
  const fields = contextSummaryField(status, 'fields_count');
  const operators = contextSummaryField(status, 'operators_count');
  const datasets = contextSummaryField(status, 'datasets_count');
  const contextError = String(
    (status?.progress?.context_error as string | number | boolean | null | undefined) ||
      resultStringField(status, 'context_error') ||
      ''
  ).trim();
  if (fields === '-' && operators === '-' && datasets === '-') {
    return '暂无通过完整性校验的官方上下文缓存统计，等待同步状态返回或手动刷新。';
  }
  if (contextError) {
    return `上下文刷新未完成，可仅重试上下文；当前缓存：字段 ${fields}，算子 ${operators}，数据集 ${datasets}。`;
  }
  if (!status) return '启动后这里会显示字段、算子和数据集缓存的快速摘要。';
  return `快速摘要：字段 ${fields}，算子 ${operators}，数据集 ${datasets}。`;
}

export function canRetryContextOnly(status: JobStatus | null) {
  if (!status) return false;
  const result = isRecord(status.result) ? status.result : undefined;
  const contextStatus = String(
    (status.progress?.['context_status'] as string | number | boolean | null | undefined) ||
      (result?.['context_status'] as string | number | boolean | null | undefined) ||
      ''
  ).toLowerCase();
  const contextError = String(
    (status.progress?.['context_error'] as string | number | boolean | null | undefined) ||
      (result?.['context_error'] as string | number | boolean | null | undefined) ||
      ''
  ).trim();
  return Boolean(contextError || contextStatus === 'failed');
}
