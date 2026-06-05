/**
 * Candidate management table for the state-card UI.
 *
 * The table keeps the compact card-first workflow, but preserves the production
 * semantics users need before official validation or submit readiness checks.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import type { Candidate, SSEEvent, UnifiedProgress } from "@/types";
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
  viewMode?: CandidateQueueView;
}

export default function CandidateTable({
  notify,
  onScore,
  showProductionControls = true,
  showRowActions = false,
  viewMode = "candidates",
}: Props) {
  const api = useApi<{ candidates: Candidate[] }>();
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

  const loadCandidates = useCallback(async () => {
    const [result, checkResultsResult] = await Promise.all([
      callApi(`/api/candidates?limit=${CANDIDATE_FETCH_LIMIT}`),
      callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results"),
    ]);
    if (result?.ok) {
      const data = result as unknown as {
        candidates?: Candidate[];
        items?: Candidate[];
        returned_count?: number;
        total?: number;
        total_count?: number;
        limit?: number;
      };
      const nextRows = data.candidates || data.items || [];
      setCandidates((current) => nextRows.length || current.length === 0 ? nextRows : current);
      setCandidateMeta({
        returned: Number(data.returned_count ?? nextRows.length),
        total: Number(data.total ?? data.total_count ?? nextRows.length),
        limit: Number(data.limit ?? CANDIDATE_FETCH_LIMIT),
      });
    } else if (result?.error) {
      notify("error", result.error);
    }
    if (checkResultsResult?.ok) {
      const data = checkResultsResult as unknown as { items?: CandidateCheckResult[] };
      setCheckResults(indexCheckResults(data.items || []));
    } else if (checkResultsResult?.error) {
      notify("error", checkResultsResult.error);
    }
  }, [callApi, callCheckResultsApi, notify]);

  const refreshCheckResults = useCallback(async () => {
    if (viewMode !== "submittable") return;
    const result = await callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results");
    if (result?.ok) {
      const data = result as unknown as { items?: CandidateCheckResult[] };
      setCheckResults(indexCheckResults(data.items || []));
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
    const message = "实时进度流已断开，请刷新候选状态确认任务结果。";
    setTaskProgress((current) => ({
      ...(current || {}),
      phase: current?.phase || "candidate_generation",
      status_message: message,
    }));
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
      body: JSON.stringify({ count: clampGenerateCount(generateCount) }),
    });

    const nextTaskId = String(
      (result as unknown as { task_id?: string; job_id?: string } | null)?.task_id ||
      (result as unknown as { job_id?: string } | null)?.job_id ||
      ""
    );

    if (result?.ok && nextTaskId) {
      setTaskId(nextTaskId);
      setTaskState("progress");
      notify("info", `候选生成已启动: ${nextTaskId}`);
    } else {
      setTaskState("error");
      setTaskError(result?.error || "启动候选生成失败");
      notify("error", result?.error || "启动候选生成失败");
    }
  }, [callApi, generateCount, notify]);

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
    <div className="min-w-0 space-y-4 animate-fade-in">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-xl font-bold tracking-tight text-slate-950">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-slate-600" role="status" aria-live="polite">
            显示 {sortedCandidates.length} / {queueCandidates.length} 个候选
            {candidateMeta.total > 0 && ` · 已返回 ${candidateMeta.returned}/${candidateMeta.total}`}
            {viewMode !== "candidates" && ` · ${queueViewLabel(viewMode)}`}
            {filter && " · 已过滤"}
          </p>
        </div>

        {showProductionControls && (
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
              数量
              <input
                type="number"
                min={MIN_GENERATE_COUNT}
                max={MAX_GENERATE_COUNT}
                value={generateCount}
                onChange={(event) => handleGenerateCountChange(event.target.value)}
                className="w-20 input text-sm"
              />
            </label>
            <button
              type="button"
              onClick={generateCandidates}
              disabled={taskState === "loading" || taskState === "progress"}
              className="btn-primary"
            >
              {taskState === "loading" || taskState === "progress" ? "生成中..." : "生成候选"}
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-5">
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
          error={taskError || (taskStream.exhausted && taskState === "progress" ? "实时进度流已断开，候选状态可能需要手动刷新。" : null)}
          onRetry={generateCandidates}
          compact={taskState === "success"}
        />
      )}

      {remoteTruncated && (
        <div className="rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-warning" role="status" aria-live="polite">
          当前只加载了前 {candidateMeta.returned} 条候选，服务端报告总量为 {candidateMeta.total} 条；请使用过滤或刷新查看最新状态，避免把当前列表误认为全集。
        </div>
      )}

      {loadError && (
        <div className="p-4 rounded-xl border border-danger/30 bg-danger/5" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-danger">加载候选失败: {loadError}</p>
            <button type="button" onClick={loadCandidates} className="btn-secondary text-sm" aria-label="刷新候选">
              重试
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <input
          type="text"
          aria-label="过滤候选"
          placeholder="按表达式、家族、ID、质量原因搜索..."
          value={filter}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(event) => handleFilterChange(event.target.value)}
          className="w-full min-w-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder-slate-400 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/30 sm:flex-1"
        />
        <button
          type="button"
          onClick={loadCandidates}
          disabled={api.loading}
          className="btn-secondary"
          aria-label="刷新候选"
        >
          {api.loading ? "刷新中..." : "刷新"}
        </button>
      </div>

      <div className="card min-w-0 overflow-hidden p-0">
        <div className="space-y-3 p-3 md:hidden" aria-label="候选结果移动列表">
          {paginatedCandidates.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
              {filter ? "没有匹配的候选" : "暂无候选记录"}
            </div>
          ) : (
            paginatedCandidates.map((candidate, index) => (
              <CandidateMobileCard
                key={`${candidateIdentity(candidate)}_mobile_${index}`}
                candidate={candidate}
                checkResults={checkResults}
                canShowRowActions={canShowRowActions}
                onScore={onScore}
              />
            ))
          )}
        </div>

        <div className="hidden max-w-full overflow-auto md:block">
          <table className="min-w-[980px] w-full text-sm" aria-label="候选结果">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                <th scope="col" className="w-[8rem] p-3 font-medium">ID</th>
                <th scope="col" className="w-[20rem] p-3 font-medium">表达式</th>
                <SortHeader column="score" label="评分" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <SortHeader column="status" label="状态" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <th scope="col" className="w-[7rem] p-3">质量</th>
                <th scope="col" className="w-[16rem] p-3">阻断原因</th>
                <th scope="col" className="w-[16rem] p-3">输出</th>
                <th scope="col" className="w-[16rem] p-3">官方证据</th>
                {canShowRowActions && <th scope="col" className="w-[6rem] p-3">操作</th>}
              </tr>
            </thead>
            <tbody>
              {paginatedCandidates.length === 0 ? (
                <tr>
                  <td colSpan={canShowRowActions ? 9 : 8} className="px-4 py-8 text-center text-slate-500">
                    {filter ? "没有匹配的候选" : "暂无候选记录"}
                  </td>
                </tr>
              ) : (
                paginatedCandidates.map((candidate, index) => {
                  const quality = candidateQualityBadge(candidate);
                  const evidence = officialEvidenceText(candidate, checkResults);
                  return (
                    <tr
                      key={`${candidateIdentity(candidate)}_${index}`}
                      className="align-top border-b border-slate-100 transition-colors hover:bg-slate-50"
                    >
                      <td className="p-3">
                        <span className="font-mono text-xs text-brand-700" title={candidateIds(candidate).join(" / ")}>
                          {candidateIdentity(candidate).slice(0, 16) || "-"}
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="whitespace-normal break-words font-mono text-xs leading-6 text-slate-900" title={candidateText(candidate.expression)}>
                          {candidateText(candidate.expression) || "-"}
                        </div>
                        <div className="mt-1 break-words text-xs text-slate-500" title={candidateText(candidate.family)}>
                          {candidateText(candidate.family)}
                        </div>
                      </td>
                      <td className="p-3">
                        <span className="font-mono font-semibold text-slate-950">
                          {candidate.scorecard?.total_score?.toFixed(1) ?? "-"}
                        </span>
                      </td>
                      <td className="p-3">
                        <span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>
                          {candidateStatus(candidate) || "-"}
                        </span>
                      </td>
                      <td className="p-3">
                        <span className={`badge ${quality.tone}`} title={quality.title}>
                          {quality.label}
                        </span>
                      </td>
                      <td className="p-3 text-xs leading-6 text-slate-700">
                        <div className="whitespace-normal break-words" title={candidateBlockerText(candidate)}>
                          {candidateBlockerText(candidate)}
                        </div>
                      </td>
                      <td className="p-3 text-xs leading-6 text-slate-700">
                        <div className="font-medium text-slate-900">{candidateOutputSummary(candidate)}</div>
                        <div className="mt-1 break-words text-slate-600" title={candidateOutputDetail(candidate)}>
                          {candidateOutputDetail(candidate)}
                        </div>
                      </td>
                      <td className="p-3 text-xs leading-6 text-slate-700">
                        <div className="break-words" title={evidence}>{evidence}</div>
                        <div className="mt-1 break-words text-slate-600" title={candidateText(candidate.simulation_id)}>
                          {candidateText(candidate.simulation_id) || "simulation:-"}
                        </div>
                      </td>
                      {canShowRowActions && (
                        <td className="p-3">
                          <button
                            type="button"
                            className="btn-ghost text-xs"
                            aria-label={`评分 ${candidateIdentity(candidate)}`}
                            onClick={() => onScore?.(candidate)}
                          >
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

        <div className="flex flex-col gap-3 border-t border-slate-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-600" role="status" aria-live="polite">
            显示 {visibleStart}-{visibleEnd}，共 {sortedCandidates.length} 条
          </div>
          {sortedCandidates.length > PAGE_SIZE && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
                className="btn-ghost text-sm disabled:opacity-50"
              >
                上一页
              </button>
              <span className="text-sm text-slate-600">
                {currentPage} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
                className="btn-ghost text-sm disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SortHeader({
  column,
  label,
  sortKey,
  sortAsc,
  onSort,
}: {
  column: SortKey;
  label: string;
  sortKey: SortKey;
  sortAsc: boolean;
  onSort: (column: SortKey) => void;
}) {
  const active = sortKey === column;
  return (
    <th scope="col" className="w-[7rem] p-3 font-medium" aria-sort={active ? (sortAsc ? "ascending" : "descending") : "none"}>
      <button type="button" className="flex items-center gap-1 transition-colors hover:text-slate-950" onClick={() => onSort(column)}>
        {label}
        <span className="text-brand-700" aria-hidden="true">{active ? (sortAsc ? "↑" : "↓") : ""}</span>
      </button>
    </th>
  );
}

function QualitySummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="card min-w-0 p-3">
      <p className="text-muted">{label}</p>
      <p className="mt-1 break-words font-semibold text-slate-950" title={value}>{value}</p>
    </div>
  );
}

function CandidateMobileCard({
  candidate,
  checkResults,
  canShowRowActions,
  onScore,
}: {
  candidate: Candidate;
  checkResults: Map<string, CandidateCheckResult>;
  canShowRowActions: boolean;
  onScore?: (candidate: Candidate) => void;
}) {
  const quality = candidateQualityBadge(candidate);
  const evidence = officialEvidenceText(candidate, checkResults);
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs text-brand-700" title={candidateIds(candidate).join(" / ")}>
            {candidateIdentity(candidate).slice(0, 24) || "-"}
          </p>
          <p className="mt-2 break-words font-mono text-xs leading-6 text-slate-900" title={candidateText(candidate.expression)}>
            {candidateText(candidate.expression) || "-"}
          </p>
        </div>
        <span className={`badge shrink-0 ${quality.tone}`} title={quality.title}>
          {quality.label}
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <dt className="text-muted">评分</dt>
          <dd className="mt-1 font-mono font-semibold text-slate-950">{candidate.scorecard?.total_score?.toFixed(1) ?? "-"}</dd>
        </div>
        <div>
          <dt className="text-muted">状态</dt>
          <dd className="mt-1"><span className={`badge ${statusBadgeClass(candidateStatus(candidate))}`}>{candidateStatus(candidate) || "-"}</span></dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted">阻断原因</dt>
          <dd className="mt-1 break-words leading-6 text-slate-700">{candidateBlockerText(candidate)}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted">官方证据</dt>
          <dd className="mt-1 break-words leading-6 text-slate-700">{evidence}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-muted">输出</dt>
          <dd className="mt-1 text-slate-900">{candidateOutputSummary(candidate)}</dd>
          <dd className="mt-1 break-words text-muted">{candidateOutputDetail(candidate)}</dd>
        </div>
      </dl>

      {canShowRowActions && (
        <button
          type="button"
          className="btn-ghost mt-4 min-h-11 w-full text-sm"
          aria-label={`评分 ${candidateIdentity(candidate)}`}
          onClick={() => onScore?.(candidate)}
        >
          评分
        </button>
      )}
    </article>
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
    submittable: "可提交预检",
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
    return { label: "达标", tone: "badge-success", title: "符合提交前质量门禁" };
  }
  if (candidateLocalValid(candidate)) {
    return { label: "本地通过", tone: "badge-warning", title: "本地质量通过，仍需官方证据" };
  }
  if (candidateHasBlockingQuality(candidate)) {
    return { label: "阻断", tone: "badge-danger", title: candidateBlockerText(candidate) };
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
  if (normalized.includes("submitted") || normalized.includes("completed")) return "badge-success";
  if (normalized.includes("failed") || normalized.includes("blocked") || normalized.includes("rejected")) return "badge-danger";
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
