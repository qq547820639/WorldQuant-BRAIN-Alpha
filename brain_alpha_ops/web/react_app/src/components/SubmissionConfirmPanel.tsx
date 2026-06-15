/** Read-only pre-submit confirmation surface. */

import { useCallback, useEffect, useMemo } from "react";
import { apiErrorMessage } from "@/helpers/errorExperience";
import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import { useApi } from "@/hooks/useApi";
import type { Candidate, SubmitReadinessResponse } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
import StatusFlowDiagram from "@/components/StatusFlowDiagram";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

interface CheckResult {
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  status?: string;
  passed?: boolean;
  submittable?: boolean;
  is_stale?: boolean;
  score?: number;
  failed_reasons?: string[];
  checked_at?: string;
}

interface ConfirmationRow {
  id: string;
  expression: string;
  status: string;
  score: string;
  reasons: string;
  checkedAt: string;
}

export default function SubmissionConfirmPanel({ notify }: Props) {
  const candidatesApi = useApi<{ candidates?: Candidate[]; items?: Candidate[] }>();
  const checksApi = useApi<{ items?: CheckResult[] }>();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const callCandidates = candidatesApi.call;
  const callChecks = checksApi.call;
  const callReadiness = readinessApi.call;

  const load = useCallback(async () => {
    const [candidatesResult, checksResult, readinessResult] = await Promise.all([
      callCandidates<{ candidates?: Candidate[]; items?: Candidate[] }>("/api/candidates"),
      callChecks<{ items?: CheckResult[] }>("/api/check_results"),
      callReadiness<SubmitReadinessResponse>("/api/submit_readiness"),
    ]);
    if (candidatesResult?.error) notify("error", apiErrorMessage(candidatesResult, "候选数据加载失败"));
    if (checksResult?.error) notify("error", apiErrorMessage(checksResult, "检查结果加载失败"));
    if (readinessResult?.error) notify("error", apiErrorMessage(readinessResult, "提交阻断复核加载失败"));
  }, [callCandidates, callChecks, callReadiness, notify]);

  useEffect(() => { void load(); }, [load]);

  const candidates = candidatesApi.data?.candidates || candidatesApi.data?.items || [];
  const checks = checksApi.data?.items || [];
  const readiness = readinessApi.data;
  const rows = useMemo(() => buildRows(candidates, checks), [candidates, checks]);
  const readyRows = rows.filter((row) => row.status === "READY");
  const blockedRows = rows.filter((row) => row.status !== "READY");
  const readyCount = readiness?.eligible_count ?? readyRows.length;
  const readinessCandidateCount = readiness?.job_family_candidate_count ?? readiness?.candidate_count ?? rows.length;
  const blockedCount = readiness ? Math.max(0, readinessCandidateCount - readyCount) : blockedRows.length;
  const loading = (candidatesApi.loading || checksApi.loading || readinessApi.loading)
    && !candidatesApi.data
    && !checksApi.data
    && !readinessApi.data;
      const error = candidatesApi.error || checksApi.error || readinessApi.error;

  // Flow stages for StatusFlowDiagram
  const flowStages = useMemo(() => {
      // P2-5 [C15]: deduplicate checks that are both passed AND submittable
  const checked = new Set(checks.filter((c) => c.passed || c.submittable).map(c => c.alpha_id || c.official_alpha_id || c.simulation_id || JSON.stringify(c))).size;
    const ready = readyCount;
    return [
      { label: "批量检查", count: checked, status: checked > 0 ? "complete" as const : "active" as const },
      { label: "阻断复核", count: ready, status: ready > 0 ? "complete" as const : checked > 0 ? "active" as const : "pending" as const },
      { label: "可提交", count: readiness?.ready_to_submit ? ready : 0, status: readiness?.ready_to_submit ? "complete" as const : blockedCount > 0 ? "blocked" as const : "pending" as const },
    ];
  }, [checks, readyCount, blockedCount, readiness?.ready_to_submit]);

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="提交前阻断复核"
        progress={{ phase: "submission_confirm_load", status_message: "正在加载提交前检查记录。" }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-text-primary">提交前阻断复核</h2>
        <p className="text-xs text-text-tertiary" role="status" aria-live="polite">
          复核候选 {readyCount} · 阻断 {blockedCount}
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-[oklch(0.48_0.08_22/0.30)] bg-[oklch(0.48_0.06_22/0.08)] p-4" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-negative">提交前阻断复核数据加载失败: {error}</p>
            <button type="button" onClick={load} className="btn btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

      <StatusFlowDiagram stages={flowStages} />

      <ReadinessSummary readiness={readiness} />

      <ConfirmationTable
        title="预检查通过"
        empty="暂无通过预提交检查的 Alpha"
        rows={readyRows}
      />

      <ConfirmationTable
        title="阻断与待处理"
        empty="暂无阻断记录"
        rows={blockedRows}
      />
    </div>
  );
}

