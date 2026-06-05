/** Read-only pre-submit confirmation surface. */

import { useCallback, useEffect, useMemo } from "react";
import { useApi } from "@/hooks/useApi";
import type { Candidate, SubmitReadinessResponse } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

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
      callCandidates<{ candidates?: Candidate[]; items?: Candidate[] }>("/api/candidates?limit=1000"),
      callChecks<{ items?: CheckResult[] }>("/api/check_results"),
      callReadiness<SubmitReadinessResponse>("/api/submit_readiness"),
    ]);
    if (candidatesResult?.error) notify("error", candidatesResult.error);
    if (checksResult?.error) notify("error", checksResult.error);
    if (readinessResult?.error) notify("error", readinessResult.error);
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

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="提交确认"
        progress={{ phase: "submission_confirm_load", status_message: "正在加载提交前检查记录。" }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-100">提交前确认</h2>
        <p className="text-xs text-muted" role="status" aria-live="polite">
          可提交 {readyCount} · 阻断 {blockedCount}
        </p>
      </div>

      {error && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-danger">提交确认数据加载失败: {error}</p>
            <button type="button" onClick={load} className="btn-secondary text-sm">
              重试
            </button>
          </div>
        </div>
      )}

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
  const blockers = (readiness?.top_blocking_reasons || [])
    .slice(0, 4)
    .map((row) => `${row.reason} ${row.count}`)
    .join(" · ");
  const familyBlockers = (readiness?.top_family_blocking_reasons || [])
    .slice(0, 4)
    .map((row) => `${row.reason} ${row.count}`)
    .join(" · ");
  const productionGaps = (readiness?.production_gaps || [])
    .slice(0, 4)
    .map((row) => row.code || row.message)
    .filter(Boolean)
    .join(" · ");
  const nextSteps = (readiness?.required_next_steps || []).slice(0, 4).join(" · ");
  const best = readiness?.best_candidate || {};
  return (
    <section className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-3">
      <dl className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <ReadinessMetric label="Ready" value={readiness?.ready_to_submit ? "yes" : "no"} tone={readiness?.ready_to_submit ? "text-success" : "text-warning"} />
        <ReadinessMetric label="Eligible" value={formatCount(readiness?.eligible_count)} />
        <ReadinessMetric label="Official sim" value={formatCount(summary.officially_simulated)} />
        <ReadinessMetric label="Live API" value={readiness?.official_api_called ? "called" : "not called"} />
        <ReadinessMetric label="最佳 Alpha" value={best.alpha_id || "-"} mono />
      </dl>
      <div className="mt-3 space-y-1 text-xs text-muted">
        <p className="truncate" title={blockers || "none"}>Blocking: {blockers || "none"}</p>
        <p className="truncate" title={familyBlockers || "none"}>Family blockers: {familyBlockers || "none"}</p>
        <p className="truncate" title={productionGaps || "none"}>Production gaps: {productionGaps || "none"}</p>
        <p className="truncate" title={nextSteps || "none"}>Next: {nextSteps || "none"}</p>
      </div>
    </section>
  );
}

function ReadinessMetric({ label, value, tone = "text-gray-100", mono = false }: { label: string; value: string; tone?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-muted">{label}</dt>
      <dd className={`mt-0.5 truncate font-medium ${tone} ${mono ? "font-mono" : ""}`} title={value}>{value}</dd>
    </div>
  );
}

function ConfirmationTable({ title, empty, rows }: { title: string; empty: string; rows: ConfirmationRow[] }) {
  return (
    <section className="min-w-0 space-y-3">
      <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
      <div className="card min-w-0 overflow-hidden p-0">
        <div className="max-w-full overflow-auto">
          <table className="min-w-[760px] w-full text-sm" aria-label={title}>
            <thead>
              <tr className="border-b border-gray-800 text-left text-xs uppercase tracking-wider text-muted">
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
                <tr><td colSpan={6} className="p-6 text-center text-muted">{empty}</td></tr>
              ) : (
                rows.map((row) => (
                  <tr key={`${title}_${row.id}`} className="border-b border-gray-800/50">
                    <td className="p-3 font-mono text-xs text-brand-400">{row.id}</td>
                    <td className="max-w-xs truncate p-3 font-mono text-xs" title={row.expression}>{row.expression || "-"}</td>
                    <td className="p-3"><span className={`badge text-xs ${row.status === "READY" ? "badge-success" : "badge-warning"}`}>{row.status}</span></td>
                    <td className="p-3 font-mono text-xs">{row.score}</td>
                    <td className="max-w-sm truncate p-3 text-xs text-gray-300" title={row.reasons}>{row.reasons || "-"}</td>
                    <td className="p-3 font-mono text-xs text-muted">{row.checkedAt || "-"}</td>
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
      reasons: (check.failed_reasons || []).join("; "),
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
