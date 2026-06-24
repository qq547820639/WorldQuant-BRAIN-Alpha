/** Sub-components for CandidateTable. */

import { useCallback, useState, memo } from "react";
import type { AlphaLifecycleHistoryResponse, AlphaLifecycleTrace, Candidate } from "@/types";
import { isStarred, toggleStar } from "@/utils/starredCandidates";
import {
  candidateBlockerText,
  candidateIdentity,
  candidateOutputDetail,
  candidateOutputSummary,
  candidateQualityBadge,
  candidateStatus,
  candidateText,
  CandidateCheckResult,
  lifecycleNextActionLabel,
  lifecycleStatusBadgeClass,
  lifecycleStatusLabel,
  lifecycleTraceTitle,
  numericResultField,
  officialEvidenceText,
  safeLifecycleNote,
  shortLifecycleTraceId,
  statusBadgeClass,
} from "./CandidateTableUtils";
import type { LifecycleMetric as LifecycleMetricType, LifecycleMetricProps, LifecycleReplayPanelProps } from "./CandidateTableUtils";

type SortKey = "score" | "status" | "created";

export const SortHeader = memo(function SortHeader({ column, label, sortKey, sortAsc, onSort }: {
  column: SortKey; label: string; sortKey: SortKey; sortAsc: boolean; onSort: (column: SortKey) => void;
}) {
  const active = sortKey === column;
  return (
    <th scope="col" className={active ? "is-sorted" : "is-sortable"} style={{ width: "7rem" }}
      aria-sort={active ? (sortAsc ? "ascending" : "descending") : "none"}>
      <button type="button" className="flex items-center gap-1" onClick={() => onSort(column)}>
        {label}
        <span className="text-accent" aria-hidden="true">{active ? (sortAsc ? "\u2191" : "\u2193") : ""}</span>
      </button>
    </th>
  );
});

export const QualitySummaryItem = memo(function QualitySummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi-card">
      <p className="kpi-card-label">{label}</p>
      <p className="font-mono-value text-base font-medium text-text-primary">{value}</p>
    </div>
  );
});

