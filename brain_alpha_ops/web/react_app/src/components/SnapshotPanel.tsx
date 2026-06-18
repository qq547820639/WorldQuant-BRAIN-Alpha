/** Read-only data and research snapshot views. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiErrorMessage, knownApiErrorMessage } from "@/helpers/errorExperience";
import {
  MAX_FILTER_LENGTH,
  RAW_SNAPSHOT_TEXT_PATTERN,
  LOCAL_SNAPSHOT_PATH_PATTERN,
  SNAPSHOT_STATUS_LABELS,
  type SnapshotRow,
  type SnapshotMetric,
  text,
  record,
  array,
  truthy,
  safeSnapshotDisplayText,
  snapshotStatusLabel,
  safeSnapshotDetail,
  statusBadge,
  isSnapshotPassStatus,
  metricText,
  ratioText,
  countText,
  sanitizeTextInput,
  formatOptionalNumber,
  formatLocalBacktestStatus,
} from "./utils";
import { readinessReasonLabel } from "@/helpers/readinessLabels";
import { useApi } from "@/hooks/useApi";
import ProgressFeedback from "@/components/ProgressFeedback";
import type { CardViewId } from "@/types";

export type SnapshotView =
  | "cloud"
  | "checkpoint_status"
  | "lifecycle"
  | "research_memory"
  | "research_knowledge"
  | "research_observability"
  | "prompt_runs"
  | "sqlite_indexes"
  | "robustness";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  viewMode: SnapshotView;
  onNavigate?: (view: CardViewId) => void;
}

interface SnapshotRow {
  id: string;
  kind: string;
  title: string;
  status: string;
  metric: string;
  detail: string;
  timestamp: string;
}

interface SnapshotMetric {
  label: string;
  value: string;
}

interface SnapshotConfig {
  title: string;
  subtitle: string;
  endpoint: string;
  empty: string;
  rows: (payload: SnapshotPayload) => SnapshotRow[];
  metrics?: (payload: SnapshotPayload, rows: SnapshotRow[]) => SnapshotMetric[];
}

type SnapshotPayload = Record<string, unknown>;





const SNAPSHOT_VIEWS: Record<SnapshotView, SnapshotConfig> = {
  cloud: {
    title: "云端数据",
    subtitle: "完整缓存的 Alpha 状态",
    endpoint: "/api/snapshot/cloud",
    empty: "暂无云端 Alpha 记录",
    rows: cloudRows,
    metrics: cloudMetrics,
  },
  checkpoint_status: {
    title: "续跑记录",
    subtitle: "上次进度、运行历史与收敛趋势",
    endpoint: "/api/checkpoint_status",
    empty: "暂无可续跑记录或运行历史",
    rows: checkpointStatusRows,
    metrics: checkpointStatusMetrics,
  },
  lifecycle: {
    title: "生命周期",
    subtitle: "审计跟踪",
    endpoint: "/api/lifecycle",
    empty: "暂无生命周期事件",
    rows: lifecycleRows,
  },
  research_memory: {
    title: "研究记忆",
    subtitle: "本地研究摘要",
    endpoint: "/api/research_memory?limit=5000&top_n=10",
    empty: "暂无研究记忆记录",
    rows: researchMemoryRows,
    metrics: researchMemoryMetrics,
  },
  research_knowledge: {
    title: "知识库",
    subtitle: "规则、发现、失败",
    endpoint: "/api/research_knowledge?limit=100&min_confidence=0",
    empty: "暂无知识记录",
    rows: researchKnowledgeRows,
    metrics: researchKnowledgeMetrics,
  },
  research_observability: {
    title: "可观测性",
    subtitle: "研究健康状态",
    endpoint: "/api/research_observability?limit=5000&top_n=10&include_cloud=true",
    empty: "暂无可观测性信号",
    rows: researchObservabilityRows,
    metrics: researchObservabilityMetrics,
  },
  prompt_runs: {
    title: "提示运行",
    subtitle: "提示账本",
    endpoint: "/api/prompt_runs?limit=100",
    empty: "暂无提示运行记录",
    rows: promptRunRows,
  },
  sqlite_indexes: {
    title: "SQLite 索引",
    subtitle: "缓存健康状态",
    endpoint: "/api/sqlite_indexes?top_n=10",
    empty: "暂无 SQLite 索引记录",
    rows: sqliteIndexRows,
    metrics: sqliteIndexMetrics,
  },
  robustness: {
    title: "稳健性",
    subtitle: "防过拟合与滚动验证",
    endpoint: "/api/latest_result",
    empty: "暂无稳健性证据",
    rows: robustnessRows,
    metrics: robustnessMetrics,
  },
};

export default function SnapshotPanel({ notify, viewMode, onNavigate }: Props) {
  const api = useApi<SnapshotPayload>();
  const [filter, setFilter] = useState("");
  const config = SNAPSHOT_VIEWS[viewMode];
  const callApi = api.call;

  const load = useCallback(async () => {
    const result = await callApi<SnapshotPayload>(config.endpoint);
    if (result?.error) notify("error", apiErrorMessage(result, `${config.title}加载失败`));
  }, [callApi, config.endpoint, notify]);

  useEffect(() => { void load(); }, [load]);

  const payload = api.data || {};
  const rows = useMemo(() => config.rows(payload).map(normalizeSnapshotRow), [config, payload]);
  const metrics = useMemo(() => config.metrics?.(payload, rows) || defaultMetrics(payload, rows), [config, payload, rows]);
  const normalizedFilter = filter.trim().toLowerCase();
  const filteredRows = normalizedFilter
    ? rows.filter((row) => rowText(row).includes(normalizedFilter))
    : rows;
  const comparisonSummary = viewMode === "checkpoint_status" ? checkpointComparisonSummary(payload) : "";

  if (api.loading && !api.data) {
    return (
      <ProgressFeedback
        state="loading"
        title={config.title}
        progress={{ phase: "snapshot_load", status_message: `正在加载 ${config.title}。` }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-text-primary">{config.title}</h2>
          <p className="text-xs text-text-tertiary">{config.subtitle}</p>
        </div>
        <button type="button" onClick={load} className="btn btn-secondary btn-sm" disabled={api.loading}>
          刷新
        </button>
      </div>

      <ProgressFeedback
        state={api.error ? "error" : api.loading ? "loading" : "idle"}
        title={config.title}
        progress={{ phase: api.loading ? "snapshot_load" : "completed", status_message: api.loading ? `正在刷新 ${config.title}。` : `${config.title} 快照已加载。` }}
        error={api.error}
        onRetry={load}
        compact={!api.loading && !api.error}
      />

      {viewMode === "checkpoint_status" && (
        <div
          className="rounded-lg p-4"
          style={{ border: '1px solid', borderColor: 'oklch(0.65 0.14 80 / 0.25)', backgroundColor: 'oklch(0.65 0.14 80 / 0.10)' }}
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-medium text-accent">
                {truthy(payload.resume_available) ? "检测到可继续的上次进度" : "暂无可继续的上次进度"}
              </p>
              <p className="mt-1 text-xs text-text-secondary">
                {truthy(payload.resume_available)
                  ? "先回到候选管理确认候选状态，再进入质量门禁复核是否满足提交前检查。"
                  : "新的生产搜索会在候选管理中创建续跑记录与历史记录。"}
              </p>
              {comparisonSummary && (
                <p className="mt-2 text-xs text-accent">
                  {comparisonSummary}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigate?.("candidates")}
                disabled={!onNavigate}
              >
                进入候选管理
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => onNavigate?.("quality_check")}
                disabled={!onNavigate}
              >
                查看质量门禁
              </button>
            </div>
          </div>
        </div>
      )}

      {api.error && (
        <div
          className="panel"
          role="alert"
          aria-live="assertive"
          style={{ borderColor: 'oklch(0.48 0.08 22 / 0.30)', backgroundColor: 'oklch(0.48 0.06 22 / 0.08)' }}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-negative text-sm">加载 {config.title} 失败: {api.error}</p>
            <button type="button" onClick={load} className="btn btn-secondary btn-sm" disabled={api.loading}>
              重试
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="kpi-card">
            <p className="kpi-card-label">{metric.label}</p>
            <p className="kpi-card-value">{metric.value}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="text"
          aria-label={`筛选 ${config.title}`}
          placeholder="筛选行..."
          value={filter}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(event) => setFilter(sanitizeTextInput(event.target.value, MAX_FILTER_LENGTH))}
          className="w-full min-w-0 rounded-md px-3 py-2 text-sm sm:flex-1"
          style={{
            backgroundColor: 'oklch(0.115 0.007 45)',
            border: '1px solid',
            borderColor: 'oklch(0.28 0.008 45)',
            color: 'oklch(0.92 0.003 45)',
          }}
        />
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          {filteredRows.length} / {rows.length} 行
        </p>
      </div>

      <div className="panel overflow-hidden p-0">
        <div className="space-y-3 p-3 md:hidden" aria-label={`${config.title}移动列表`}>
          {filteredRows.length === 0 ? (
            <div
              className="rounded-md px-4 py-6 text-center text-sm text-text-tertiary"
              style={{
                border: '1px solid',
                borderColor: 'oklch(0.22 0.007 45 / 0.60)',
                backgroundColor: 'oklch(0.100 0.007 45 / 0.50)',
              }}
            >
              {config.empty}
            </div>
          ) : (
            filteredRows.map((row, index) => <SnapshotMobileCard key={`${row.kind}_${row.id}_mobile_${index}`} row={row} />)
          )}
        </div>

        <div className="hidden max-w-full overflow-auto md:block">
          <table className="data-table min-w-[820px] w-full text-sm" aria-label={`${config.title}表格`}>
            <thead>
              <tr
                className="text-left text-xs uppercase tracking-wider"
                style={{ borderBottom: '1px solid', borderColor: 'oklch(0.28 0.008 45)' }}
              >
                <th scope="col" className="p-3 text-text-tertiary">类型</th>
                <th scope="col" className="p-3 text-text-tertiary">名称</th>
                <th scope="col" className="p-3 text-text-tertiary">状态</th>
                <th scope="col" className="p-3 text-text-tertiary">指标</th>
                <th scope="col" className="p-3 text-text-tertiary">详情</th>
                <th scope="col" className="p-3 text-text-tertiary">时间</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-text-tertiary">{config.empty}</td></tr>
              ) : (
                filteredRows.map((row, index) => (
                  <tr
                    key={`${row.kind}_${row.id}_${index}`}
                    className="transition-colors"
                    style={{ borderBottom: '1px solid', borderColor: 'oklch(0.22 0.007 45 / 0.50)' }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.backgroundColor = 'oklch(0.115 0.007 45 / 0.30)'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.backgroundColor = ''; }}
                  >
                    <td className="p-3 text-xs text-text-tertiary">{displayKind(row.kind)}</td>
                    <td className="p-3 font-mono-value text-xs text-accent">{row.title || row.id || "-"}</td>
                    <td className="p-3"><span className={`badge text-xs ${statusBadge(row.status)}`}>{row.status || "-"}</span></td>
                    <td className="p-3 font-mono-value text-xs">{row.metric || "-"}</td>
                    <td className="p-3 text-xs text-text-secondary max-w-md truncate" title={row.detail}>{row.detail || "-"}</td>
                    <td className="p-3 font-mono-value text-xs text-text-tertiary">{row.timestamp || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function defaultMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  return [
    { label: "行数", value: String(rows.length) },
    { label: "来源", value: text(payload.source || "快照") },
    { label: "版本", value: text(payload.schema_version || "-") },
    { label: "状态", value: payload.ok === false ? "错误" : "就绪" },
  ];
}

function normalizeSnapshotRow(row: SnapshotRow): SnapshotRow {
  return {
    ...row,
    title: safeSnapshotDisplayText(row.title || row.id, "记录待确认"),
    status: snapshotStatusLabel(row.status),
    metric: safeSnapshotDisplayText(row.metric, "指标待确认"),
    detail: safeSnapshotDetail(row.detail),
    timestamp: safeSnapshotDisplayText(row.timestamp, "时间待确认"),
  };
}

function snapshotStatusLabel(value: unknown) {
  const raw = text(value).trim();
  if (!raw) return "";
  const known = knownApiErrorMessage(raw);
  if (known) return known;
  if (RAW_SNAPSHOT_TEXT_PATTERN.test(raw)) return "状态待确认";
  const normalized = raw.toLowerCase();
  return SNAPSHOT_STATUS_LABELS[normalized] || "状态待确认";
}

function safeSnapshotDetail(value: unknown) {
  const raw = text(value).trim();
  if (!raw) return "";
  const known = knownApiErrorMessage(raw);
  if (known) return known;
  if (RAW_SNAPSHOT_TEXT_PATTERN.test(raw) || LOCAL_SNAPSHOT_PATH_PATTERN.test(raw)) return "详情待确认";
  return raw;
}

function safeSnapshotDisplayText(value: unknown, fallback: string) {
  const raw = text(value).trim();
  if (!raw) return "";
  if (knownApiErrorMessage(raw) || RAW_SNAPSHOT_TEXT_PATTERN.test(raw) || LOCAL_SNAPSHOT_PATH_PATTERN.test(raw)) return fallback;
  return raw;
}

function SnapshotMobileCard({ row }: { row: SnapshotRow }) {
  return (
    <article
      className="rounded-md p-4 text-sm"
      style={{
        border: '1px solid',
        borderColor: 'oklch(0.28 0.008 45 / 0.70)',
        backgroundColor: 'oklch(0.100 0.007 45 / 0.70)',
      }}
    >
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-wide text-text-tertiary">{displayKind(row.kind || "snapshot")}</p>
          <p className="mt-1 break-words font-mono-value text-xs text-accent">{row.title || row.id || "-"}</p>
        </div>
        <span className={`badge shrink-0 text-xs ${statusBadge(row.status)}`}>{row.status || "-"}</span>
      </div>
      <dl className="mt-4 grid gap-3 text-xs">
        <div>
          <dt className="text-text-tertiary">指标</dt>
          <dd className="mt-1 break-words font-mono-value text-text-primary">{row.metric || "-"}</dd>
        </div>
        <div>
          <dt className="text-text-tertiary">详情</dt>
          <dd className="mt-1 break-words text-text-secondary">{row.detail || "-"}</dd>
        </div>
        <div>
          <dt className="text-text-tertiary">时间</dt>
          <dd className="mt-1 break-words font-mono-value text-text-tertiary">{row.timestamp || "-"}</dd>
        </div>
      </dl>
    </article>
  );
}

function cloudMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const summary = record(payload.summary);
  return [
    { label: "缓存总数", value: text(summary.total ?? summary.count ?? summary.total_count ?? "-") },
    { label: "载入状态", value: cloudLoadStatus(summary) },
    { label: "已提交", value: text(summary.submitted_count ?? "-") },
    { label: "已通过", value: text(summary.passed_unsubmitted_count ?? "-") },
  ];
}

function cloudLoadStatus(summary: Record<string, unknown>) {
  const displayLimit = Number(summary.display_limit);
  if (Number.isFinite(displayLimit) && displayLimit > 0) {
    const returned = text(summary.returned_count ?? "-");
    const total = text(summary.total ?? summary.count ?? summary.total_count ?? "-");
    return `${returned} / ${total} 预览`;
  }
  return "完整载入";
}

function checkpointStatusMetrics(payload: SnapshotPayload, _rows: SnapshotRow[]) {
  const analytics = record(payload.history_analytics);
  return [
    { label: "续跑记录", value: text(payload.checkpoint_count ?? "0") },
    { label: "历史记录", value: text(payload.history_count ?? "0") },
    { label: "可续跑", value: truthy(payload.resume_available) ? "是" : "否" },
    { label: "趋势", value: safeSnapshotDisplayText(analytics.trend_status || analytics.status || "-", "趋势待确认") || "-" },
  ];
}

function checkpointComparisonSummary(payload: SnapshotPayload) {
  const latestComparison = record(payload.latest_comparison);
  const deltas = record(latestComparison.deltas);
  const keys = Object.keys(deltas)
    .map((key) => safeSnapshotDisplayText(key, "对比项待确认"))
    .filter(Boolean);
  if (!keys.length) return "";
  return `对比 ${keys.length} 项: ${keys.slice(0, 3).join(", ")}`;
}

function researchMemoryMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  return [
    { label: "行数", value: String(rows.length) },
    { label: "候选数量", value: text(payload.total_candidates ?? "0") },
    { label: "生命周期", value: text(payload.total_lifecycle_records ?? "0") },
    { label: "检查记录", value: text(payload.total_check_records ?? "0") },
  ];
}

function researchKnowledgeMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const counts = record(payload.counts);
  return [
    { label: "行数", value: String(rows.length) },
    { label: "规则", value: text(counts.rules ?? "0") },
    { label: "发现", value: text(counts.findings ?? "0") },
    { label: "失败", value: text(counts.failures ?? "0") },
  ];
}

function researchObservabilityMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const health = record(payload.health);
  const errors = record(payload.errors);
  return [
    { label: "行数", value: String(rows.length) },
    { label: "风险", value: text(health.risk_level || "未知") },
    { label: "错误", value: text(errors.total ?? "0") },
    { label: "阻断", value: text(array(health.blocking_flags).length) },
  ];
}

function sqliteIndexMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const expression = record(payload.expression_index);
  const recordIndex = record(payload.record_index);
  return [
    { label: "行数", value: String(rows.length) },
    { label: "表达式", value: text(expression.total_expression_records ?? "0") },
    { label: "重复", value: text(expression.duplicate_expression_count ?? "0") },
    { label: "记录", value: text(recordIndex.row_count ?? "0") },
  ];
}

function robustnessMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const antiRows = rows.filter((row) => row.kind === "anti_overfit");
  const rollingRows = rows.filter((row) => row.kind === "rolling_validation");
  const metrics = [
    { label: "行数", value: String(rows.length) },
    { label: "防过拟合", value: String(antiRows.length) },
    { label: "滚动验证", value: String(rollingRows.length) },
    { label: "警告", value: String(rows.filter((row) => row.status && !isSnapshotPassStatus(row.status)).length) },
  ];
  const audit = replayAuditPayload(payload);
  if (Object.keys(audit).length) {
    metrics.push(
      { label: "回放候选", value: ratioText(audit.recovered_candidate_count, audit.total_candidate_count) },
      { label: "生命周期命中", value: ratioText(audit.lifecycle_rows_used_count, audit.lifecycle_row_count) },
      { label: "科学审计", value: ratioText(audit.candidates_with_scientific_audit, audit.recovered_candidate_count) },
      { label: "非提交边界", value: replayBoundaryOk(audit) ? "已锁定" : "需复核" },
    );
  }
  return metrics;
}

function cloudRows(payload: SnapshotPayload) {
  return array(payload.alphas).map((item, index) => {
    const row = record(item);
    const metrics = record(row.metrics);
    const regular = record(row.regular);
    return {
      id: rowId(row, `cloud_${index}`),
      kind: "cloud",
      title: text(row.alpha_id || row.id || `cloud_${index + 1}`),
      status: text(row.status || row.pass_fail || metrics.pass_fail),
      metric: compactJoin([
        metricText("S", row.sharpe ?? metrics.sharpe),
        metricText("F", row.fitness ?? metrics.fitness),
        metricText("TO", row.turnover ?? metrics.turnover),
      ]),
      detail: text(row.expression || regular.code || row.code || row.region || row.universe),
      timestamp: text(row.updated_at || row.dateCreated || row.loaded_at),
    };
  });
}

function lifecycleRows(payload: SnapshotPayload) {
  return array(payload.records).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `life_${index}`),
      kind: "lifecycle",
      title: text(row.alpha_id || row.official_alpha_id || row.simulation_id || row.run_id || `event_${index + 1}`),
      status: text(row.status || row.lifecycle_status || row.status_category),
      metric: text(row.stage || row.status_category),
      detail: text(row.message || row.note || row.family || row.expression),
      timestamp: text(row.timestamp || row.created_at || row.updated_at),
    };
  });
}

function checkpointStatusRows(payload: SnapshotPayload) {
  const latest = record(payload.latest);
  const latestHistory = record(payload.latest_history);
  const latestComparison = record(payload.latest_comparison);
  const analytics = record(payload.history_analytics);
  const rows: SnapshotRow[] = [];

  if (Object.keys(latest).length) {
    rows.push({
      id: rowId(latest, "latest_checkpoint"),
      kind: "checkpoint",
      title: text(latest.run_id || latest.checkpoint_id || "latest_checkpoint"),
      status: truthy(payload.resume_available) ? "resume_available" : "recorded",
      metric: text(latest.phase_completed || latest.stage || latest.cycle_number || ""),
      detail: text(latest.summary || latest.message || latest.error || "记录已保存"),
      timestamp: text(latest.saved_at || latest.timestamp || latest.updated_at),
    });
  }

  rows.push(...array(payload.checkpoints).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `checkpoint_${index}`),
      kind: "checkpoint",
      title: text(row.run_id || row.checkpoint_id || `checkpoint_${index + 1}`),
      status: text(row.status || row.phase_completed || row.stage || "recorded"),
      metric: text(row.cycle_number ?? row.step ?? ""),
      detail: text(row.summary || row.message || row.error || row.path),
      timestamp: text(row.saved_at || row.timestamp || row.updated_at),
    };
  }));

  if (Object.keys(latestHistory).length) {
    rows.push({
      id: rowId(latestHistory, "latest_history"),
      kind: "history",
      title: text(latestHistory.run_id || "latest_history"),
      status: text(latestHistory.status || latestHistory.outcome || "recorded"),
      metric: metricText("score", latestHistory.best_score ?? latestHistory.score),
      detail: text(latestHistory.summary || latestHistory.message || latestHistory.error || latestHistory.best_alpha_id),
      timestamp: text(latestHistory.completed_at || latestHistory.started_at || latestHistory.timestamp),
    });
  }

  rows.push(...array(payload.history).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `history_${index}`),
      kind: "history",
      title: text(row.run_id || `history_${index + 1}`),
      status: text(row.status || row.outcome || "recorded"),
      metric: metricText("score", row.best_score ?? row.score),
      detail: text(row.summary || row.message || row.error || row.best_alpha_id),
      timestamp: text(row.completed_at || row.started_at || row.timestamp),
    };
  }));

  rows.push(...comparisonRows(latestComparison));
  rows.push(...analyticsRows(analytics));
  return dedupeSnapshotRows(rows);
}

function comparisonRows(comparison: SnapshotPayload) {
  const deltas = record(comparison.deltas);
  return Object.entries(deltas).map(([key, value]) => ({
    id: `comparison_${key}`,
    kind: "comparison",
    title: safeSnapshotDisplayText(key, "对比项待确认"),
    status: "delta",
    metric: text(value),
    detail: text(comparison.summary || comparison.baseline_run_id || comparison.current_run_id),
    timestamp: text(comparison.generated_at || comparison.timestamp),
  }));
}

function analyticsRows(analytics: SnapshotPayload) {
  const rows = [
    { key: "trend_status", value: analytics.trend_status || analytics.status },
    { key: "latest_run_id", value: analytics.latest_run_id },
    { key: "history_count", value: analytics.history_count },
    { key: "latest_comparison_available", value: analytics.latest_comparison_available },
  ].filter((item) => item.value !== undefined && item.value !== null && item.value !== "");
  return rows.map((item) => ({
    id: `analytics_${item.key}`,
    kind: "analytics",
    title: item.key,
    status: "ready",
    metric: text(item.value),
    detail: text(analytics.schema_version || "run_history_analytics"),
    timestamp: text(analytics.generated_at || analytics.timestamp),
  }));
}

function researchMemoryRows(payload: SnapshotPayload) {
  return [
    ...namedRows("family", array(payload.families), "name"),
    ...namedRows("field", array(payload.fields), "name"),
    ...namedRows("operator", array(payload.operators), "name"),
    ...namedRows("failure", array(payload.failure_patterns), "reason"),
    ...array(payload.recommendations).map((item, index) => ({
      id: `recommendation_${index}`,
      kind: "recommendation",
      title: `recommendation_${index + 1}`,
      status: "",
      metric: "",
      detail: text(item),
      timestamp: "",
    })),
  ];
}

function researchKnowledgeRows(payload: SnapshotPayload) {
  return array(payload.items).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `knowledge_${index}`),
      kind: text(row.kind || "knowledge"),
      title: text(row.title || row.knowledge_id || row.entry_id || `knowledge_${index + 1}`),
      status: text(row.confidence ?? ""),
      metric: compactJoin([metricText("evidence", array(row.evidence).length), text(row.source_run_id)]),
      detail: text(row.body || row.expression_pattern || row.category),
      timestamp: text(row.updated_at || row.created_at),
    };
  });
}

function researchObservabilityRows(payload: SnapshotPayload) {
  const health = record(payload.health);
  const errors = record(payload.errors);
  const backtests = record(payload.backtests);
  const checks = record(payload.checks);
  return [
    ...signalRows("blocking", array(health.blocking_flags), "blocked"),
    ...signalRows("warning", array(health.warning_flags), "warning"),
    ...signalRows("health", array(health.health_flags), text(health.risk_level || "unknown")),
    ...signalRows("recommendation", array(payload.recommendations), "action"),
    ...namedRows("error", array(errors.recent_errors || errors.top_errors), "error_code"),
    ...namedRows("backtest", array(backtests.failure_patterns), "reason"),
    ...namedRows("check", array(checks.failure_patterns || checks.blocking_patterns), "reason"),
  ];
}

function promptRunRows(payload: SnapshotPayload) {
  return array(payload.items).map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `prompt_${index}`),
      kind: "prompt_run",
      title: text(row.prompt_digest || row.response_digest || `prompt_${index + 1}`),
      status: text(row.parse_status || "recorded"),
      metric: compactJoin([text(row.model), metricText("T", row.temperature)]),
      detail: compactJoin([text(row.context_digest), text(row.schema_version)]),
      timestamp: text(row.timestamp),
    };
  });
}

function sqliteIndexRows(payload: SnapshotPayload) {
  const expression = record(payload.expression_index);
  const records = record(payload.record_index);
  return [
    {
      id: "record_index",
      kind: "record_index",
      title: "record_index",
      status: records.ok === false ? "missing" : "ready",
      metric: metricText("rows", records.row_count),
      detail: text(records.db_path || records.error || records.source),
      timestamp: text(records.latest_timestamp),
    },
    ...namedRows("duplicate", array(expression.duplicates), "expression_canonical"),
    ...namedRows("frequent", array(expression.frequent_expressions), "expression_canonical"),
    ...namedRows("field", array(expression.fields), "name"),
    ...namedRows("operator", array(expression.operators), "name"),
    ...namedRows("window", array(expression.windows), "window"),
  ];
}

function robustnessRows(payload: SnapshotPayload) {
  const candidateRows = latestCandidateRows(payload).flatMap((candidate, index) => {
    const row = record(candidate);
    const anti = candidateReport(row, "anti_overfit_report");
    const rolling = candidateReport(row, "rolling_validation_report");
    const alphaId = text(row.alpha_id || row.official_alpha_id || row.simulation_id || `candidate_${index + 1}`);
    const rows: SnapshotRow[] = [];
    if (Object.keys(anti).length) {
      rows.push({
        id: `${alphaId}_anti`,
        kind: "anti_overfit",
        title: alphaId,
        status: text(anti.recommendation || anti.status || anti.passed),
        metric: metricText("score", anti.score),
        detail: failedTests(anti),
        timestamp: text(anti.generated_at || row.updated_at),
      });
    }
    if (Object.keys(rolling).length) {
      rows.push({
        id: `${alphaId}_rolling`,
        kind: "rolling_validation",
        title: alphaId,
        status: text(rolling.status || rolling.passed),
        metric: compactJoin([metricText("score", rolling.score), metricText("sample", rolling.sample_size)]),
        detail: failedTests(rolling),
        timestamp: text(rolling.generated_at || row.updated_at),
      });
    }
    return rows;
  });
  return [...replayAuditRows(payload), ...candidateRows];
}

function replayAuditRows(payload: SnapshotPayload): SnapshotRow[] {
  const audit = replayAuditPayload(payload);
  if (!Object.keys(audit).length) return [];
  const productionCounts = replayCountSummary(audit.production_decision_counts, "决策:0");
  const blockerCounts = replayCountSummary(audit.readiness_blocker_counts, "阻断:0", "readiness");
  const executionGaps = replayCountSummary(audit.execution_gap_counts, "缺口:0");
  const queueCounts = replayCountSummary(audit.workflow_queue_counts, "队列:0");
  const stopRule = replayStopRule(audit.stop_rule);
  return [
    {
      id: "replay_audit_recovery",
      kind: "replay_audit",
      title: "本地回放审计",
      status: replayBoundaryOk(audit) ? "ready" : "warning",
      metric: compactJoin([
        `候选:${ratioText(audit.recovered_candidate_count, audit.total_candidate_count)}`,
        `生命周期:${ratioText(audit.lifecycle_rows_used_count, audit.lifecycle_row_count)}`,
      ]),
      detail: compactJoin([stopRule, "本地只读", "未调用官方接口", "不允许提交"]),
      timestamp: "",
    },
    {
      id: "replay_audit_decisions",
      kind: "replay_decision",
      title: "生产决策证据",
      status: Number(audit.candidates_with_production_decision ?? 0) > 0 ? "ready" : "missing",
      metric: productionCounts,
      detail: compactJoin([blockerCounts, executionGaps]),
      timestamp: "",
    },
    {
      id: "replay_audit_scientific",
      kind: "replay_scientific",
      title: "科学审计证据",
      status: replayScientificBoundaryOk(audit) ? (Number(audit.candidates_missing_scientific_audit ?? 0) > 0 ? "warning" : "ready") : "blocked",
      metric: compactJoin([
        `审计:${ratioText(audit.candidates_with_scientific_audit, audit.recovered_candidate_count)}`,
        `缺口:${countText(audit.candidates_missing_scientific_audit)}`,
      ]),
      detail: compactJoin([
        truthy(audit.workflow_plan_available) ? `工作流:${queueCounts}` : "工作流:未恢复",
        truthy(audit.scientific_audit_summary_available) ? "科学审计摘要可用" : "科学审计摘要缺失",
      ]),
      timestamp: "",
    },
  ];
}

function namedRows(kind: string, rows: unknown[], titleKey: string) {
  return rows.map((item, index) => {
    const row = record(item);
    return {
      id: rowId(row, `${kind}_${index}`),
      kind,
      title: text(row[titleKey] || row.name || row.reason || row.id || `${kind}_${index + 1}`),
      status: text(row.status || row.pass_fail || row.ok),
      metric: compactJoin([
        metricText("count", row.count ?? row.record_count),
        metricText("rate", row.success_rate ?? row.failure_rate),
        metricText("score", row.avg_score ?? row.max_score ?? row.score),
      ]),
      detail: text(row.detail || row.summary || row.body || row.expression || row.expression_canonical || row.error),
      timestamp: text(row.timestamp || row.updated_at || row.created_at),
    };
  });
}

function signalRows(kind: string, rows: unknown[], status: string) {
  return rows.map((item, index) => ({
    id: `${kind}_${index}`,
    kind,
    title: `${kind}_${index + 1}`,
    status,
    metric: "",
    detail: text(item),
    timestamp: "",
  }));
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
  return tests.length ? tests.join(", ") : text(report.summary || report.message || report.recommendation || report.status);
}

function dedupeRows(rows: unknown[]) {
  const seen = new Set<string>();
  const result: SnapshotPayload[] = [];
  for (const item of rows.map(record)) {
    const key = rowId(item, text(result.length));
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

function dedupeSnapshotRows(rows: SnapshotRow[]) {
  const seen = new Set<string>();
  const result: SnapshotRow[] = [];
  for (const row of rows) {
    const key = `${row.kind}:${row.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(row);
  }
  return result;
}

function rowId(row: SnapshotPayload, fallback: string) {
  return text(row.alpha_id || row.official_alpha_id || row.simulation_id || row.id || row.checkpoint_id || row.knowledge_id || row.entry_id || row.run_id || row.prompt_digest || row.expression_fingerprint || fallback);
}

function rowText(row: SnapshotRow) {
  return [
    safeSnapshotDisplayText(row.id, ""),
    displayKind(row.kind),
    row.title,
    row.status,
    row.metric,
    row.detail,
    row.timestamp,
  ].join(" ").toLowerCase();
}

function displayKind(kind: string) {
  const labels: Record<string, string> = {
    checkpoint: "续跑记录",
    history: "历史记录",
    comparison: "对比",
    analytics: "趋势",
    lifecycle: "生命周期",
    replay_audit: "回放审计",
    replay_decision: "决策审计",
    replay_scientific: "科学审计",
  };
  return labels[kind] || safeSnapshotDisplayText(kind, "类型待确认") || "类型待确认";
}

function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

function statusBadge(status: string) {
  const normalized = status.toLowerCase();
  if (["ready", "pass", "passed", "true", "submitted", "production", "就绪", "通过", "已提交", "生产中", "成功", "已完成", "活跃", "可续跑"].some((item) => normalized.includes(item))) return "badge badge-positive";
  if (["fail", "false", "missing", "blocked", "error", "rejected", "失败", "未通过", "缺失", "阻断", "错误", "已拒绝"].some((item) => normalized.includes(item))) return "badge badge-negative";
  if (["warn", "stale", "caution", "unknown", "警告", "需刷新", "需注意", "状态待确认"].some((item) => normalized.includes(item))) return "badge badge-warning";
  return "badge badge-neutral";
}

function isSnapshotPassStatus(status: string) {
  return ["pass", "passed", "ready", "true", "通过", "成功", "已完成", "就绪"].includes(status.trim().toLowerCase());
}

function metricText(label: string, value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "number") return `${label}:${Number.isInteger(value) ? value : value.toFixed(3)}`;
  const parsed = Number(value);
  if (Number.isFinite(parsed) && String(value).trim() !== "") return `${label}:${Number.isInteger(parsed) ? parsed : parsed.toFixed(3)}`;
  return `${label}:${text(value)}`;
}

function ratioText(numerator: unknown, denominator: unknown) {
  return `${countText(numerator)}/${countText(denominator)}`;
}

function countText(value: unknown) {
  if (value === undefined || value === null || value === "") return "0";
  const parsed = Number(value);
  if (Number.isFinite(parsed)) return String(Number.isInteger(parsed) ? parsed : Number(parsed.toFixed(3)));
  return safeSnapshotDisplayText(value, "0") || "0";
}

function replayAuditPayload(payload: SnapshotPayload) {
  return record(record(payload.result).replay_audit);
}

function replayBoundaryOk(audit: SnapshotPayload) {
  return truthy(audit.submit_boundary_intact) &&
    !truthy(audit.submit_allowed) &&
    !truthy(audit.real_submit_performed);
}

function replayScientificBoundaryOk(audit: SnapshotPayload) {
  return truthy(audit.scientific_submit_boundary_intact);
}

function replayStopRule(value: unknown) {
  const raw = text(value);
  if (/check_live_submit_readiness\.py/.test(raw) && !RAW_SNAPSHOT_TEXT_PATTERN.test(raw)) {
    return "停机规则:check_live_submit_readiness.py";
  }
  return "停机规则待确认";
}

function replayCountSummary(value: unknown, fallback: string, labelMode: "safe" | "readiness" = "safe") {
  const entries = Object.entries(record(value))
    .map(([key, count]) => {
      const label = labelMode === "readiness"
        ? readinessReasonLabel(safeSnapshotDisplayText(key, ""), "阻断原因待确认")
        : safeSnapshotDisplayText(key, "项待确认");
      return label ? `${label}:${countText(count)}` : "";
    })
    .filter(Boolean);
  return entries.length ? entries.slice(0, 4).join(" ") : fallback;
}

function compactJoin(values: string[]) {
  return values.filter(Boolean).join(" ");
}

function record(value: unknown): SnapshotPayload {
  return value && typeof value === "object" && !Array.isArray(value) ? value as SnapshotPayload : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown) {
  if (value === undefined || value === null) return "";
  return String(value);
}

function truthy(value: unknown) {
  return value === true || value === "true" || value === "True" || value === 1 || value === "1";
}
