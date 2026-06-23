/** Read-only quality-gate summary before pre-submit blocker review. */

import { useCallback, useEffect, useMemo } from "react";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { readinessNextActionLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import { useApi } from "@/hooks/useApi";
import { useGlobalData } from "@/hooks/useGlobalData";
import type { BacktestSlotsResponse, SubmitReadinessResponse } from "@/types";
import CandidateTable from "@/components/CandidateTable";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function QualityCheckPanel({ notify }: Props) {
  const { slots: slotsGlobal } = useGlobalData();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const callReadiness = readinessApi.call;

  const load = useCallback(async () => {
    const readinessResult = await callReadiness<SubmitReadinessResponse>("/api/submit_readiness");
    if (readinessResult?.error) notify("error", apiErrorMessage(readinessResult, "提交阻断复核加载失败"));
  }, [callReadiness, notify]);

  useEffect(() => { void load(); }, [load]);

  const summary = useMemo(
    () => buildQualitySummary(slotsGlobal.data, readinessApi.data),
    [slotsGlobal.data, readinessApi.data],
  );
  const loading = slotsGlobal.loading || readinessApi.loading;
  const error = slotsGlobal.error || readinessApi.error;

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
        <h2 className="text-base font-semibold text-text-primary">达标检查</h2>
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          本地通过 {summary.localValid} · 官方仿真 {summary.officiallySimulated} · 复核候选 {summary.eligible}
        </p>
      </div>

      {error && (
        <div
          className="panel"
          role="alert"
          aria-live="assertive"
          style={{ borderColor: 'var(--color-error-border)', backgroundColor: 'var(--color-error-bg)' }}
        >
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-negative">达标检查数据加载失败: {error}</p>
            <button type="button" onClick={load} className="btn btn-secondary btn-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <QualitySummaryStrip summary={summary} />

      <CandidateTable
        notify={notify}
        viewMode="passed"
        showProductionControls
        showRowActions
      />
    </div>
  );
}

interface QualitySummary {
  total: number;
  localValid: number;
  localBlocked: number;
  aboveSimulationScore: number;
  reviewReady: number;
  officiallySimulated: number;
  submitReady: number;
  eligible: number;
  openSlots: number;
  slotLimit: number;
  submitEvidenceBlocked: number;
  officialApiCalled: boolean;
  thresholdText: string;
  blockers: string;
  reviewBlockers: string;
  familyBlockers: string;
  submitBlockers: string;
  nextAction: string;
}

function QualitySummaryStrip({ summary }: { summary: QualitySummary }) {
  return (
    <section
      className="rounded-md px-3 py-3"
      style={{ border: '1px solid', borderColor: 'var(--color-border-medium)', backgroundColor: 'var(--color-surface-deep-60)' }}
    >
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <QualityMetric label="候选" value={String(summary.total)} />
        <QualityMetric label="本地通过" value={String(summary.localValid)} />
        <QualityMetric label="本地阻断" value={String(summary.localBlocked)} />
        <QualityMetric label="仿真分数" value={String(summary.aboveSimulationScore)} />
        <QualityMetric label="待官方复核" value={String(summary.reviewReady)} />
        <QualityMetric label="可用槽位" value={`${summary.openSlots}/${summary.slotLimit}`} />
        <QualityMetric label="官方仿真" value={String(summary.officiallySimulated)} />
        <QualityMetric label="阻断复核候选" value={String(summary.eligible)} />
        <QualityMetric label="提交证据缺口" value={String(summary.submitEvidenceBlocked)} />
        <QualityMetric label="官方接口" value={summary.officialApiCalled ? "已调用" : "未调用"} />
      </dl>
      <div className="mt-3 space-y-1 text-xs text-text-tertiary">
        <p className="truncate" title={summary.thresholdText}>官方门槛: {summary.thresholdText}</p>
        <p className="truncate" title={summary.reviewBlockers || "暂无"}>官方工作阻断: {summary.reviewBlockers || "暂无"}</p>
        <p className="truncate" title={summary.submitBlockers || "暂无"}>提交证据阻断: {summary.submitBlockers || "暂无"}</p>
        <p className="truncate" title={summary.familyBlockers || "暂无"}>候选族阻断: {summary.familyBlockers || "暂无"}</p>
        <p className="truncate" title={summary.nextAction}>下一步: {summary.nextAction}</p>
      </div>
    </section>
  );
}

function QualityMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-text-primary" title={value}>{value}</dd>
    </div>
  );
}

function buildQualitySummary(
  slots: BacktestSlotsResponse | null,
  readiness: SubmitReadinessResponse | null,
): QualitySummary {
  const threshold = readiness?.threshold_summary || {};
  const summaryCounts = readiness?.summary_counts || {};
  const queue = slots?.queue_summary;
  const total = queue?.candidate_count ?? queue?.returned_candidate_count ?? 0;
  const localValid = queue?.local_valid_count ?? 0;
  return {
    total,
    localValid,
    localBlocked: queue?.blocked_candidate_count ?? Math.max(0, total - localValid),
    aboveSimulationScore: queue?.above_simulation_score_count ?? 0,
    reviewReady: queue?.review_candidate_count ?? 0,
    officiallySimulated: summaryCounts.officially_simulated ?? 0,
    submitReady: summaryCounts.submission_ready ?? 0,
    eligible: readiness?.eligible_count ?? 0,
    openSlots: queue?.open_slot_count ?? Math.max(0, (slots?.slot_limit ?? 0) - (slots?.active_count ?? 0)),
    slotLimit: queue?.slot_limit ?? slots?.slot_limit ?? 0,
    submitEvidenceBlocked: queue?.submit_evidence_blocking_count ?? 0,
    officialApiCalled: Boolean(readiness?.official_api_called || queue?.official_api_called),
    thresholdText: thresholdText(threshold),
    blockers: reasonText(readiness?.top_blocking_reasons),
    reviewBlockers: reasonText(queue?.top_blocking_reasons),
    familyBlockers: reasonText(readiness?.top_family_blocking_reasons),
    submitBlockers: reasonText(queue?.top_submit_blocking_reasons),
    nextAction: nextActionText(queue?.next_action),
  };
}

function reasonText(rows: { reason: string; count: number }[] | undefined) {
  return (rows || [])
    .map((row) => `${readinessReasonLabel(row.reason)} ${row.count}`)
    .join(" · ");
}

function nextActionText(action: unknown) {
  const labels: Record<string, string> = {
    generate_candidates: "先生成候选",
    improve_or_regenerate_candidates: "优化或重新生成候选",
    trusted_environment_official_simulation_required: "在可信环境运行官方仿真",
    wait_for_open_backtest_slot: "等待官方回测槽位释放",
  };
  const key = String(action || "");
  if (!key) return "等待候选和门禁数据";
  return labels[key] || readinessNextActionLabel(key, "等待候选和门禁数据");
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
