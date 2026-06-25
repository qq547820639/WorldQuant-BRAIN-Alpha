import {
  firstPositiveNumber,
  formatCount,
  numberField,
  resultNumberField,
  resultStringField,
} from './formatters';
import { contextCacheComplete, operationStatusMessage } from './syncProgress';
import { classifyJobState } from '@/helpers/runPayload';
import type { CloudAlphaCache, JobStatus, OfficialContextCache } from '@/types';
import { isRecord } from '@/types';

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
    status?.progress?.context_error || resultStringField(status, 'context_error') || ''
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
    status.progress?.['context_status'] || result?.['context_status'] || ''
  ).toLowerCase();
  const contextError = String(
    status.progress?.['context_error'] || result?.['context_error'] || ''
  ).trim();
  return Boolean(contextError || contextStatus === 'failed');
}
