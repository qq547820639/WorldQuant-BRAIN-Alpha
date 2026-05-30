/** Read-only data and research snapshot views. */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import ProgressFeedback from "@/components/ProgressFeedback";

export type SnapshotView =
  | "cloud"
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

const MAX_FILTER_LENGTH = 200;
const SNAPSHOT_VIEWS: Record<SnapshotView, SnapshotConfig> = {
  cloud: {
    title: "Cloud data",
    subtitle: "Cached alpha state",
    endpoint: "/api/snapshot/cloud?limit=100",
    empty: "No cached cloud alpha records",
    rows: cloudRows,
    metrics: cloudMetrics,
  },
  lifecycle: {
    title: "Lifecycle",
    subtitle: "Audit trail",
    endpoint: "/api/lifecycle",
    empty: "No lifecycle events",
    rows: lifecycleRows,
  },
  research_memory: {
    title: "Research memory",
    subtitle: "Local research summary",
    endpoint: "/api/research_memory?limit=5000&top_n=10",
    empty: "No research memory rows",
    rows: researchMemoryRows,
    metrics: researchMemoryMetrics,
  },
  research_knowledge: {
    title: "Knowledge base",
    subtitle: "Rules, findings, failures",
    endpoint: "/api/research_knowledge?limit=100&min_confidence=0",
    empty: "No knowledge records",
    rows: researchKnowledgeRows,
    metrics: researchKnowledgeMetrics,
  },
  research_observability: {
    title: "Observability",
    subtitle: "Research health",
    endpoint: "/api/research_observability?limit=5000&top_n=10&include_cloud=true",
    empty: "No observability signals",
    rows: researchObservabilityRows,
    metrics: researchObservabilityMetrics,
  },
  prompt_runs: {
    title: "Prompt runs",
    subtitle: "Prompt ledger",
    endpoint: "/api/prompt_runs?limit=100",
    empty: "No prompt run records",
    rows: promptRunRows,
  },
  sqlite_indexes: {
    title: "SQLite indexes",
    subtitle: "Cache health",
    endpoint: "/api/sqlite_indexes?top_n=10",
    empty: "No SQLite index rows",
    rows: sqliteIndexRows,
    metrics: sqliteIndexMetrics,
  },
  robustness: {
    title: "Robustness",
    subtitle: "Anti-overfit and rolling validation",
    endpoint: "/api/latest_result",
    empty: "No robustness evidence",
    rows: robustnessRows,
    metrics: robustnessMetrics,
  },
};