export const LifecycleReplayPanel = memo(function LifecycleReplayPanel({
  error,
  filterActive,
  history,
  loading,
  visibleTraces,
}: {
  error: string | null;
  filterActive: boolean;
  history: AlphaLifecycleHistoryResponse | null;
  loading: boolean;
  visibleTraces: AlphaLifecycleTrace[];
}) {
  const summary: NonNullable<AlphaLifecycleHistoryResponse["summary"]> = history?.summary || {};
  const recordCount = numericResultField(summary.record_count ?? history?.count);
  const alphaCount = numericResultField(summary.alpha_count);
  const traceRows = visibleTraces.slice(0, 4);
  return (
    <section className="panel mb-4" aria-label="生命周期回放">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <span>生命周期回放</span>
          <span className="badge badge-neutral">本地只读</span>
          <span className="badge badge-neutral">非提交</span>
          {filterActive && <span className="badge badge-info">已过滤</span>}
        </div>
      </div>
      <div className="panel-body-padded">
        <div
          className="grid gap-3"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}
        >
          <LifecycleMetric label="记录" value={loading && !history ? "..." : String(recordCount)} />
          <LifecycleMetric label="Alpha" value={String(alphaCount)} />
          <LifecycleMetric label="通过" value={String(numericResultField(summary.passed_count))} tone="text-positive" />
          <LifecycleMetric label="阻断/失败" value={`${numericResultField(summary.blocked_count)}/${numericResultField(summary.failed_count)}`} tone="text-negative" />
          <LifecycleMetric label="已提交" value={String(numericResultField(summary.submitted_count))} />
        </div>

        {error ? (
          <p className="mt-4 rounded-md border border-negative/40 bg-negative/10 px-3 py-2 text-xs text-negative" role="alert">
            {error}
          </p>
        ) : traceRows.length > 0 ? (
          <div className="mt-4 grid gap-2">
            {traceRows.map((trace) => (
              <div
                key={trace.trace_key || trace.expression_digest || trace.latest_event_at}
                className="rounded-md border border-border-subtle bg-surface-2 px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-mono-value text-xs text-accent" title={lifecycleTraceTitle(trace)}>
                      {shortLifecycleTraceId(trace)}
                    </p>
                    <p className="mt-1 text-xs text-text-tertiary">
                      {candidateText(trace.latest_stage) || "--"} · {candidateText(trace.latest_status) || "--"}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`badge ${lifecycleStatusBadgeClass(trace)}`}>{lifecycleStatusLabel(trace)}</span>
                    <span className="badge badge-neutral">{lifecycleNextActionLabel(trace.next_action)}</span>
                    <span className="font-mono-value text-xs text-text-tertiary">{numericResultField(trace.event_count)} events</span>
                  </div>
                </div>
                {safeLifecycleNote(trace.last_note) && (
                  <p className="mt-2 truncate text-xs text-text-secondary" title={safeLifecycleNote(trace.last_note)}>
                    {safeLifecycleNote(trace.last_note)}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-xs text-text-tertiary">
            {loading ? "正在读取生命周期历史。" : "暂无匹配的生命周期记录。"}
          </p>
        )}
      </div>
    </section>
  );
});

export const LifecycleMetric = memo(function LifecycleMetric({ label, tone = "text-text-primary", value }: { label: string; tone?: string; value: string }) {
  return (
    <div className="min-w-0 border-l border-border-subtle pl-3">
      <p className="text-2xs font-semibold uppercase tracking-wider text-text-tertiary">{label}</p>
      <p className={`font-mono-value text-base font-medium ${tone}`}>{value}</p>
    </div>
  );
});

export const CandidateMobileCard = memo(function CandidateMobileCard({
  candidate,
  checkResults,
  canShowRowActions,
  canSimulate,
  canCheck,
  workflowBusy,
  simulationBusy,
  checkingAlphaId,
  checkBusy,
  onScore,
  onSimulate,
  onCheck,
  cardRef,
  style,
}: {
  candidate: Candidate;
  checkResults: Map<string, CandidateCheckResult>;
  canShowRowActions: boolean;
  canSimulate: boolean;
  canCheck: boolean;
  workflowBusy: boolean;
  simulationBusy: boolean;
  checkingAlphaId: string | null;
  checkBusy: boolean;
  onScore?: (candidate: Candidate) => void;
  onSimulate?: (candidate: Candidate) => void;
  onCheck?: (candidate: Candidate) => void;
  cardRef?: React.Ref<HTMLDivElement>;
  style?: React.CSSProperties;
}) {
  const quality = candidateQualityBadge(candidate);
  const evidence = officialEvidenceText(candidate, checkResults);
  const identity = candidateIdentity(candidate);
  const hasActions = canShowRowActions || canSimulate || canCheck;
  const [starred, setStarred] = useState(() => isStarred(identity));
  const handleToggleStar = useCallback(() => {
    const newState = toggleStar(identity);
    setStarred(newState);
  }, [identity]);
  return (
    <div ref={cardRef} className="panel" style={{ padding: "12px", ...style }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button
              type="button"
              onClick={handleToggleStar}
              aria-label={starred ? "取消收藏" : "收藏"}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 16, lineHeight: 1, padding: 0,
                opacity: starred ? 1 : 0.3, transition: "opacity 0.15s",
              }}
            >
              ⭐
            </button>
            <p className="text-xs font-mono text-info">{candidateIdentity(candidate).slice(0, 24) || "--"}</p>
          </div>
          <p className="text-xs font-mono text-text-secondary mt-2 break-words">{candidateText(candidate.expression) || "--"}</p>
        </div>
        <span className={`badge shrink-0 ${quality.tone}`}>{quality.label}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12, fontSize: "0.75rem" }}>
        <div><span className="text-text-tertiary">评分</span><p className="font-mono-value text-text-primary">{candidate.scorecard?.total_score?.toFixed(1) ?? "--"}</p></div>
        <div><span className="text-text-tertiary">状态</span><p className="mt-1"><span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>{candidateStatus(candidate) || "--"}</span></p></div>
        <div style={{ gridColumn: "span 2" }}><span className="text-text-tertiary">阻断原因</span><p className="text-text-secondary break-words">{candidateBlockerText(candidate)}</p></div>
        <div style={{ gridColumn: "span 2" }}><span className="text-text-tertiary">官方证据</span><p className="text-text-secondary break-words">{evidence}</p></div>
        <div style={{ gridColumn: "span 2" }}><span className="text-text-tertiary">输出</span><p className="text-text-primary">{candidateOutputSummary(candidate)}</p><p className="text-text-tertiary">{candidateOutputDetail(candidate)}</p></div>
      </div>
      {hasActions && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
          {canShowRowActions && (
            <button type="button" className="btn btn-ghost btn-sm" style={{ width: "100%" }}
              aria-label={`评分 ${candidateIdentity(candidate)}`} disabled={workflowBusy} onClick={() => onScore?.(candidate)}>
              评分
            </button>
          )}
          {canCheck && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: "100%" }}
              aria-label={`单行补查 ${identity}`}
              disabled={checkBusy}
              onClick={() => onCheck?.(candidate)}
            >
              {checkingAlphaId === identity ? "检查中..." : "单行补查"}
            </button>
          )}
          {canSimulate && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: "100%" }}
              aria-label={`单行补模拟 ${identity}`}
              disabled={simulationBusy}
              onClick={() => onSimulate?.(candidate)}
            >
              单行补模拟
            </button>
          )}
        </div>
      )}
    </div>
  );
});

export const EmptyState = memo(function EmptyState({ filter, showProductionControls }: { filter: boolean; showProductionControls: boolean }) {
  if (filter) {
    return (
      <div style={{ padding: "2rem 0", color: "var(--color-text-muted)", fontSize: 13 }}>
        <p>没有匹配的候选</p>
        <p style={{ marginTop: 4, fontSize: 12 }}>
          尝试调整筛选条件，或清除筛选查看全部候选。
        </p>
      </div>
    );
  }

  if (showProductionControls) {
    return (
      <div style={{ padding: "1.5rem 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 48, height: 48, borderRadius: "50%",
          background: "var(--color-search-ring-bg)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--color-icon-warning)" strokeWidth="1.5" strokeLinecap="round">
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
          </svg>
        </div>
        <div>
          <p style={{ color: "var(--color-text-light)", fontSize: 14, fontWeight: 500 }}>暂无候选记录</p>
          <p style={{ color: "var(--color-text-muted)", fontSize: 12, marginTop: 4, lineHeight: 1.5, maxWidth: 320 }}>
            候选 Alpha 通过顶部「自动推进候选池」启动生产搜索、预筛与本地排序；官方验证队列和质量检查单独推进。
            全流程保持非提交边界，提交仍需人工确认。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "1.5rem 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <p style={{ color: "var(--color-text-muted)", fontSize: 13 }}>暂无候选记录</p>
      <p style={{ color: "var(--color-text-extra-dim)", fontSize: 12, lineHeight: 1.5, maxWidth: 280 }}>
        请先运行非提交验证产生候选，或从候选管理页面选择一个候选进入评分。
      </p>
    </div>
  );
});
