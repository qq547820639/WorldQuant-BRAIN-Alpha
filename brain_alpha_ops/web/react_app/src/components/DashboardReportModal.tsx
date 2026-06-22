import React from "react";
import { type TrendData } from "@/components/TrendPanel";
import type { JobStatus, CloudAlphaWithMetrics, ResearchMemorySummary } from "@/types";

interface CloudSummaryData {
  count?: number;
  submitted_count?: number;
  passed_unsubmitted_count?: number;
  is_stale: boolean;
  loaded_at?: string;
  age_seconds?: number;
}

interface ReportInput {
  trendCandidates: TrendData[];
  trendSubmissions: TrendData[];
  cloudSummary: CloudSummaryData;
  memory: ResearchMemorySummary | null;
  status: JobStatus | null;
  cloudPreviewRows: CloudAlphaWithMetrics[];
}

function cloudAlphaId(row: CloudAlphaWithMetrics) {
  return String(row.alpha_id || row.id || "-");
}

function cloudAlphaPassFail(row: CloudAlphaWithMetrics) {
  const metrics = row.metrics && typeof row.metrics === "object" ? row.metrics : {};
  return String(row.pass_fail || metrics.pass_fail || "");
}

function cloudAlphaMetric(row: CloudAlphaWithMetrics, key: string) {
  const metrics = row.metrics && typeof row.metrics === "object" ? row.metrics : {};
  const value = (row as Record<string, unknown>)[key] ?? (metrics as Record<string, unknown>)[key];
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function formatMetric(value: number | undefined) {
  return value == null ? "--" : value.toFixed(2);
}

export function generateReportMarkdown(input: ReportInput): string {
  const { trendCandidates, trendSubmissions, cloudSummary, memory, status, cloudPreviewRows } = input;
  const now = new Date();
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - now.getDay() + 1);
  const weekLabel = `${weekStart.getFullYear()}-${String(weekStart.getMonth() + 1).padStart(2, "0")}-${String(weekStart.getDate()).padStart(2, "0")}`;

  const weekCandidatesTotal = trendCandidates
    .filter((d) => d.date >= weekLabel)
    .reduce((sum, d) => sum + d.value, 0);
  const weekSubmissionsTotal = trendSubmissions
    .filter((d) => d.date >= weekLabel)
    .reduce((sum, d) => sum + d.value, 0);

  const totalCount = cloudSummary.count ?? 0;
  const submittedCount = cloudSummary.submitted_count ?? 0;
  const passRate = totalCount > 0 ? ((submittedCount / totalCount) * 100).toFixed(1) : "0.0";

  const topAlphas = cloudPreviewRows.slice(0, 5);

  const lines: string[] = [];
  lines.push(`# BRAIN Alpha 工作日报`);
  lines.push("");
  lines.push(`**日期**: ${now.toLocaleDateString("zh-CN")}`);
  lines.push(`**报告周期**: ${weekLabel} ~ ${now.toLocaleDateString("zh-CN")}`);
  lines.push("");
  lines.push("## 核心指标");
  lines.push("");
  lines.push(`| 指标 | 数值 |`);
  lines.push(`|------|------|`);
  lines.push(`| 本周候选生成数 | ${weekCandidatesTotal} |`);
  lines.push(`| 本周提交数 | ${weekSubmissionsTotal} |`);
  lines.push(`| 云端 Alpha 总数 | ${totalCount} |`);
  lines.push(`| 已提交数 | ${submittedCount} |`);
  lines.push(`| 通过率 | ${passRate}% |`);
  lines.push(`| 当前候选池 | ${memory?.total_candidates ?? status?.progress?.candidates_generated ?? 0} |`);
  lines.push(`| 回测完成数 | ${status?.progress?.backtests_completed ?? 0} |`);
  lines.push(`| 回测待处理 | ${status?.progress?.backtests_pending ?? 0} |`);
  lines.push("");

  if (topAlphas.length > 0) {
    lines.push("## Top 候选摘要");
    lines.push("");
    lines.push("| Alpha ID | 状态 | Sharpe | Fitness | Turnover |");
    lines.push("|----------|------|--------|---------|----------|");
    for (const a of topAlphas) {
      const id = cloudAlphaId(a);
      const pf = cloudAlphaPassFail(a);
      const sharpe = formatMetric(cloudAlphaMetric(a, "sharpe"));
      const fitness = formatMetric(cloudAlphaMetric(a, "fitness"));
      const turnover = formatMetric(cloudAlphaMetric(a, "turnover"));
      lines.push(`| ${id} | ${pf} | ${sharpe} | ${fitness} | ${turnover} |`);
    }
    lines.push("");
  }

  if (memory?.families && memory.families.length > 0) {
    lines.push("## 热门家族 Top 3");
    lines.push("");
    for (const f of memory.families.slice(0, 3)) {
      lines.push(`- **${f.name}**: n=${f.count}, 成功率=${(f.success_rate ?? 0).toFixed(2)}`);
    }
    lines.push("");
  }

  lines.push("---");
  lines.push(`*由 BRAIN-Alpha 本地控制台自动生成 · ${now.toISOString().slice(0, 19).replace("T", " ")}*`);

  return lines.join("\n");
}

interface DashboardReportModalProps {
  show: boolean;
  onClose: () => void;
  markdown: string;
}

export function DashboardReportModal({ show, onClose, markdown }: DashboardReportModalProps) {
  if (!show) return null;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      return true;
    } catch {
      const ta = document.createElement("textarea");
      ta.value = markdown;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      return true;
    }
  };

  return (
    <div
      className="modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="工作日报"
    >
      <div className="flex flex-col rounded-lg shadow-lg border border-modal max-w-[640px] w-[calc(100%-32px)] max-h-[80vh]" style={{ backgroundColor: "var(--color-modal-bg)" }}>
        <div className="flex justify-between items-center px-5 py-4 border-b border-modal-border">
          <h2 className="text-base font-semibold text-text-primary">📋 工作日报</h2>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            aria-label="关闭"
          >
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 font-mono text-[13px] leading-relaxed whitespace-pre-wrap border-y border-divider" style={{ color: "var(--color-report-text)", backgroundColor: "var(--color-report-bg)" }}>
          {markdown}
        </div>
        <ReportFooter onClose={onClose} onCopy={handleCopy} markdown={markdown} />
      </div>
    </div>
  );
}

function ReportFooter({ onClose, onCopy, markdown }: { onClose: () => void; onCopy: () => Promise<boolean>; markdown: string }) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    const success = await onCopy();
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex justify-end gap-2 px-5 py-3">
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={onClose}
      >
        关闭
      </button>
      <button
        type="button"
        className="btn btn-primary btn-sm"
        onClick={handleCopy}
      >
        {copied ? "✓ 已复制" : "复制为 Markdown"}
      </button>
    </div>
  );
}
