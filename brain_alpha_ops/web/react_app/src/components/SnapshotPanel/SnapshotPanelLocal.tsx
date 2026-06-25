import {
  text,
  record,
  array,
  truthy,
  metricText,
  safeSnapshotDisplayText,
  rowId,
  dedupeSnapshotRows,
  namedRows,
  signalRows,
  compactJoin,
  type SnapshotPayload,
  type SnapshotRow,
} from './utils';

export function checkpointStatusRows(payload: SnapshotPayload): SnapshotRow[] {
  const latest = record(payload.latest);
  const latestHistory = record(payload.latest_history);
  const latestComparison = record(payload.latest_comparison);
  const analytics = record(payload.history_analytics);
  const rows: SnapshotRow[] = [];

  if (Object.keys(latest).length) {
    rows.push({
      id: rowId(latest, 'latest_checkpoint'),
      kind: 'checkpoint',
      title: text(latest.run_id || latest.checkpoint_id || 'latest_checkpoint'),
      status: truthy(payload.resume_available) ? 'resume_available' : 'recorded',
      metric: text(latest.phase_completed || latest.stage || latest.cycle_number || ''),
      detail: text(latest.summary || latest.message || latest.error || '记录已保存'),
      timestamp: text(latest.saved_at || latest.timestamp || latest.updated_at),
    });
  }

  rows.push(
    ...((payload.checkpoints as unknown[]) || []).map((item, index) => {
      const row = record(item);
      return {
        id: rowId(row, `checkpoint_${index}`),
        kind: 'checkpoint',
        title: text(row.run_id || row.checkpoint_id || `checkpoint_${index + 1}`),
        status: text(row.status || row.phase_completed || row.stage || 'recorded'),
        metric: text(row.cycle_number ?? row.step ?? ''),
        detail: text(row.summary || row.message || row.error || row.path),
        timestamp: text(row.saved_at || row.timestamp || row.updated_at),
      };
    })
  );

  if (Object.keys(latestHistory).length) {
    rows.push({
      id: rowId(latestHistory, 'latest_history'),
      kind: 'history',
      title: text(latestHistory.run_id || 'latest_history'),
      status: text(latestHistory.status || latestHistory.outcome || 'recorded'),
      metric: metricText('score', latestHistory.best_score ?? latestHistory.score),
      detail: text(
        latestHistory.summary ||
          latestHistory.message ||
          latestHistory.error ||
          latestHistory.best_alpha_id
      ),
      timestamp: text(
        latestHistory.completed_at || latestHistory.started_at || latestHistory.timestamp
      ),
    });
  }

  rows.push(
    ...((payload.history as unknown[]) || []).map((item, index) => {
      const row = record(item);
      return {
        id: rowId(row, `history_${index}`),
        kind: 'history',
        title: text(row.run_id || `history_${index + 1}`),
        status: text(row.status || row.outcome || 'recorded'),
        metric: metricText('score', row.best_score ?? row.score),
        detail: text(row.summary || row.message || row.error || row.best_alpha_id),
        timestamp: text(row.completed_at || row.started_at || row.timestamp),
      };
    })
  );

  rows.push(...comparisonRows(latestComparison));
  rows.push(...analyticsRows(analytics));
  return dedupeSnapshotRows(rows);
}

export function checkpointStatusMetrics(payload: SnapshotPayload, _rows: SnapshotRow[]) {
  const analytics = record(payload.history_analytics);
  return [
    { label: '续跑记录', value: text(payload.checkpoint_count ?? '0') },
    { label: '历史记录', value: text(payload.history_count ?? '0') },
    { label: '可续跑', value: truthy(payload.resume_available) ? '是' : '否' },
    {
      label: '趋势',
      value:
        safeSnapshotDisplayText(analytics.trend_status || analytics.status || '-', '趋势待确认') ||
        '-',
    },
  ];
}

function comparisonRows(comparison: SnapshotPayload) {
  const deltas = record(comparison.deltas);
  return Object.entries(deltas).map(([key, value]) => ({
    id: `comparison_${key}`,
    kind: 'comparison',
    title: safeSnapshotDisplayText(key, '对比项待确认'),
    status: 'delta',
    metric: text(value),
    detail: text(comparison.summary || comparison.baseline_run_id || comparison.current_run_id),
    timestamp: text(comparison.generated_at || comparison.timestamp),
  }));
}

function analyticsRows(analytics: SnapshotPayload) {
  const rows = [
    { key: 'trend_status', value: analytics.trend_status || analytics.status },
    { key: 'latest_run_id', value: analytics.latest_run_id },
    { key: 'history_count', value: analytics.history_count },
    { key: 'latest_comparison_available', value: analytics.latest_comparison_available },
  ].filter((item) => item.value !== undefined && item.value !== null && item.value !== '');
  return rows.map((item) => ({
    id: `analytics_${item.key}`,
    kind: 'analytics',
    title: item.key,
    status: 'ready',
    metric: text(item.value),
    detail: text(analytics.schema_version || 'run_history_analytics'),
    timestamp: text(analytics.generated_at || analytics.timestamp),
  }));
}

