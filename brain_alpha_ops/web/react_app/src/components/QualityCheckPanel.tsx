/** Read-only quality-gate summary before submit confirmation. */

import { useCallback, useEffect, useMemo } from "react";
import { useApi } from "@/hooks/useApi";
import type { BacktestSlotsResponse, Candidate, SubmitReadinessResponse } from "@/types";
import CandidateTable from "@/components/CandidateTable";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function QualityCheckPanel({ notify }: Props) {
  const candidatesApi = useApi<{ candidates?: Candidate[]; items?: Candidate[]; total?: number }>();
  const slotsApi = useApi<BacktestSlotsResponse>();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const callCandidates = candidatesApi.call;
  const callSlots = slotsApi.call;
  const callReadiness = readinessApi.call;

  const load = useCallback(async () => {
    const [candidatesResult, slotsResult, readinessResult] = await Promise.all([
      callCandidates<{ candidates?: Candidate[]; items?: Candidate[]; total?: number }>("/api/candidates?limit=1000"),
      callSlots<BacktestSlotsResponse>("/api/backtest_slots"),
      callReadiness<SubmitReadinessResponse>("/api/submit_readiness"),
    ]);
    if (candidatesResult?.error) notify("error", candidatesResult.error);
    if (slotsResult?.error) notify("error", slotsResult.error);
    if (readinessResult?.error) notify("error", readinessResult.error);
  }, [callCandidates, callSlots, callReadiness, notify]);

  useEffect(() => { void load(); }, [load]);

  const candidates = candidatesApi.data?.candidates || candidatesApi.data?.items || [];
  const summary = useMemo(
    () => buildQualitySummary(candidates, slotsApi.data, readinessApi.data),
    [candidates, slotsApi.data, readinessApi.data],
  );
  const loading = (candidatesApi.loading || slotsApi.loading || readinessApi.loading)
    && !candidatesApi.data
    && !slotsApi.data
    && !readinessApi.data;
  const error = candidatesApi.error || slotsApi.error || readinessApi.error;

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="达标检查"
        progress={{ phase: "quality_check_load", status_message: "正在加载质量门禁快照。" }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-100">达标检查</h2>
        <p className="text-xs text-muted" role="status" aria-live="polite">
          本地通过 {summary.localValid} · 官方仿真 {summary.officiallySimulated} · 可提交 {summary.eligible}
        </p>
      </div>

      {error && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-danger">达标检查数据加载失败: {error}</p>
            <button type="button" onClick={load} className="btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <QualitySummaryStrip summary={summary} />

      <CandidateTable
        notify={notify}
        viewMode="passed"
        showProductionControls={false}
        showRowActions={false}
      />
    </div>
  );
}

interface QualitySummary {
  total: number;
  localValid: number;
  localBlocked: number;
  reviewReady: number;
  officiallySimulated: number;
  submitReady: number;
  eligible: number;
  officialApiCalled: boolean;
  thresholdText: string;
  blockers: string;
  familyBlockers: string;
}

function QualitySummaryStrip({ summary }: { summary: QualitySummary }) {
  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-3">
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <QualityMetric label="Candidates" value={String(summary.total)} />
        <QualityMetric label="Local valid" value={String(summary.localValid)} />
        <QualityMetric label="Review ready" value={String(summary.reviewReady)} />
        <QualityMetric label="Official sim" value={String(summary.officiallySimulated)} />
        <QualityMetric label="Eligible" value={String(summary.eligible)} />
        <QualityMetric label="Live API" value={summary.officialApiCalled ? "called" : "not called"} />
      </dl>
      <div className="mt-3 space-y-1 text-xs text-muted">
        <p className="truncate" title={summary.thresholdText}>Thresholds: {summary.thresholdText}</p>
        <p className="truncate" title={summary.blockers || "none"}>Blocking: {summary.blockers || "none"}</p>
        <p className="truncate" title={summary.familyBlockers || "none"}>Family blockers: {summary.familyBlockers || "none"}</p>
      </div>
    </section>
  );
}

function QualityMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-gray-100" title={value}>{value}</dd>
    </div>
  );
}

function buildQualitySummary(
  candidates: Candidate[],
  slots: BacktestSlotsResponse | null,
  readiness: SubmitReadinessResponse | null,
): QualitySummary {
  const localValid = candidates.filter(isLocalValidCandidate).length;
  const threshold = readiness?.threshold_summary || {};
  const summaryCounts = readiness?.summary_counts || {};
  return {
    total: candidates.length,
    localValid,
    localBlocked: Math.max(0, candidates.length - localValid),
    reviewReady: slots?.queue_summary?.review_candidate_count ?? 0,
    officiallySimulated: summaryCounts.officially_simulated ?? 0,
    submitReady: summaryCounts.submission_ready ?? 0,
    eligible: readiness?.eligible_count ?? 0,
    officialApiCalled: Boolean(readiness?.official_api_called || slots?.queue_summary?.official_api_called),
    thresholdText: thresholdText(threshold),
    blockers: reasonText(readiness?.top_blocking_reasons),
    familyBlockers: reasonText(readiness?.top_family_blocking_reasons),
  };
}

function isLocalValidCandidate(candidate: Candidate) {
  if (candidate.quality_diagnosis?.local_candidate_valid === true) return true;
  return candidate.local_quality?.passed === true;
}

function reasonText(rows: { reason: string; count: number }[] | undefined) {
  return (rows || [])
    .slice(0, 4)
    .map((row) => `${row.reason} ${row.count}`)
    .join(" · ");
}

function thresholdText(thresholds: Record<string, unknown>) {
  const sharpe = valueText(thresholds.min_sharpe);
  const fitness = valueText(thresholds.min_fitness);
  const turnover = valueText(thresholds.platform_max_turnover);
  const correlation = valueText(thresholds.max_self_correlation);
  return `夏普 ${sharpe} · 适应度 ${fitness} · 换手率 <= ${turnover} · 自相关 <= ${correlation}`;
}

function valueText(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return Number.isInteger(number) ? String(number) : number.toFixed(2);
}