function ReadinessSummary({ readiness }: { readiness: SubmitReadinessResponse | null }) {
  const summary = readiness?.summary_counts || {};
  const allBlockers = readiness?.top_blocking_reasons || [];
  const allFamilyBlockers = readiness?.top_family_blocking_reasons || [];
  const allProductionGaps = readiness?.production_gaps || [];
  const allNextSteps = readiness?.required_next_steps || [];
  const blockers = allBlockers
    .map((row) => `${readinessReasonLabel(row.reason)} ${row.count}`)
    .join(" · ");
  const familyBlockers = allFamilyBlockers
    .map((row) => `${readinessReasonLabel(row.reason)} ${row.count}`)
    .join(" · ");
  const productionGaps = allProductionGaps
    .map((row) => readinessProductionGapLabel(row))
    .filter(Boolean)
    .join(" · ");
  const nextSteps = allNextSteps.map((step) => readinessNextActionLabel(step)).join(" · ");
  const stopRule = readiness?.authoritative_stop_rule || readiness?.validation_command || readiness?.source || "check_live_submit_readiness.py";
  const submitBoundary = readiness?.real_submit_performed ? "真实提交已发生" : "未执行真实提交";
  const claimPolicy = readiness?.submit_ready_claim_allowed ? "可按验证结果继续人工复核" : "不可声明提交就绪";
  const best = readiness?.best_candidate || {};
  return (
    <section className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] px-3 py-3">
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <ReadinessMetric label="阻断复核" value={readiness?.ready_to_submit ? "通过" : "未通过"} tone={readiness?.ready_to_submit ? "text-positive" : "text-warning"} />
        <ReadinessMetric label="复核候选" value={formatCount(readiness?.eligible_count)} />
        <ReadinessMetric label="官方仿真" value={formatCount(summary.officially_simulated)} />
        <ReadinessMetric label="官方接口" value={readiness?.official_api_called ? "已调用" : "未调用"} />
        <ReadinessMetric label="最佳 Alpha" value={best.alpha_id || "-"} mono />
        <ReadinessMetric label="真实提交" value={submitBoundary} tone={readiness?.real_submit_performed ? "text-negative" : "text-positive"} />
      </dl>
      <div className="mt-3 space-y-1 text-xs text-text-tertiary">
        <p className="break-words" title={stopRule}>判定来源: {stopRule}</p>
        <p className="break-words" title={claimPolicy}>提交就绪声明: {claimPolicy}</p>
        <p className="break-words" title={blockers || "无"}>{countLabel("当前阻断", allBlockers.length)}: {blockers || "无"}</p>
        <p className="break-words" title={familyBlockers || "无"}>{countLabel("候选族阻断", allFamilyBlockers.length)}: {familyBlockers || "无"}</p>
        <p className="break-words" title={productionGaps || "无"}>{countLabel("生产缺口", allProductionGaps.length)}: {productionGaps || "无"}</p>
        <p className="break-words" title={nextSteps || "无"}>{countLabel("下一步", allNextSteps.length)}: {nextSteps || "无"}</p>
      </div>
    </section>
  );
}

function ReadinessMetric({ label, value, tone = "text-text-primary", mono = false }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-text-tertiary">{label}</dt>
      <dd className={`mt-0.5 truncate font-medium ${tone} ${mono ? "font-mono-value" : ""}`} title={value}>{value}</dd>
    </div>
  );
}

function countLabel(label: string, total: number) {
  return total > 0 ? `${label}（共 ${total}）` : label;
}

