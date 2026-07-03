/** SnapshotPanel view configurations and data extractors. */

import {
  text,
  record,
  array,
  truthy,
  metricText,
  ratioText,
  countText,
  isSnapshotPassStatus,
  safeSnapshotDisplayText,
  rowId,
  dedupeSnapshotRows,
  dedupeRows,
  namedRows,
  signalRows,
  compactJoin,
  RAW_SNAPSHOT_TEXT_PATTERN,
  cloudRows,
  cloudMetrics,
  type SnapshotMetric,
  type SnapshotPayload,
  type SnapshotRow,
} from './utils';
import { readinessReasonLabel } from '@/helpers/readinessLabels';

export type SnapshotView =
  | 'cloud'
  | 'checkpoint_status'
  | 'lifecycle'
  | 'research_memory'
  | 'research_knowledge'
  | 'research_observability'
  | 'prompt_runs'
  | 'sqlite_indexes'
  | 'robustness';

export interface SnapshotConfig {
  title: string;
  subtitle: string;
  endpoint: string;
  empty: string;
  rows: (payload: SnapshotPayload) => SnapshotRow[];
  metrics?: (payload: SnapshotPayload, rows: SnapshotRow[]) => SnapshotMetric[];
}

// === Local snapshot data extractors ===

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

// === Compare/robustness data extractors ===

export function checkpointComparisonSummary(payload: SnapshotPayload) {
  const latestComparison = record(payload.latest_comparison);
  const deltas = record(latestComparison.deltas);
  const keys = Object.keys(deltas)
    .map((key) => safeSnapshotDisplayText(key, '对比项待确认'))
    .filter(Boolean);
  if (!keys.length) return '';
  return `对比 ${keys.length} 项: ${keys.slice(0, 3).join(', ')}`;
}

export function robustnessRows(payload: SnapshotPayload) {
  const candidateRows = latestCandidateRows(payload).flatMap((candidate, index) => {
    const row = record(candidate);
    const anti = candidateReport(row, 'anti_overfit_report');
    const rolling = candidateReport(row, 'rolling_validation_report');
    const alphaId = text(
      row.alpha_id || row.official_alpha_id || row.simulation_id || `candidate_${index + 1}`
    );
    const rows: SnapshotRow[] = [];
    if (Object.keys(anti).length) {
      rows.push({
        id: `${alphaId}_anti`,
        kind: 'anti_overfit',
        title: alphaId,
        status: text(anti.recommendation || anti.status || anti.passed),
        metric: metricText('score', anti.score),
        detail: failedTests(anti),
        timestamp: text(anti.generated_at || row.updated_at),
      });
    }
    if (Object.keys(rolling).length) {
      rows.push({
        id: `${alphaId}_rolling`,
        kind: 'rolling_validation',
        title: alphaId,
        status: text(rolling.status || rolling.passed),
        metric: compactJoin([
          metricText('score', rolling.score),
          metricText('sample', rolling.sample_size),
        ]),
        detail: failedTests(rolling),
        timestamp: text(rolling.generated_at || row.updated_at),
      });
    }
    return rows;
  });
  return [...replayAuditRows(payload), ...candidateRows];
}

export function robustnessMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const antiRows = rows.filter((row) => row.kind === 'anti_overfit');
  const rollingRows = rows.filter((row) => row.kind === 'rolling_validation');
  const metrics = [
    { label: '行数', value: String(rows.length) },
    { label: '防过拟合', value: String(antiRows.length) },
    { label: '滚动验证', value: String(rollingRows.length) },
    {
      label: '警告',
      value: String(rows.filter((row) => row.status && !isSnapshotPassStatus(row.status)).length),
    },
  ];
  const audit = replayAuditPayload(payload);
  if (Object.keys(audit).length) {
    metrics.push(
      {
        label: '回放候选',
        value: ratioText(audit.recovered_candidate_count, audit.total_candidate_count),
      },
      {
        label: '生命周期命中',
        value: ratioText(audit.lifecycle_rows_used_count, audit.lifecycle_row_count),
      },
      {
        label: '科学审计',
        value: ratioText(audit.candidates_with_scientific_audit, audit.recovered_candidate_count),
      },
      { label: '非提交边界', value: replayBoundaryOk(audit) ? '已锁定' : '需复核' }
    );
  }
  return metrics;
}