export default function SnapshotPanel({ notify, viewMode }: Props) {
  const api = useApi<SnapshotPayload>();
  const [filter, setFilter] = useState("");
  const config = SNAPSHOT_VIEWS[viewMode];
  const callApi = api.call;

  const load = useCallback(async () => {
    const result = await callApi<SnapshotPayload>(config.endpoint);
    if (result?.error) notify("error", result.error);
  }, [callApi, config.endpoint, notify]);

  useEffect(() => { void load(); }, [load]);

  const payload = api.data || {};
  const rows = useMemo(() => config.rows(payload), [config, payload]);
  const metrics = useMemo(() => config.metrics?.(payload, rows) || defaultMetrics(payload, rows), [config, payload, rows]);
  const normalizedFilter = filter.trim().toLowerCase();
  const filteredRows = normalizedFilter
    ? rows.filter((row) => rowText(row).includes(normalizedFilter))
    : rows;

  if (api.loading && !api.data) {
    return (
      <ProgressFeedback
        state="loading"
        title={config.title}
        progress={{ phase: "snapshot_load", status_message: `Loading ${config.title}.` }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4 animate-fade-in">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-gray-100">{config.title}</h2>
          <p className="text-xs text-muted">{config.subtitle}</p>
        </div>
        <button type="button" onClick={load} className="btn-secondary text-sm" disabled={api.loading}>
          Refresh
        </button>
      </div>

      <ProgressFeedback
        state={api.error ? "error" : api.loading ? "loading" : "idle"}
        title={config.title}
        progress={{ phase: api.loading ? "snapshot_load" : "completed", status_message: api.loading ? `Refreshing ${config.title}.` : `${config.title} snapshot loaded.` }}
        error={api.error}
        onRetry={load}
        compact={!api.loading && !api.error}
      />

      {api.error && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-danger text-sm">Failed to load {config.title}: {api.error}</p>
            <button type="button" onClick={load} className="btn-secondary text-sm" disabled={api.loading}>
              Retry
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {metrics.map((metric) => (
          <div key={metric.label} className="card min-w-0 p-3">
            <p className="text-xs text-muted">{metric.label}</p>
            <p className="mt-1 truncate text-lg font-semibold text-gray-100">{metric.value}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="text"
          aria-label={`Filter ${config.title}`}
          placeholder="Filter rows..."
          value={filter}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(event) => setFilter(sanitizeTextInput(event.target.value, MAX_FILTER_LENGTH))}
          className="w-full min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 sm:flex-1"
        />
        <p className="text-xs text-muted" role="status" aria-live="polite">
          {filteredRows.length} of {rows.length} rows
        </p>
      </div>

      <div className="card min-w-0 overflow-hidden p-0">
        <div className="max-w-full overflow-auto">
          <table className="min-w-[820px] w-full text-sm" aria-label={`${config.title} rows`}>
            <thead>
              <tr className="border-b border-gray-800 text-left text-xs text-muted uppercase tracking-wider">
                <th scope="col" className="p-3">Type</th>
                <th scope="col" className="p-3">Name</th>
                <th scope="col" className="p-3">Status</th>
                <th scope="col" className="p-3">Metric</th>
                <th scope="col" className="p-3">Detail</th>
                <th scope="col" className="p-3">Time</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-muted">{config.empty}</td></tr>
              ) : (
                filteredRows.map((row, index) => (
                  <tr key={`${row.kind}_${row.id}_${index}`} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                    <td className="p-3 text-xs text-muted">{row.kind}</td>
                    <td className="p-3 font-mono text-xs text-brand-400">{row.title || row.id || "-"}</td>
                    <td className="p-3"><span className={`badge text-xs ${statusBadge(row.status)}`}>{row.status || "-"}</span></td>
                    <td className="p-3 font-mono text-xs">{row.metric || "-"}</td>
                    <td className="p-3 text-xs text-gray-300 max-w-md truncate" title={row.detail}>{row.detail || "-"}</td>
                    <td className="p-3 font-mono text-xs text-muted">{row.timestamp || "-"}</td>
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
    { label: "Rows", value: String(rows.length) },
    { label: "Source", value: text(payload.source || "snapshot") },
    { label: "Schema", value: text(payload.schema_version || "-") },
    { label: "Status", value: payload.ok === false ? "Error" : "Ready" },
  ];
}

function cloudMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const summary = record(payload.summary);
  return [
    { label: "Returned", value: text(summary.returned_count ?? rows.length) },
    { label: "Submitted", value: text(summary.submitted_count ?? "-") },
    { label: "Passed", value: text(summary.passed_unsubmitted_count ?? "-") },
    { label: "Stale", value: truthy(summary.is_stale) ? "Yes" : "No" },
  ];
}

function researchMemoryMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  return [
    { label: "Rows", value: String(rows.length) },
    { label: "Candidates", value: text(payload.total_candidates ?? "0") },
    { label: "Lifecycle", value: text(payload.total_lifecycle_records ?? "0") },
    { label: "Checks", value: text(payload.total_check_records ?? "0") },
  ];
}

function researchKnowledgeMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const counts = record(payload.counts);
  return [
    { label: "Rows", value: String(rows.length) },
    { label: "Rules", value: text(counts.rules ?? "0") },
    { label: "Findings", value: text(counts.findings ?? "0") },
    { label: "Failures", value: text(counts.failures ?? "0") },
  ];
}

function researchObservabilityMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const health = record(payload.health);
  const errors = record(payload.errors);
  return [
    { label: "Rows", value: String(rows.length) },
    { label: "Risk", value: text(health.risk_level || "unknown") },
    { label: "Errors", value: text(errors.total ?? "0") },
    { label: "Blocks", value: text(array(health.blocking_flags).length) },
  ];
}

function sqliteIndexMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
  const expression = record(payload.expression_index);
  const recordIndex = record(payload.record_index);
  return [
    { label: "Rows", value: String(rows.length) },
    { label: "Expressions", value: text(expression.total_expression_records ?? "0") },
    { label: "Duplicates", value: text(expression.duplicate_expression_count ?? "0") },
    { label: "Records", value: text(recordIndex.row_count ?? "0") },
  ];
}

function robustnessMetrics(_payload: SnapshotPayload, rows: SnapshotRow[]) {
  const antiRows = rows.filter((row) => row.kind === "anti_overfit");
  const rollingRows = rows.filter((row) => row.kind === "rolling_validation");
  return [
    { label: "Rows", value: String(rows.length) },
    { label: "Anti-overfit", value: String(antiRows.length) },
    { label: "Rolling", value: String(rollingRows.length) },
    { label: "Warnings", value: String(rows.filter((row) => row.status && row.status !== "pass" && row.status !== "passed").length) },
  ];
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
  return latestCandidateRows(payload).flatMap((candidate, index) => {
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

function rowId(row: SnapshotPayload, fallback: string) {
  return text(row.alpha_id || row.official_alpha_id || row.simulation_id || row.id || row.knowledge_id || row.entry_id || row.run_id || row.prompt_digest || row.expression_fingerprint || fallback);
}

function rowText(row: SnapshotRow) {
  return [row.id, row.kind, row.title, row.status, row.metric, row.detail, row.timestamp].join(" ").toLowerCase();
}

function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

function statusBadge(status: string) {
  const normalized = status.toLowerCase();
  if (["ready", "pass", "passed", "true", "submitted", "production"].some((item) => normalized.includes(item))) return "badge-success";
  if (["fail", "false", "missing", "blocked", "error", "rejected"].some((item) => normalized.includes(item))) return "badge-danger";
  if (["warn", "stale", "caution", "unknown"].some((item) => normalized.includes(item))) return "badge-warning";
  return "badge-neutral";
}

function metricText(label: string, value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  if (typeof value === "number") return `${label}:${Number.isInteger(value) ? value : value.toFixed(3)}`;
  const parsed = Number(value);
  if (Number.isFinite(parsed) && String(value).trim() !== "") return `${label}:${Number.isInteger(parsed) ? parsed : parsed.toFixed(3)}`;
  return `${label}:${text(value)}`;
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
