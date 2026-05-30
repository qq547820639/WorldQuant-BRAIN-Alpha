/** Filterable, sortable candidate data table. */

import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import type { UIEvent } from "react";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import type { Candidate, SSEEvent, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onScore?: (candidate: Candidate) => void;
  viewMode?: CandidateQueueView;
}

type SortKey = "score" | "sharpe" | "fitness" | "turnover" | "status";
type CandidateQueueView =
  | "candidates"
  | "pending_backtest"
  | "running_backtest"
  | "backtest_rework"
  | "passed"
  | "submittable"
  | "submitted"
  | "failed";
interface CandidateCheckResult {
  alpha_id?: string;
  official_alpha_id?: string;
  simulation_id?: string;
  passed?: boolean;
  submittable?: boolean;
  is_stale?: boolean;
}
type CandidateCheckIndex = Record<string, CandidateCheckResult>;
const MIN_GENERATE_COUNT = 1;
const MAX_GENERATE_COUNT = 100;
const MAX_FILTER_LENGTH = 200;
const CANDIDATE_FETCH_LIMIT = 1000;
const VIRTUAL_ROW_HEIGHT = 48;
const VIRTUAL_OVERSCAN = 8;
const VIRTUAL_VIEWPORT_HEIGHT = 520;
const QUEUE_VIEW_META: Record<CandidateQueueView, { title: string; empty: string }> = {
  candidates: {
    title: "Candidates",
    empty: "No candidates found",
  },
  pending_backtest: {
    title: "Waiting for backtest",
    empty: "No candidates are waiting for backtest",
  },
  running_backtest: {
    title: "Backtesting",
    empty: "No candidates are currently backtesting",
  },
  backtest_rework: {
    title: "Backtest rework",
    empty: "No candidates need backtest rework",
  },
  passed: {
    title: "Passed candidates",
    empty: "No candidates have reached the submission gate",
  },
  submittable: {
    title: "Ready to submit",
    empty: "No candidates have a fresh passed pre-submit check",
  },
  submitted: {
    title: "Submitted candidates",
    empty: "No submitted candidate records found",
  },
  failed: {
    title: "Blocked candidates",
    empty: "No failed, rejected, or blocked candidates found",
  },
};