function replayAuditRows(payload: SnapshotPayload): SnapshotRow[] {
  const audit = replayAuditPayload(payload);
  if (!Object.keys(audit).length) return [];
  const productionCounts = replayCountSummary(audit.production_decision_counts, '决策:0');
  const blockerCounts = replayCountSummary(audit.readiness_blocker_counts, '阻断:0', 'readiness');
  const executionGaps = replayCountSummary(audit.execution_gap_counts, '缺口:0');
  const queueCounts = replayCountSummary(audit.workflow_queue_counts, '队列:0');
  const stopRule = replayStopRule(audit.stop_rule);
  return [
    {
      id: 'replay_audit_recovery',
      kind: 'replay_audit',
      title: '本地回放审计',
      status: replayBoundaryOk(audit) ? 'ready' : 'warning',
      metric: compactJoin([
        `候选:${ratioText(audit.recovered_candidate_count, audit.total_candidate_count)}`,
        `生命周期:${ratioText(audit.lifecycle_rows_used_count, audit.lifecycle_row_count)}`,
      ]),
      detail: compactJoin([stopRule, '本地只读', '未调用官方接口', '不允许提交']),
      timestamp: '',
    },
    {
      id: 'replay_audit_decisions',
      kind: 'replay_decision',
      title: '生产决策证据',
      status: Number(audit.candidates_with_production_decision ?? 0) > 0 ? 'ready' : 'missing',
      metric: productionCounts,
      detail: compactJoin([blockerCounts, executionGaps]),
      timestamp: '',
    },
    {
      id: 'replay_audit_scientific',
      kind: 'replay_scientific',
      title: '科学审计证据',
      status: replayScientificBoundaryOk(audit)
        ? Number(audit.candidates_missing_scientific_audit ?? 0) > 0
          ? 'warning'
          : 'ready'
        : 'blocked',
      metric: compactJoin([
        `审计:${ratioText(audit.candidates_with_scientific_audit, audit.recovered_candidate_count)}`,
        `缺口:${countText(audit.candidates_missing_scientific_audit)}`,
      ]),
      detail: compactJoin([
        truthy(audit.workflow_plan_available) ? `工作流:${queueCounts}` : '工作流:未恢复',
        truthy(audit.scientific_audit_summary_available) ? '科学审计摘要可用' : '科学审计摘要缺失',
      ]),
      timestamp: '',
    },
  ];
}

function replayAuditPayload(payload: SnapshotPayload) {
  return record(record(payload.result).replay_audit);
}

function replayBoundaryOk(audit: SnapshotPayload) {
  return (
    truthy(audit.submit_boundary_intact) &&
    !truthy(audit.submit_allowed) &&
    !truthy(audit.real_submit_performed)
  );
}

function replayScientificBoundaryOk(audit: SnapshotPayload) {
  return truthy(audit.scientific_submit_boundary_intact);
}

function replayStopRule(value: unknown) {
  const raw = text(value);
  if (/check_live_submit_readiness\.py/.test(raw) && !RAW_SNAPSHOT_TEXT_PATTERN.test(raw)) {
    return '停机规则:check_live_submit_readiness.py';
  }
  return '停机规则待确认';
}

