import {
  text, record, array, truthy, metricText, ratioText, countText,
  isSnapshotPassStatus, safeSnapshotDisplayText, dedupeRows, compactJoin,
  RAW_SNAPSHOT_TEXT_PATTERN,
  type SnapshotPayload, type SnapshotRow,
} from "./utils";
import { readinessReasonLabel } from "@/helpers/readinessLabels";

export function checkpointComparisonSummary(payload: SnapshotPayload) {
  const latestComparison = record(payload.latest_comparison);
  const deltas = record(latestComparison.deltas);
  const keys = Object.keys(deltas)
    .map((key) => safeSnapshotDisplayText(key, "对比项待确认"))
    .filter(Boolean);
  if (!keys.length) return "";
  return `对比 ${keys.length} 项: ${keys.slice(0, 3).join(", ")}`;
}

export function robustnessRows(payload: SnapshotPayload) {
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

export function robustnessMetrics(payload: SnapshotPayload, rows: SnapshotRow[]) {
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
