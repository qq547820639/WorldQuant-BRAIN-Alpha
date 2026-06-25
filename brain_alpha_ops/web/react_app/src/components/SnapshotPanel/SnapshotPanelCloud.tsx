import {
  text,
  record,
  metricText,
  compactJoin,
  rowId,
  type SnapshotPayload,
  type SnapshotRow,
} from './utils';

export function cloudRows(payload: SnapshotPayload): SnapshotRow[] {
  return ((payload.alphas as unknown[]) || []).map((item, index) => {
    const row = record(item);
    const metrics = record(row.metrics);
    const regular = record(row.regular);
    return {
      id: rowId(row, `cloud_${index}`),
      kind: 'cloud',
      title: text(row.alpha_id || row.id || `cloud_${index + 1}`),
      status: text(row.status || row.pass_fail || metrics.pass_fail),
      metric: compactJoin([
        metricText('S', row.sharpe ?? metrics.sharpe),
        metricText('F', row.fitness ?? metrics.fitness),
        metricText('TO', row.turnover ?? metrics.turnover),
      ]),
      detail: text(row.expression || regular.code || row.code || row.region || row.universe),
      timestamp: text(row.updated_at || row.dateCreated || row.loaded_at),
    };
  });
}

export function cloudMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const summary = record(payload.summary);
  return [
    {
      label: '缓存总数',
      value: text(summary.total ?? summary.count ?? summary.total_count ?? '-'),
    },
    { label: '载入状态', value: cloudLoadStatus(summary) },
    { label: '已提交', value: text(summary.submitted_count ?? '-') },
    { label: '已通过', value: text(summary.passed_unsubmitted_count ?? '-') },
  ];
}

function cloudLoadStatus(summary: Record<string, unknown>) {
  const displayLimit = Number(summary.display_limit);
  if (Number.isFinite(displayLimit) && displayLimit > 0) {
    const returned = text(summary.returned_count ?? '-');
    const total = text(summary.total ?? summary.count ?? summary.total_count ?? '-');
    return `${returned} / ${total} 预览`;
  }
  return '完整载入';
}
