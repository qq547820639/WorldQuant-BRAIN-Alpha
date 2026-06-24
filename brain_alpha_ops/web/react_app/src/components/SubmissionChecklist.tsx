import { memo } from "react";
import { readinessReasonLabel } from "@/helpers/readinessLabels";
import type { Candidate } from "@/types";

export interface CheckResult {
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

export interface ConfirmationRow {
  id: string;
  expression: string;
  status: string;
  score: string;
  reasons: string;
  checkedAt: string;
}

export function readinessStatusLabel(status: string) {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "READY") return "可复核";
  if (normalized === "BLOCKED") return "阻断";
  if (normalized === "FAILED") return "失败";
  if (normalized === "PENDING") return "待检查";
  return normalized ? "状态待确认" : "-";
}

export function buildRows(candidates: Candidate[], checks: CheckResult[]) {
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

function countLabel(label: string, total: number) {
  return total > 0 ? `${label}（共 ${total}）` : label;
}

export function formatCount(value: unknown) {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return String(Math.max(0, Math.trunc(number)));
}

function formatNumber(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(2);
}

export const ConfirmationTable = memo(function ConfirmationTable({ title, empty, rows }: { title: string; empty: string; rows: ConfirmationRow[] }) {
  return (
    <section className="min-w-0 space-y-3">
      <h3 className="text-sm font-semibold text-text-secondary">{title}</h3>
      <div className="space-y-3 md:hidden" aria-label={`${title} 移动端卡片`}>
        {rows.length === 0 ? (
          <div className="rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] p-4 text-center text-sm text-text-tertiary">{empty}</div>
        ) : (
          rows.map((row) => (
            <article key={`${title}_mobile_${row.id}`} className="rounded-md border border-border-subtle bg-[var(--color-surface-elevated)] p-4 text-sm">
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
      <div className="hidden min-w-0 overflow-hidden md:block rounded-md border border-border-subtle bg-[var(--color-surface-deep)]">
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
});