export function lifecycleRows(payload: SnapshotPayload) {
  return ((payload.records as unknown[]) || []).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `life_${index}`),
      kind: 'lifecycle',
      title: text(
        row.alpha_id ||
          row.official_alpha_id ||
          row.simulation_id ||
          row.run_id ||
          `event_${index + 1}`
      ),
      status: text(row.status || row.lifecycle_status || row.status_category),
      metric: text(row.stage || row.status_category),
      detail: text(row.message || row.note || row.family || row.expression),
      timestamp: text(row.timestamp || row.created_at || row.updated_at),
    };
  });
}

export function researchMemoryRows(payload: SnapshotPayload) {
  return [
    ...namedRows('family', array(payload.families), 'name'),
    ...namedRows('field', array(payload.fields), 'name'),
    ...namedRows('operator', array(payload.operators), 'name'),
    ...namedRows('failure', array(payload.failure_patterns), 'reason'),
    ...array(payload.recommendations).map((item, index) => ({
      id: `recommendation_${index}`,
      kind: 'recommendation',
      title: `recommendation_${index + 1}`,
      status: '',
      metric: '',
      detail: text(item),
      timestamp: '',
    })),
  ];
}

export function researchMemoryMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  return [
    { label: '行数', value: String(rows.length) },
    { label: '候选数量', value: text(payload.total_candidates ?? '0') },
    { label: '生命周期', value: text(payload.total_lifecycle_records ?? '0') },
    { label: '检查记录', value: text(payload.total_check_records ?? '0') },
  ];
}

export function researchKnowledgeRows(payload: SnapshotPayload) {
  return array(payload.items).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `knowledge_${index}`),
      kind: text(row.kind || 'knowledge'),
      title: text(row.title || row.knowledge_id || row.entry_id || `knowledge_${index + 1}`),
      status: text(row.confidence ?? ''),
      metric: compactJoin([
        metricText('evidence', array(row.evidence).length),
        text(row.source_run_id),
      ]),
      detail: text(row.body || row.expression_pattern || row.category),
      timestamp: text(row.updated_at || row.created_at),
    };
  });
}

export function researchKnowledgeMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const counts = record(payload.counts);
  return [
    { label: '行数', value: String(rows.length) },
    { label: '规则', value: text(counts.rules ?? '0') },
    { label: '发现', value: text(counts.findings ?? '0') },
    { label: '失败', value: text(counts.failures ?? '0') },
  ];
}

export function researchObservabilityRows(payload: SnapshotPayload) {
  const health = record(payload.health);
  const errors = record(payload.errors);
  const backtests = record(payload.backtests);
  const checks = record(payload.checks);
  return [
    ...signalRows('blocking', array(health.blocking_flags), 'blocked'),
    ...signalRows('warning', array(health.warning_flags), 'warning'),
    ...signalRows('health', array(health.health_flags), text(health.risk_level || 'unknown')),
    ...signalRows('recommendation', array(payload.recommendations), 'action'),
    ...namedRows('error', array(errors.recent_errors || errors.top_errors), 'error_code'),
    ...namedRows('backtest', array(backtests.failure_patterns), 'reason'),
    ...namedRows('check', array(checks.failure_patterns || checks.blocking_patterns), 'reason'),
  ];
}

export function researchObservabilityMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const health = record(payload.health);
  const errors = record(payload.errors);
  return [
    { label: '行数', value: String(rows.length) },
    { label: '风险', value: text(health.risk_level || '未知') },
    { label: '错误', value: text(errors.total ?? '0') },
    { label: '阻断', value: text(array(health.blocking_flags).length) },
  ];
}

export function promptRunRows(payload: SnapshotPayload) {
  return array(payload.items).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `prompt_${index}`),
      kind: 'prompt_run',
      title: text(row.prompt_digest || row.response_digest || `prompt_${index + 1}`),
      status: text(row.parse_status || 'recorded'),
      metric: compactJoin([text(row.model), metricText('T', row.temperature)]),
      detail: compactJoin([text(row.context_digest), text(row.schema_version)]),
      timestamp: text(row.timestamp),
    };
  });
}

export function sqliteIndexRows(payload: SnapshotPayload) {
  const expression = record(payload.expression_index);
  const records = record(payload.record_index);
  return [
    {
      id: 'record_index',
      kind: 'record_index',
      title: 'record_index',
      status: records.ok === false ? 'missing' : 'ready',
      metric: metricText('rows', records.row_count),
      detail: text(records.db_path || records.error || records.source),
      timestamp: text(records.latest_timestamp),
    },
    ...namedRows('duplicate', array(expression.duplicates), 'expression_canonical'),
    ...namedRows('frequent', array(expression.frequent_expressions), 'expression_canonical'),
    ...namedRows('field', array(expression.fields), 'name'),
    ...namedRows('operator', array(expression.operators), 'name'),
    ...namedRows('window', array(expression.windows), 'window'),
  ];
}

export function sqliteIndexMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const expression = record(payload.expression_index);
  const recordIndex = record(payload.record_index);
  return [
    { label: '行数', value: String(rows.length) },
    { label: '表达式', value: text(expression.total_expression_records ?? '0') },
    { label: '重复', value: text(expression.duplicate_expression_count ?? '0') },
    { label: '记录', value: text(recordIndex.row_count ?? '0') },
  ];
}