export default function CandidateTable({ notify, onScore, viewMode = "candidates" }: Props) {
  const api = useApi<{ candidates: Candidate[] }>();
  const checkResultsApi = useApi<{ items?: CandidateCheckResult[] }>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [checkResults, setCheckResults] = useState<CandidateCheckIndex>({});
  const [filter, setFilter] = useState("");
  const [generateCount, setGenerateCount] = useState(5);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskState, setTaskState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [taskProgress, setTaskProgress] = useState<UnifiedProgress | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const tableViewportRef = useRef<HTMLDivElement | null>(null);
  const callApi = api.call;
  const callCheckResultsApi = checkResultsApi.call;
  const viewMeta = QUEUE_VIEW_META[viewMode];

  const loadCandidates = useCallback(async () => {
    const result = await callApi(`/api/candidates?limit=${CANDIDATE_FETCH_LIMIT}`);
    if (result?.ok) {
      const data = result as unknown as { candidates: Candidate[] };
      const nextRows = data.candidates || [];
      setCandidates((current) => nextRows.length || current.length === 0 ? nextRows : current);
    } else if (result?.error) {
      notify("error", result.error);
    }
  }, [callApi, notify]);

  const loadCheckResults = useCallback(async () => {
    if (viewMode !== "submittable") return;
    const result = await callCheckResultsApi<{ items?: CandidateCheckResult[] }>("/api/check_results");
    if (result?.ok) {
      const data = result as unknown as { items?: CandidateCheckResult[] };
      setCheckResults(indexCheckResults(data.items || []));
    } else if (result?.error) {
      notify("error", result.error);
    }
  }, [callCheckResultsApi, notify, viewMode]);

  const load = useCallback(async () => {
    await Promise.all([loadCandidates(), loadCheckResults()]);
  }, [loadCandidates, loadCheckResults]);

  useEffect(() => { void load(); }, [load]);

  const handleTaskEvent = useCallback((event: SSEEvent) => {
    const progress = event.progress || event.data || {};
    setTaskProgress(progress as UnifiedProgress);
    if (event.type === "error" || event.ok === false || event.status === "failed") {
      setTaskState("error");
      setTaskError(event.error || event.status_message || "Candidate generation failed");
      notify("error", event.error || "Candidate generation failed");
      return;
    }
    if (event.type === "complete") {
      setTaskState("success");
      const result = event.result as { candidates?: Candidate[]; candidates_preview?: Candidate[]; count?: number } | undefined;
      const rows = result?.candidates || result?.candidates_preview || [];
      if (rows.length) setCandidates(rows);
      void load();
      notify("success", `Candidate generation completed${result?.count ? `: ${result.count}` : ""}`);
      setTaskId(null);
      return;
    }
    setTaskState("progress");
  }, [load, notify]);

  useSSE(taskId ? `/sse?job_id=${encodeURIComponent(taskId)}` : null, { onEvent: handleTaskEvent });

  const generateCandidates = useCallback(async () => {
    setTaskState("loading");
    setTaskError(null);
    setTaskProgress({ phase: "candidate_generation", status_message: "Starting candidate generation." });
    const result = await callApi<{ job_id: string; task_id?: string }>("/api/generate_candidates", {
      method: "POST",
      body: JSON.stringify({ count: clampGenerateCount(generateCount) }),
    });
    const nextTaskId = String((result as unknown as { task_id?: string; job_id?: string } | null)?.task_id || (result as unknown as { job_id?: string } | null)?.job_id || "");
    if (result?.ok && nextTaskId) {
      setTaskId(nextTaskId);
      setTaskState("progress");
      notify("info", `Candidate generation started: ${nextTaskId}`);
    } else {
      setTaskState("error");
      setTaskError(result?.error || "Failed to start candidate generation");
      notify("error", result?.error || "Failed to start candidate generation");
    }
  }, [callApi, generateCount, notify]);

  const updateGenerateCount = (value: string) => {
    setGenerateCount(clampGenerateCount(value));
  };

  const updateFilter = (value: string) => {
    setFilter(sanitizeTextInput(value, MAX_FILTER_LENGTH));
  };

  const sorted = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase();
    const viewRows = candidates.filter((candidate) => candidateMatchesQueueView(candidate, viewMode, checkResults));
    const filtered = normalizedFilter
      ? viewRows.filter((c) =>
          candidateText(c.expression).toLowerCase().includes(normalizedFilter) ||
          candidateText(c.family).toLowerCase().includes(normalizedFilter) ||
          candidateIdentity(c).toLowerCase().includes(normalizedFilter),
        )
      : viewRows;

    return [...filtered].sort((a, b) => {
      let va: number, vb: number;
      switch (sortKey) {
        case "score": va = a.scorecard?.total_score ?? 0; vb = b.scorecard?.total_score ?? 0; break;
        case "sharpe": va = a.official_metrics?.sharpe ?? 0; vb = b.official_metrics?.sharpe ?? 0; break;
        case "fitness": va = a.official_metrics?.fitness ?? 0; vb = b.official_metrics?.fitness ?? 0; break;
        case "turnover": va = a.official_metrics?.turnover ?? 0; vb = b.official_metrics?.turnover ?? 0; break;
        case "status": return candidateStatus(a).localeCompare(candidateStatus(b)) * (sortAsc ? 1 : -1);
        default: return 0;
      }
      return sortAsc ? va - vb : vb - va;
    });
  }, [candidates, checkResults, filter, sortKey, sortAsc, viewMode]);

  useEffect(() => {
    setScrollTop(0);
    tableViewportRef.current?.scrollTo({ top: 0 });
  }, [candidates.length, filter, sortAsc, sortKey]);

  const virtualStartIndex = Math.max(0, Math.floor(scrollTop / VIRTUAL_ROW_HEIGHT) - VIRTUAL_OVERSCAN);
  const virtualWindowSize = Math.ceil(VIRTUAL_VIEWPORT_HEIGHT / VIRTUAL_ROW_HEIGHT) + VIRTUAL_OVERSCAN * 2;
  const virtualEndIndex = Math.min(sorted.length, virtualStartIndex + virtualWindowSize);
  const virtualRows = sorted.slice(virtualStartIndex, virtualEndIndex);
  const topSpacerHeight = virtualStartIndex * VIRTUAL_ROW_HEIGHT;
  const bottomSpacerHeight = Math.max(sorted.length - virtualEndIndex, 0) * VIRTUAL_ROW_HEIGHT;
  const visibleStartRow = sorted.length ? virtualStartIndex + 1 : 0;
  const visibleEndRow = virtualEndIndex;

  const handleVirtualScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  };

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortAsc(!sortAsc); return; }
    setSortKey(key);
    setSortAsc(false);
  };

  const statusBadge = (s?: string) => {
    const normalized = candidateText(s);
    if (normalized.includes("submitted")) return "badge-success";
    if (normalized.includes("completed") || normalized.includes("gated:submit")) return "badge-success";
    if (normalized.includes("failed") || normalized.includes("blocked")) return "badge-danger";
    if (normalized.includes("validat") || normalized.includes("simulat")) return "badge-warning";
    return "badge-neutral";
  };

  const loading = api.loading || (viewMode === "submittable" && checkResultsApi.loading);
  const loadError = api.error || (viewMode === "submittable" ? checkResultsApi.error : null);

  if (loading && candidates.length === 0) {
    return (
      <ProgressFeedback
        state="loading"
        title="Candidates"
        progress={{ phase: "candidate_load", status_message: "Loading candidates." }}
      />
    );
  }

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-100">{viewMeta.title}</h2>
        {viewMode !== "candidates" && (
          <p className="text-xs text-muted" role="status" aria-live="polite">
            Queue filter: {viewMode.replace(/_/g, " ")}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <input
          type="text"
          aria-label="Filter candidates"
          placeholder="Filter by expression, family, or ID..."
          value={filter}
          maxLength={MAX_FILTER_LENGTH}
          onChange={(e) => updateFilter(e.target.value)}
          className="w-full min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500 sm:flex-1"
        />
        <button onClick={load} className="btn-secondary text-sm" disabled={loading} aria-label="Refresh candidates">
          <span aria-hidden="true">↻</span> Refresh
        </button>
        <label className="flex items-center gap-2 text-xs text-muted">
          Count
          <input
            type="number"
            min={MIN_GENERATE_COUNT}
            max={MAX_GENERATE_COUNT}
            value={generateCount}
            onChange={(e) => updateGenerateCount(e.target.value)}
            className="w-20 bg-gray-800 border border-gray-700 rounded-lg px-2 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500"
          />
        </label>
        <button onClick={generateCandidates} className="btn-primary text-sm" disabled={taskState === "loading" || taskState === "progress"}>
          Generate
        </button>
      </div>

      <ProgressFeedback
        state={taskState}
        title="Candidate generation"
        progress={taskProgress}
        error={taskError}
        onRetry={generateCandidates}
        compact={taskState === "idle" || taskState === "success"}
      />

      {loading && candidates.length > 0 && (
        <ProgressFeedback
          state="loading"
          title="Candidates"
          progress={{ phase: "candidate_load", status_message: "Refreshing candidate records." }}
          compact
        />
      )}

      {loadError && (
        <div className="card border-danger/40 bg-danger/10" role="alert" aria-live="assertive">
          <div className="flex items-center justify-between gap-3">
            <p className="text-danger text-sm">Failed to load candidates: {loadError}</p>
            <button onClick={load} className="btn-secondary text-sm" disabled={loading}>
              Retry
            </button>
          </div>
        </div>
      )}

      <div className="card min-w-0 overflow-hidden p-0">
        <div
          ref={tableViewportRef}
          className="max-w-full overflow-auto"
          style={{ maxHeight: VIRTUAL_VIEWPORT_HEIGHT }}
          onScroll={handleVirtualScroll}
          data-virtualized-candidate-table="true"
          aria-label="Scrollable candidate results"
        >
          <table
            className="min-w-[760px] w-full text-sm"
            aria-label="Candidate results"
            aria-rowcount={sorted.length > 0 ? sorted.length + 1 : undefined}
          >
            <thead>
              <tr className="border-b border-gray-800 text-left text-xs text-muted uppercase tracking-wider">
                <th scope="col" className="p-3">ID</th>
                <th scope="col" className="p-3">Expression</th>
                <SortHeader label="Score" column="score" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <SortHeader label="Sharpe" column="sharpe" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <SortHeader label="Fitness" column="fitness" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <SortHeader label="TO" column="turnover" sortKey={sortKey} sortAsc={sortAsc} onSort={handleSort} />
                <th scope="col" className="p-3">Status</th>
                <th scope="col" className="p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 ? (
                <tr><td colSpan={8} className="p-6 text-center text-muted">{viewMeta.empty}</td></tr>
              ) : (
                <>
                  {topSpacerHeight > 0 && (
                    <tr aria-hidden="true">
                      <td colSpan={8} style={{ height: topSpacerHeight, padding: 0, border: 0 }} />
                    </tr>
                  )}
                  {virtualRows.map((c, index) => (
                    <tr
                      key={`${candidateIdentity(c) || candidateText(c.expression)}_${virtualStartIndex + index}`}
                      className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                      aria-rowindex={virtualStartIndex + index + 2}
                      style={{ height: VIRTUAL_ROW_HEIGHT }}
                    >
                      <td className="p-3 text-brand-400 font-mono text-xs">{candidateIdentity(c).slice(0, 12) || "-"}</td>
                      <td className="p-3 font-mono text-xs max-w-xs truncate" title={candidateText(c.expression)}>
                        {candidateText(c.expression) || "-"}
                      </td>
                      <td className="p-3 font-mono">{c.scorecard?.total_score?.toFixed(1) ?? "-"}</td>
                      <td className="p-3 font-mono">{c.official_metrics?.sharpe?.toFixed(2) ?? "-"}</td>
                      <td className="p-3 font-mono">{c.official_metrics?.fitness?.toFixed(2) ?? "-"}</td>
                      <td className="p-3 font-mono">{c.official_metrics?.turnover != null ? `${(c.official_metrics.turnover * 100).toFixed(1)}%` : "-"}</td>
                      <td className="p-3"><span className={`badge text-xs ${statusBadge(candidateStatus(c))}`}>{candidateStatus(c) || "-"}</span></td>
                      <td className="p-3">
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          aria-label={`Score ${candidateIdentity(c) || candidateText(c.expression) || "candidate"}`}
                          onClick={() => onScore?.(c)}
                          disabled={!onScore}
                        >
                          Score
                        </button>
                      </td>
                    </tr>
                  ))}
                  {bottomSpacerHeight > 0 && (
                    <tr aria-hidden="true">
                      <td
                        colSpan={8}
                        style={{ height: bottomSpacerHeight, padding: 0, border: 0 }}
                      >
                        &nbsp;
                      </td>
                    </tr>
                  )}
                </>
              )}
            </tbody>
          </table>
        </div>
        {sorted.length > 0 && (
          <div className="flex flex-col gap-2 border-t border-gray-800 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted" role="status" aria-live="polite">
              Showing {visibleStartRow}-{visibleEndRow} of {sorted.length} candidates
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function clampGenerateCount(value: string | number) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return MIN_GENERATE_COUNT;
  return Math.min(Math.max(Math.trunc(parsed), MIN_GENERATE_COUNT), MAX_GENERATE_COUNT);
}

function SortHeader({
  label,
  column,
  sortKey,
  sortAsc,
  onSort,
}: {
  label: string;
  column: SortKey;
  sortKey: SortKey;
  sortAsc: boolean;
  onSort: (key: SortKey) => void;
}) {
  const active = sortKey === column;
  return (
    <th scope="col" className="p-3" aria-sort={active ? (sortAsc ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className="inline-flex items-center gap-1 uppercase tracking-wider text-left"
        onClick={() => onSort(column)}
      >
        <span>{label}</span>
        <span aria-hidden="true">{active ? (sortAsc ? "↑" : "↓") : ""}</span>
      </button>
    </th>
  );
}

function sanitizeTextInput(value: string, maxLength: number) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, maxLength);
}

function candidateIdentity(candidate: Candidate) {
  return candidateIds(candidate)[0] || "";
}

function candidateStatus(candidate: Candidate) {
  return candidateText(candidate.lifecycle_status || (candidate as Candidate & { status?: unknown }).status);
}

function candidateText(value: unknown) {
  return String(value || "");
}

function candidateIds(candidate: Pick<Candidate, "alpha_id" | "official_alpha_id" | "simulation_id">) {
  return [candidate.alpha_id, candidate.official_alpha_id, candidate.simulation_id]
    .map(candidateText)
    .filter(Boolean);
}

function candidateStage(candidate: Candidate) {
  return candidateText((candidate as Candidate & { stage?: unknown }).stage).toLowerCase();
}

function indexCheckResults(items: CandidateCheckResult[]) {
  const index: CandidateCheckIndex = {};
  for (const item of items) {
    for (const id of candidateIds(item as Candidate)) index[id] = item;
  }
  return index;
}

function freshPassedCheckForCandidate(candidate: Candidate, checkResults: CandidateCheckIndex) {
  for (const id of candidateIds(candidate)) {
    const result = checkResults[id];
    if (result && result.is_stale !== true && (result.submittable ?? result.passed)) return true;
  }
  return false;
}

function candidateMatchesQueueView(candidate: Candidate, viewMode: CandidateQueueView, checkResults: CandidateCheckIndex) {
  if (viewMode === "candidates") return true;
  const status = candidateStatus(candidate).toLowerCase();
  if (viewMode === "pending_backtest") return status === "pending_backtest";
  if (viewMode === "running_backtest") return status === "running_backtest" || status === "running";
  if (viewMode === "backtest_rework") return status === "backtest_rework" || status === "failed_backtest" || status === "rejected";
  if (viewMode === "passed") return status === "submission_ready" || Boolean((candidate.gate as { submission_ready?: unknown } | undefined)?.submission_ready);
  if (viewMode === "submittable") return status !== "submitted" && candidateStage(candidate) !== "submitted" && freshPassedCheckForCandidate(candidate, checkResults);
  if (viewMode === "submitted") return status === "submitted" || candidateStage(candidate) === "submitted";
  return status === "failed" || status === "rejected" || status === "blocked";
}