function replayCountSummary(
  value: unknown,
  fallback: string,
  labelMode: 'safe' | 'readiness' = 'safe'
) {
  const entries = Object.entries(record(value))
    .map(([key, count]) => {
      const label =
        labelMode === 'readiness'
          ? readinessReasonLabel(safeSnapshotDisplayText(key, ''), '阻断原因待确认')
          : safeSnapshotDisplayText(key, '项待确认');
      return label ? `${label}:${countText(count)}` : '';
    })
    .filter(Boolean);
  return entries.length ? entries.slice(0, 4).join(' ') : fallback;
}

function latestCandidateRows(payload: SnapshotPayload) {
  const result = record(payload.result);
  const progress = record(payload.progress);
  const summary = record(result.summary || progress.data || payload.summary);
  return dedupeRows([
    ...array(result.candidates),
    ...array(summary.candidates),
    ...array(summary.passed_candidates),
    ...array(summary.pending_backtest_candidates),
    ...array(summary.submitted_candidates),
  ]);
}

function candidateReport(candidate: SnapshotPayload, key: string) {
  const submission = record(candidate.submission);
  const scorecard = record(candidate.scorecard);
  return record(submission[key] || scorecard[key] || candidate[key]);
}

function failedTests(report: SnapshotPayload) {
  const tests = array(report.tests)
    .map(record)
    .filter((row) => row.passed === false)
    .map((row) => text(row.name || row.check_name))
    .filter(Boolean);
  return tests.length
    ? tests.join(', ')
    : text(report.summary || report.message || report.recommendation || report.status);
}

// === View configurations ===

export const SNAPSHOT_VIEWS: Record<SnapshotView, SnapshotConfig> = {
  cloud: {
    title: '云端数据',
    subtitle: '完整缓存的 Alpha 状态',
    endpoint: '/api/snapshot/cloud',
    empty: '暂无云端 Alpha 记录',
    rows: cloudRows,
    metrics: cloudMetrics,
  },
  checkpoint_status: {
    title: '续跑记录',
    subtitle: '上次进度、运行历史与收敛趋势',
    endpoint: '/api/checkpoint_status',
    empty: '暂无可续跑记录或运行历史',
    rows: checkpointStatusRows,
    metrics: checkpointStatusMetrics,
  },
  lifecycle: {
    title: '生命周期',
    subtitle: '审计跟踪',
    endpoint: '/api/lifecycle',
    empty: '暂无生命周期事件',
    rows: lifecycleRows,
  },
  research_memory: {
    title: '研究记忆',
    subtitle: '本地研究摘要',
    endpoint: '/api/research_memory?limit=5000&top_n=10',
    empty: '暂无研究记忆记录',
    rows: researchMemoryRows,
    metrics: researchMemoryMetrics,
  },
  research_knowledge: {
    title: '知识库',
    subtitle: '规则、发现、失败',
    endpoint: '/api/research_knowledge?limit=100&min_confidence=0',
    empty: '暂无知识记录',
    rows: researchKnowledgeRows,
    metrics: researchKnowledgeMetrics,
  },
  research_observability: {
    title: '可观测性',
    subtitle: '研究健康状态',
    endpoint: '/api/research_observability?limit=5000&top_n=10&include_cloud=true',
    empty: '暂无可观测性信号',
    rows: researchObservabilityRows,
    metrics: researchObservabilityMetrics,
  },
  prompt_runs: {
    title: '提示运行',
    subtitle: '提示账本',
    endpoint: '/api/prompt_runs?limit=100',
    empty: '暂无提示运行记录',
    rows: promptRunRows,
  },
  sqlite_indexes: {
    title: 'SQLite 索引',
    subtitle: '缓存健康状态',
    endpoint: '/api/sqlite_indexes?top_n=10',
    empty: '暂无 SQLite 索引记录',
    rows: sqliteIndexRows,
    metrics: sqliteIndexMetrics,
  },
  robustness: {
    title: '稳健性',
    subtitle: '防过拟合与滚动验证',
    endpoint: '/api/latest_result',
    empty: '暂无稳健性证据',
    rows: robustnessRows,
    metrics: robustnessMetrics,
  },
};
