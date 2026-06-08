/**
 * Candidate management table for the state-card UI.
 *
 * The table keeps the compact card-first workflow, but preserves the production
 * semantics users need before official validation or pre-submit blocker review checks.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { requestJobCancel } from "@/api/jobCancel";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import type { BrainCredentials, Candidate, SSEEvent, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

const MIN_GENERATE_COUNT = 1;
const MAX_GENERATE_COUNT = 100;
const MAX_FILTER_LENGTH = 200;
const CANDIDATE_FETCH_LIMIT = 1000;
const PAGE_SIZE = 20;

type SortKey = "score" | "status" | "created";
export type CandidateQueueView =
  | "candidates"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed";

type CandidateCheckResult = {
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
};

type CandidateListMeta = {
  returned: number;
  total: number;
  limit: number;
};

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onScore?: (candidate: Candidate) => void;
  showProductionControls?: boolean;
  showRowActions?: boolean;
  credentials?: BrainCredentials;
  viewMode?: CandidateQueueView;
}

export default function CandidateTable({
  credentials,
  notify,
  onScore,
  showProductionControls = true,
  showRowActions = false,
  viewMode = "candidates",
}: Props) {
  const api = useApi<{ candidates?: Candidate[]; items?: Candidate[]; returned_count?: number; total?: number; total_count?: number; limit?: number }>();
  const checkResultsApi = useApi<{ items?: CandidateCheckResult[] }>();
  const callApi = api.call;
  const callCheckResultsApi = checkResultsApi.call;
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidateMeta, setCandidateMeta] = useState<CandidateListMeta>({ returned: 0, total: 0, limit: CANDIDATE_FETCH_LIMIT });
  const [checkResults, setCheckResults] = useState<Map<string, CandidateCheckResult>>(new Map());

  const [filter, setFilter] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);

  const [generateCount, setGenerateCount] = useState(5);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskState, setTaskState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [taskProgress, setTaskProgress] = useState<UnifiedProgress | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  // BRAIN simulation state
  const [simJobId, setSimJobId] = useState<string | null>(null);
  const [simState, setSimState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [simProgress, setSimProgress] = useState<UnifiedProgress | null>(null);
  const [simError, setSimError] = useState<string | null>(null);

  const loadCandidates = useCallback(async () => {
    const [result, checkResultsResult] = await Promise.all([
      callApi(`/api/candidates?limit=${CANDIDATE_FETCH_LIMIT}`),
      callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results"),
    ]);
    if (result?.ok) {
      const nextRows = result.candidates || result.items || [];
      setCandidates((current) => nextRows.length || current.length === 0 ? nextRows : current);
      setCandidateMeta({
        returned: Number(result.returned_count ?? nextRows.length),
        total: Number(result.total ?? result.total_count ?? nextRows.length),
        limit: Number(result.limit ?? CANDIDATE_FETCH_LIMIT),
      });
    } else if (result?.error) {
      notify("error", result.error);
    }
    if (checkResultsResult?.ok) {
      setCheckResults(indexCheckResults(checkResultsResult.items || []));
    } else if (checkResultsResult?.error) {
      notify("error", checkResultsResult.error);
    }
  }, [callApi, callCheckResultsApi, notify]);

  const refreshCheckResults = useCallback(async () => {
    if (viewMode !== "submittable") return;
    const result = await callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results");
    if (result?.ok) {
      setCheckResults(indexCheckResults(result.items || []));
    } else if (result?.error) {
      notify("error", result.error);
    }
  }, [callCheckResultsApi, notify, viewMode]);

  useEffect(() => {
    void loadCandidates();
  }, [loadCandidates]);

  useEffect(() => {
    void refreshCheckResults();
  }, [refreshCheckResults]);

  const handleTaskEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setTaskProgress(progress as UnifiedProgress);

    if (event.type === "error" || event.ok === false || event.status === "failed") {
      setTaskState("error");
      setTaskError(event.error || event.status_message || "候选生成失败");
      notify("error", event.error || "候选生成失败");
      return;
    }

    if (event.type === "complete") {
      setTaskState("success");
      const result = event.result as { candidates?: Candidate[]; candidates_preview?: Candidate[]; count?: number } | undefined;
      const rows = result?.candidates || result?.candidates_preview || [];
      if (rows.length) setCandidates(rows);
      void loadCandidates();
      notify("success", `候选生成完成${result?.count ? `: ${result.count}` : ""}`);
      setTaskId(null);
      return;
    }

    setTaskState("progress");
  }, [loadCandidates, notify]);

  const handleTaskStreamExhausted = useCallback(() => {
    if (!taskId) return;
    const cancelledTaskId = taskId;
    const message = "候选生成进度暂时不可确认，系统已安全停止本次生成。请刷新候选列表后再重试。";
    setTaskState("error");
    setTaskError(message);
    setTaskId(null);
    setTaskProgress((current) => ({
      ...(current || {}),
      phase: current?.phase || "candidate_generation",
      status_message: message,
      percent_complete: 100,
    }));
    void requestJobCancel({ jobId: cancelledTaskId, reason: "sse_exhausted", message });
    notify("warning", message);
    void loadCandidates();
  }, [loadCandidates, notify, taskId]);

  const taskStream = useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}` : null, {
    onEvent: handleTaskEvent,
    onExhausted: handleTaskStreamExhausted,
  });

  const generateCandidates = useCallback(async () => {
    setTaskState("loading");
    setTaskError(null);
    setTaskProgress({ phase: "candidate_generation", status_message: "正在启动候选生成。" });

    const result = await callApi<{ job_id: string; task_id?: string }>("/api/generate_candidates", {
      method: "POST",
      body: JSON.stringify({ ...buildCredentialOverrides(), count: clampGenerateCount(generateCount) }),
    });

    const nextTaskId = String(result?.task_id || result?.job_id || "");

    if (result?.ok && nextTaskId) {
      setTaskId(nextTaskId);
      setTaskState("progress");
      notify("info", "候选生成已启动，可在本页查看进度。");
    } else {
      setTaskState("error");
      setTaskError(result?.error || "启动候选生成失败");
      notify("error", result?.error || "启动候选生成失败");
    }
  }, [callApi, generateCount, notify]);

  // BRAIN simulation handler
  const startSimulation = useCallback(async () => {
    setSimState("loading");
    setSimError(null);
    setSimProgress({ phase: "simulation_start", status_message: "正在提交BRAIN模拟请求。" });

    const result = await callApi<{ job_id: string; task_id?: string }>("/api/candidates/simulate", {
      method: "POST",
      body: JSON.stringify(buildCredentialOverrides()),
    });

    const nextJobId = String(result?.task_id || result?.job_id || "");

    if (result?.ok && nextJobId) {
      setSimJobId(nextJobId);
      setSimState("progress");
      notify("info", "BRAIN模拟已启动，可在本页查看进度。");
    } else {
      setSimState("error");
      setSimError(result?.error || "启动BRAIN模拟失败");
      notify("error", result?.error || "启动BRAIN模拟失败");
    }
  }, [callApi, notify]);

  // SSE stream for simulation progress
  const handleSimEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setSimProgress(progress as UnifiedProgress);

    if (event.type === "error" || event.ok === false || event.status === "failed") {
      setSimState("error");
      setSimError(event.error || event.status_message || "BRAIN模拟失败");
      notify("error", event.error || "BRAIN模拟失败");
      setSimJobId(null);
      return;
    }

    if (event.type === "complete" || event.status === "completed") {
      setSimState("success");
      const result = event.result as { completed?: number; failed?: number; results?: unknown[] } | undefined;
      notify("success", `BRAIN模拟完成${result?.completed ? `: ${result.completed}个成功` : ""}`);
      setSimJobId(null);
      void loadCandidates();
      return;
    }

    setSimState("progress");
  }, [loadCandidates, notify]);


  const buildCredentialOverrides = useCallback((): Record<string, string> => {
    const overrides: Record<string, string> = {};
    const username = credentials?.username.trim() || "";
    const password = credentials?.password || "";
    if (username) overrides.username = username;
    if (password) overrides.password = password;
    return overrides;
  }, [credentials]);
  const handleSimStreamExhausted = useCallback(() => {
    if (!simJobId) return;
    setSimState("error");
    setSimError("模拟进度暂时不可确认，请刷新候选列表后查看结果。");
    setSimJobId(null);
    void loadCandidates();
  }, [loadCandidates, simJobId]);

  useSSE(simJobId ? `/sse?job_id=${encodeURIComponent(simJobId)}` : null, {
    onEvent: handleSimEvent,
    onExhausted: handleSimStreamExhausted,
  });

  const queueCandidates = useMemo(
    () => candidates.filter((candidate) => candidateMatchesQueueView(candidate, viewMode, checkResults)),
    [candidates, checkResults, viewMode],
  );

  const sortedCandidates = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    const filtered = normalizedFilter
      ? queueCandidates.filter((c) =>
          candidateText(c.expression).toLowerCase().includes(normalizedFilter) ||
          candidateText(c.family).toLowerCase().includes(normalizedFilter) ||
          candidateIdentity(c).toLowerCase().includes(normalizedFilter) ||
          candidateQualitySearchText(c).toLowerCase().includes(normalizedFilter)
        )
      : queueCandidates;

    return [...filtered].sort((a, b) => {
      let va: number;
      let vb: number;
      switch (sortKey) {
        case "score":
          va = a.scorecard?.total_score ?? 0;
          vb = b.scorecard?.total_score ?? 0;
          break;
        case "status":
          return candidateStatus(a).localeCompare(candidateStatus(b)) * (sortAsc ? 1 : -1);
        case "created":
          va = candidateCreatedAt(a);
          vb = candidateCreatedAt(b);
          break;
        default:
          return 0;
      }
      return sortAsc ? va - vb : vb - va;
    });
  }, [filter, queueCandidates, sortAsc, sortKey]);

  const qualitySummary = useMemo(() => summarizeCandidateQuality(queueCandidates), [queueCandidates]);
  const totalPages = Math.max(1, Math.ceil(sortedCandidates.length / PAGE_SIZE));
  const paginatedCandidates = useMemo(() => {
    const startIndex = (currentPage - 1) * PAGE_SIZE;
    return sortedCandidates.slice(startIndex, startIndex + PAGE_SIZE);
  }, [currentPage, sortedCandidates]);
  const canShowRowActions = showRowActions && Boolean(onScore);

  useEffect(() => {
    setCurrentPage(1);
  }, [filter, sortKey, sortAsc, viewMode]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const handleGenerateCountChange = (value: string) => {
    setGenerateCount(clampGenerateCount(value));
  };

  const handleFilterChange = (value: string) => {
    setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH));
  };

  const loading = api.loading && candidates.length === 0;
  const loadError = api.error;
  const visibleStart = sortedCandidates.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const visibleEnd = Math.min(currentPage * PAGE_SIZE, sortedCandidates.length);
  const title = viewMode === "candidates" ? "候选管理" : `${queueViewLabel(viewMode)}候选`;
  const remoteTruncated = candidateMeta.total > candidateMeta.returned;

  if (loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="候选管理"
        progress={{ phase: "candidate_load", status_message: "正在加载候选数据。" }}
      />
    );
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-xl font-medium text-text-primary mb-1">{title}</h1>
      <p className="text-sm text-text-tertiary mb-4" role="status" aria-live="polite">
        显示 {sortedCandidates.length} / {queueCandidates.length} 个候选
        {candidateMeta.total > 0 && ` · 已返回 ${candidateMeta.returned}/${candidateMeta.total}`}
        {viewMode !== "candidates" && ` · ${queueViewLabel(viewMode)}`}
        {filter && " · 已过滤"}
      </p>

      {showProductionControls && (
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <label className="flex items-center gap-2 text-sm font-medium text-text-secondary">
            数量
            <input
              type="number"
              min={MIN_GENERATE_COUNT}
              max={MAX_GENERATE_COUNT}
              value={generateCount}
              onChange={(event) => handleGenerateCountChange(event.target.value)}
              className="form-input w-20"
            />
          </label>
          <button
            type="button"
            onClick={generateCandidates}
            disabled={taskState === "loading" || taskState === "progress"}
            className="btn btn-primary btn-sm"
          >
            {taskState === "loading" || taskState === "progress" ? "生成中..." : "生成候选"}
          </button>
          <button
            type="button"
            onClick={startSimulation}
            disabled={simState === "loading" || simState === "progress"}
            className="btn btn-secondary btn-sm"
            title="提交符合分数阈值的候选到BRAIN平台进行官方回测模拟"
          >
            {simState === "loading" || simState === "progress" ? "模拟中..." : "提交BRAIN模拟"}
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
        <QualitySummaryItem label="达标" value={String(qualitySummary.ready)} />
        <QualitySummaryItem label="本地通过" value={String(qualitySummary.localValid)} />
        <QualitySummaryItem label="阻断" value={String(qualitySummary.blocked)} />
        <QualitySummaryItem label="输出模式" value={qualitySummary.outputMode} />
        <QualitySummaryItem label="Dataset" value={qualitySummary.dataset} />
      </div>

      {showProductionControls && taskState !== "idle" && (
        <ProgressFeedback
          state={taskStream.exhausted && taskState === "progress" ? "error" : taskState}
          title="候选生成"
          progress={taskProgress}
          error={taskError || (taskStream.exhausted && taskState === "progress" ? "候选生成状态不明确，系统已安全停止本次生成。" : null)}
          onRetry={generateCandidates}
          compact={taskState === "success"}
        />
      )}

      {showProductionControls && simState !== "idle" && (
        <ProgressFeedback
          state={simState}
          title="BRAIN官方模拟"
          progress={simProgress}
          error={simError}
          onRetry={startSimulation}
          compact={simState === "success"}
        />
      )}

      {remoteTruncated && (
        <div className="mb-4 px-3 py-2 text-xs rounded-md bg-warning-subtle text-warning" role="status" aria-live="polite">
          当前只加载了前 {candidateMeta.returned} 条候选，服务端报告总量为 {candidateMeta.total} 条；请使用过滤或刷新查看最新状态，避免把当前列表误认为全集。
        </div>
      )}

      {loadError && (
        <div className="panel mb-4" style={{ borderColor: "oklch(0.48 0.08 22 / 0.30)", background: "oklch(0.48 0.06 22 / 0.08)" }} role="alert" aria-live="assertive">
          <div className="panel-body-padded" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <p className="text-sm text-negative">加载候选失败: {loadError}</p>
            <button type="button" onClick={loadCandidates} className="btn btn-secondary btn-sm">重试</button>
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-3 mb-4">
        <input
          type="text"
          aria-label="过滤候选"
          placeholder="按表达式、家族、ID、质量原因搜索..."
          value={filter}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(event) => handleFilterChange(event.target.value)}
          className="form-input flex-1"
        />
        <button type="button" onClick={loadCandidates} disabled={api.loading} className="btn btn-secondary btn-sm">
          {api.loading ? "刷新中..." : "刷新"}
        </button>
      </div>

      <div className="panel">
        {/* Mobile card list */}
        <div className="panel-body md:hidden">
          {paginatedCandidates.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", fontSize: 13, color: "oklch(0.52 0.006 45)" }}>
              {filter ? "没有匹配的候选" : "暂无候选记录"}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {paginatedCandidates.map((candidate, index) => (
                <CandidateMobileCard
                  key={`${candidateIdentity(candidate)}_mobile_${index}`}
                  candidate={candidate}
                  checkResults={checkResults}
                  canShowRowActions={canShowRowActions}
                  onScore={onScore}
                />
              ))}
            </div>
          )}
        </div>

        {/* Desktop table */}
        <div className="md:block" style={{ maxWidth: "100%", overflow: "auto" }}>
          <table className="data-table card-view" style={{ minWidth: 980 }} aria-label="候选结果">
            <thead>
              <tr>
                <th style={{ width: "8rem" }}>ID</th>
                <th style={{ width: "20rem" }}>表达式</th>
                <SortHeader column="score" label="评分" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <SortHeader column="status" label="状态" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <th style={{ width: "7rem" }}>质量</th>
                <th style={{ width: "14rem" }}>阻断原因</th>
                <th style={{ width: "18rem" }}>输出</th>
                <th style={{ width: "16rem" }}>官方证据</th>
                {canShowRowActions && <th style={{ width: "6rem" }}>操作</th>}
              </tr>
            </thead>
            <tbody>
              {paginatedCandidates.length === 0 ? (
                <tr>
                  <td colSpan={canShowRowActions ? 9 : 8} style={{ padding: "2rem", textAlign: "center", color: "oklch(0.52 0.006 45)" }}>
                    {filter ? "没有匹配的候选" : "暂无候选记录"}
                  </td>
                </tr>
              ) : (
                paginatedCandidates.map((candidate, index) => {
                  const quality = candidateQualityBadge(candidate);
                  const evidence = officialEvidenceText(candidate, checkResults);
                  return (
                    <tr key={`${candidateIdentity(candidate)}_${index}`}>
                      <td className="id">{candidateIdentity(candidate).slice(0, 16) || "--"}</td>
                      <td>
                        <div className="font-mono text-xs text-text-secondary break-words" title={candidateText(candidate.expression)}>
                          {candidateText(candidate.expression) || "--"}
                        </div>
                        <div className="text-2xs text-text-tertiary mt-1">{candidateText(candidate.family)}</div>
                      </td>
                      <td className="num" style={{ fontWeight: 500, color: "oklch(0.92 0.003 45)" }}>
                        {candidate.scorecard?.total_score?.toFixed(1) ?? "--"}
                      </td>
                      <td>
                        <span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>
                          {candidateStatus(candidate) || "--"}
                        </span>
                      </td>
                      <td><span className={`badge ${quality.tone}`} title={quality.title}>{quality.label}</span></td>
                      <td className="text-xs text-text-secondary">{candidateBlockerText(candidate)}</td>
                      <td className="text-xs">
                        <div className="font-medium text-text-primary">{candidateOutputSummary(candidate)}</div>
                        <div className="text-text-tertiary mt-1">{candidateOutputDetail(candidate)}</div>
                      </td>
                      <td className="text-xs">
                        <div className="text-text-secondary">{evidence}</div>
                        <div className="text-text-tertiary mt-1">{candidateText(candidate.simulation_id) || "simulation:--"}</div>
                      </td>
                      {canShowRowActions && (
                        <td>
                          <button type="button" className="btn btn-ghost btn-sm"
                            aria-label={`评分 ${candidateIdentity(candidate)}`}
                            onClick={() => onScore?.(candidate)}>
                            评分
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border-subtle px-3.5 py-3">
          <div className="text-sm text-text-tertiary" role="status" aria-live="polite">
            显示 {visibleStart}-{visibleEnd}，共 {sortedCandidates.length} 条
          </div>
          {sortedCandidates.length > PAGE_SIZE && (
            <div className="flex items-center gap-2">
              <button type="button" onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1} className="btn btn-ghost btn-sm">上一页</button>
              <span className="text-sm text-text-secondary">{currentPage} / {totalPages}</span>
              <button type="button" onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="btn btn-ghost btn-sm">下一页</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SortHeader({ column, label, sortKey, sortAsc, onSort }: {
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
}

function QualitySummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi-card">
      <p className="kpi-card-label">{label}</p>
      <p className="font-mono-value text-base font-medium text-text-primary">{value}</p>
    </div>
  );
}

function CandidateMobileCard({ candidate, checkResults, canShowRowActions, onScore }: {
  candidate: Candidate; checkResults: Map<string, CandidateCheckResult>;
  canShowRowActions: boolean; onScore?: (candidate: Candidate) => void;
}) {
  const quality = candidateQualityBadge(candidate);
  const evidence = officialEvidenceText(candidate, checkResults);
  return (
    <div className="panel" style={{ padding: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="text-xs font-mono text-info">{candidateIdentity(candidate).slice(0, 24) || "--"}</p>
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
      {canShowRowActions && (
        <button type="button" className="btn btn-ghost btn-sm" style={{ width: "100%", marginTop: 12 }}
          aria-label={`评分 ${candidateIdentity(candidate)}`} onClick={() => onScore?.(candidate)}>
          评分
        </button>
      )}
    </div>
  );
}

function clampGenerateCount(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return MIN_GENERATE_COUNT;
  return Math.min(Math.max(Math.trunc(parsed), MIN_GENERATE_COUNT), MAX_GENERATE_COUNT);
}

function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

function indexCheckResults(rows: CandidateCheckResult[]) {
  const index = new Map<string, CandidateCheckResult>();
  for (const row of rows) {
    for (const id of candidateIds(row)) index.set(id, row);
  }
  return index;
}

function checkResultForCandidate(candidate: Candidate, checkResults: Map<string, CandidateCheckResult>) {
  for (const id of candidateIds(candidate)) {
    const result = checkResults.get(id);
    if (result) return result;
  }
  return undefined;
}

function candidateMatchesQueueView(
  candidate: Candidate,
  viewMode: CandidateQueueView,
  checkResults: Map<string, CandidateCheckResult>,
) {
  if (viewMode === "candidates") return true;
  const status = candidateStatus(candidate);
  const stage = candidateStage(candidate);
  const result = checkResultForCandidate(candidate, checkResults);
  if (viewMode === "pending_backtest") return status === "pending_backtest";
  if (viewMode === "running_backtest") return status === "running_backtest" || status === "running";
  if (viewMode === "backtest_rework") return status === "backtest_rework" || status === "failed_backtest" || status === "rejected";
  if (viewMode === "passed") return status === "submission_ready" || candidate.quality_diagnosis?.submission_ready === true || candidate.gate?.passed === true;
  if (viewMode === "submittable") return status !== "submitted" && result?.is_stale !== true && Boolean(result?.submittable ?? result?.passed ?? candidate.quality_diagnosis?.submission_ready);
  if (viewMode === "submitted") return status === "submitted" || stage === "submitted";
  return status === "failed" || status === "rejected" || status === "blocked";
}

function queueViewLabel(viewMode: CandidateQueueView) {
  const labels: Record<CandidateQueueView, string> = {
    candidates: "全部候选",
    pending_backtest: "等待回测",
    running_backtest: "回测中",
    backtest_rework: "需返工",
    passed: "已达标",
    submittable: "复核预检",
    submitted: "已提交",
    failed: "失败/阻断",
  };
  return labels[viewMode];
}

function candidateIdentity(candidate: Candidate) {
  return candidateIds(candidate)[0] || "";
}

function candidateIds(candidate: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id"> | CandidateCheckResult) {
  return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

function candidateStatus(candidate: Candidate) {
  const normalized = candidateText(candidate.lifecycle_status || candidate.quality_diagnosis?.status || candidate.gate?.status);
  return normalized.toLowerCase();
}

function candidateStage(candidate: Candidate) {
  const submission = record(candidate.submission);
  return candidateText(submission.stage || submission.status || candidate.lifecycle_status).toLowerCase();
}

function candidateText(value: unknown) {
  return String(value || "");
}

function candidateCreatedAt(candidate: Candidate) {
  return new Date(candidate.created_at || candidate.updated_at || 0).getTime();
}

function candidateQualitySearchText(candidate: Candidate) {
  return [
    candidateBlockerText(candidate),
    candidateOutputSummary(candidate),
    candidateOutputDetail(candidate),
    candidate.official_alpha_id,
    candidate.simulation_id,
    candidate.dataset_id,
  ].filter(Boolean).join(" ");
}

function candidateQualityBadge(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (diagnosis.qualified || diagnosis.submission_ready) {
    return { label: "达标", tone: "badge-positive", title: "符合提交前质量复核条件" };
  }
  if (candidateLocalValid(candidate)) {
    return { label: "本地通过", tone: "badge-warning", title: "本地质量通过，仍需官方证据" };
  }
  if (candidateHasBlockingQuality(candidate)) {
    return { label: "阻断", tone: "badge-negative", title: candidateBlockerText(candidate) };
  }
  return { label: "未验证", tone: "badge-neutral", title: "缺少质量诊断" };
}

function candidateBlockerText(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  const primary = record(diagnosis.primary_reason);
  const primaryText = candidateText(primary.message || primary.code || primary.category);
  if (primaryText) return primaryText;
  if ((diagnosis.blocking_reasons || []).length) return (diagnosis.blocking_reasons || []).join("; ");
  if ((candidate.local_quality?.reasons || []).length) return candidate.local_quality?.reasons?.join("; ") || "";
  if ((candidate.gate?.failed_reasons || []).length) return candidate.gate?.failed_reasons?.join("; ") || "";
  if (candidate.local_quality?.passed === false) return "local_quality_failed";
  if (!candidate.quality_diagnosis) return "missing_quality_diagnosis";
  return "-";
}

function candidateLocalValid(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  if (typeof diagnosis.local_candidate_valid === "boolean") {
    return diagnosis.local_candidate_valid;
  }
  return candidate.local_quality?.passed === true;
}

function candidateHasBlockingQuality(candidate: Candidate) {
  const diagnosis = candidate.quality_diagnosis || {};
  return Boolean(
    diagnosis.primary_reason ||
    (diagnosis.blocking_reasons || []).length ||
    (candidate.local_quality?.reasons || []).length ||
    candidate.local_quality?.passed === false ||
    (candidate.gate?.failed_reasons || []).length
  );
}

function candidateOutputSummary(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  if (config.local_only === true) return "本地输出";
  if (config.official_api_called === true) return "官方证据";
  if (config.allow_submit === false) return "禁止提交";
  return config.alpha_type || candidate.decision_band || "-";
}

function candidateOutputDetail(candidate: Candidate) {
  const config = candidate.alpha_output_config || {};
  const settings = record(config.settings);
  const dataset = config.dataset_id || candidate.dataset_id || settings.dataset;
  const alphaType = config.alpha_type || settings.type;
  const official = config.official_api_called === true ? "official_called" : "official_not_called";
  return [dataset ? `dataset:${dataset}` : "", alphaType ? `type:${alphaType}` : "", official].filter(Boolean).join(" · ");
}

function officialEvidenceText(candidate: Candidate, checkResults: Map<string, CandidateCheckResult>) {
  const result = checkResultForCandidate(candidate, checkResults);
  if (result) {
    const status = result.status || (result.submittable ? "submittable" : result.passed ? "passed" : "blocked");
    const stale = result.is_stale ? " · stale" : "";
    return `${candidateText(result.official_alpha_id || candidate.official_alpha_id || "official:-")} · ${status}${stale}`;
  }
  return candidateText(candidate.official_alpha_id || "official:-");
}

function summarizeCandidateQuality(candidates: Candidate[]) {
  const ready = candidates.filter((candidate) => candidate.quality_diagnosis?.submission_ready || candidate.gate?.passed).length;
  const localValid = candidates.filter(candidateLocalValid).length;
  const blocked = candidates.filter(candidateHasBlockingQuality).length;
  const outputModes = candidates.map(candidateOutputSummary).filter((value) => value && value !== "-");
  const datasets = candidates.map((candidate) => candidate.alpha_output_config?.dataset_id || candidate.dataset_id).filter(Boolean);
  return {
    ready,
    localValid,
    blocked,
    outputMode: mostCommon(outputModes) || "-",
    dataset: mostCommon(datasets) || "-",
  };
}

function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("submitted") || normalized.includes("completed")) return "badge-positive";
  if (normalized.includes("failed") || normalized.includes("blocked") || normalized.includes("rejected")) return "badge-negative";
  if (normalized.includes("validat") || normalized.includes("simulat") || normalized.includes("running")) return "badge-warning";
  return "badge-neutral";
}

function mostCommon(values: unknown[]) {
  const counts = new Map<string, number>();
  for (const value of values) {
    const text = candidateText(value);
    if (!text) continue;
    counts.set(text, (counts.get(text) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || "";
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