function ConfirmationTable({ title, empty, rows }: { title: string; empty: string; rows: ConfirmationRow[] }) {
  return (
    <section className="min-w-0 space-y-3">
      <h3 className="text-sm font-semibold text-text-secondary">{title}</h3>
      <div className="space-y-3 md:hidden" aria-label={`${title} 移动端卡片`}>
        {rows.length === 0 ? (
          <div className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-4 text-center text-sm text-text-tertiary">{empty}</div>
        ) : (
          rows.map((row) => (
            <article key={`${title}_mobile_${row.id}`} className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-4 text-sm">
              <div className="flex min-w-0 items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="break-all font-mono-value text-xs text-accent">{row.id}</p>
                  <p className="mt-1 break-words font-mono-value text-xs text-text-secondary">{row.expression || "-"}</p>
                </div>
                <span className={`badge shrink-0 text-xs ${row.status === "READY" ? "badge-positive" : "badge-warning"}`}>
                  {readinessStatusLabel(row.status)}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <div>
                  <dt className="text-text-tertiary">得分</dt>
                  <dd className="mt-1 font-mono-value text-text-primary">{row.score}</dd>
                </div>
                <div>
                  <dt className="text-text-tertiary">检查时间</dt>
                  <dd className="mt-1 break-words font-mono-value text-text-primary">{row.checkedAt || "-"}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-text-tertiary">原因</dt>
                  <dd className="mt-1 break-words text-text-secondary">{row.reasons || "-"}</dd>
                </div>
              </dl>
            </article>
          ))
        )}
      </div>
      <div className="hidden min-w-0 overflow-hidden md:block rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)]">
        <div className="max-w-full overflow-auto">
          <table className="min-w-[760px] w-full text-sm" aria-label={title}>
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs uppercase tracking-wider text-text-tertiary">
                <th scope="col" className="p-3">Alpha ID</th>
                <th scope="col" className="p-3">表达式</th>
                <th scope="col" className="p-3">状态</th>
                <th scope="col" className="p-3">得分</th>
                <th scope="col" className="p-3">原因</th>
                <th scope="col" className="p-3">检查时间</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={6} className="p-6 text-center text-text-tertiary">{empty}</td></tr>
              ) : (
                rows.map((row) => (
                  <tr key={`${title}_${row.id}`} className="border-b border-border-subtle">
                    <td className="p-3 font-mono-value text-xs text-accent">{row.id}</td>
                    <td className="max-w-xs truncate p-3 font-mono-value text-xs" title={row.expression}>{row.expression || "-"}</td>
                    <td className="p-3"><span className={`badge text-xs ${row.status === "READY" ? "badge-positive" : "badge-warning"}`}>{readinessStatusLabel(row.status)}</span></td>
                    <td className="p-3 font-mono-value text-xs">{row.score}</td>
                    <td className="max-w-sm break-words p-3 text-xs text-text-secondary" title={row.reasons}>{row.reasons || "-"}</td>
                    <td className="p-3 font-mono-value text-xs text-text-tertiary">{row.checkedAt || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

function readinessStatusLabel(status: string) {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "READY") return "可复核";
  if (normalized === "BLOCKED") return "阻断";
  if (normalized === "FAILED") return "失败";
  if (normalized === "PENDING") return "待检查";
  return normalized ? "状态待确认" : "-";
}

function buildRows(candidates: Candidate[], checks: CheckResult[]) {
  const candidatesById = new Map<string, Candidate>();
  for (const candidate of candidates) {
    for (const id of candidateIds(candidate)) {
      candidatesById.set(id, candidate);
    }
  }
  return checks.map((check, index): ConfirmationRow => {
    const id = candidateIds(check)[0] || `check_${index + 1}`;
    const candidate = candidatesById.get(id);
    const ready = check.is_stale !== true && Boolean(check.submittable ?? check.passed);
    return {
      id,
      expression: candidate?.expression || "",
      status: ready ? "READY" : String(check.status || "BLOCKED").toUpperCase(),
      score: check.score == null ? "-" : Number(check.score).toFixed(2),
      reasons: (check.failed_reasons || []).map((reason) => readinessReasonLabel(reason)).join("; "),
      checkedAt: String(check.checked_at || ""),
    };
  });
}

function candidateIds(row: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id"> | CheckResult) {
  return [row.alpha_id, row.official_alpha_id, row.simulation_id]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return String(Math.max(0, Math.trunc(number)));
}

function formatNumber(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(2);
}
