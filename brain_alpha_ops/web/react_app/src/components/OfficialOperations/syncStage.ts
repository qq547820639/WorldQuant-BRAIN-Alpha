import type { SyncStageKind, SyncStageMetric } from './constants';
import {
  firstPositiveFloat,
  firstPositiveNumber,
  formatCount,
  numberField,
  resultNumberField,
} from './formatters';
import type { JobStatus } from '@/types';

export function syncStageCode(status: JobStatus | null) {
  return String(
    status?.progress?.status_code || status?.phase || status?.progress?.phase || 'context_refresh'
  ).toUpperCase();
}

export function phaseLabel(status: JobStatus | null) {
  const code = String(
    status?.progress?.status_code || status?.phase || status?.progress?.phase || 'context_refresh'
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
