/** Filterable, sortable candidate data table. */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useApi } from "@/hooks/useApi";
import { useSSE } from "@/hooks/useSSE";
import type { Candidate, SSEEvent, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  onScore?: (candidate: Candidate) => void;
}

type SortKey = "score" | "sharpe" | "fitness" | "turnover" | "status";

export default function CandidateTable({ notify, onScore }: Props) {
  const api = useApi<{ candidates: Candidate[] }>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskState, setTaskState] = useState<"idle" | "loading" | "progress" | "success" | "error">("idle");
  const [taskProgress, setTaskProgress] = useState<UnifiedProgress | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const callApi = api.call;

  const load = useCallback(async () => {
    const result = await callApi("/api/candidates?limit=100");
    if (result?.ok) {
      const data = result as unknown as { candidates: Candidate[] };
      const nextRows = data.candidates || [];
      setCandidates((current) => nextRows.length || current.length === 0 ? nextRows : current);
    } else if (result?.error) {
      notify("error", result.error);
    }
  }, [callApi, notify]);

  useEffect(() => { load(); }, [load]);

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
      body: JSON.stringify({ count: 5 }),
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
  }, [callApi, notify]);

  const sorted = useMemo(() => {
    const filtered = filter
      ? candidates.filter((c) =>
          c.expression.toLowerCase().includes(filter.toLowerCase()) ||
          c.family.toLowerCase().includes(filter.toLowerCase()) ||
          (c.alpha_id || "").toLowerCase().includes(filter.toLowerCase()),
        )
      : candidates;

    return [...filtered].sort((a, b) => {
      let va: number, vb: number;
      switch (sortKey) {
        case "score": va = a.scorecard?.total_score ?? 0; vb = b.scorecard?.total_score ?? 0; break;
        case "sharpe": va = a.official_metrics?.sharpe ?? 0; vb = b.official_metrics?.sharpe ?? 0; break;
        case "fitness": va = a.official_metrics?.fitness ?? 0; vb = b.official_metrics?.fitness ?? 0; break;
        case "turnover": va = a.official_metrics?.turnover ?? 0; vb = b.official_metrics?.turnover ?? 0; break;
        case "status": return String(a.lifecycle_status).localeCompare(String(b.lifecycle_status)) * (sortAsc ? 1 : -1);
        default: return 0;
      }
      return sortAsc ? va - vb : vb - va;
    });
  }, [candidates, filter, sortKey, sortAsc]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortAsc(!sortAsc); return; }
    setSortKey(key);
    setSortAsc(false);
  };

  const statusBadge = (s: string) => {
    if (s.includes("submitted")) return "badge-success";
    if (s.includes("completed") || s.includes("gated:submit")) return "badge-success";
    if (s.includes("failed") || s.includes("blocked")) return "badge-danger";
    if (s.includes("validat") || s.includes("simulat")) return "badge-warning";
    return "badge-neutral";
  };

  if (api.loading && candidates.length === 0) {
    return (
      <ProgressFeedback
        state="loading"
        title="Candidates"
        progress={{ phase: "candidate_load", status_message: "Loading candidates." }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Filter by expression, family, or ID..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500"
        />
        <button onClick={load} className="btn-secondary text-sm" disabled={api.loading}>
          ↻ Refresh
        </button>
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

      {api.loading && candidates.length > 0 && (
        <ProgressFeedback
          state="loading"
          title="Candidates"
          progress={{ phase: "candidate_load", status_message: "Refreshing candidate records." }}
          compact
        />
      )}

      {api.error && (
        <div className="card border-danger/40 bg-danger/10">
          <div className="flex items-center justify-between gap-3">
            <p className="text-danger text-sm">Failed to load candidates: {api.error}</p>
            <button onClick={load} className="btn-secondary text-sm" disabled={api.loading}>
              Retry
            </button>
          </div>
        </div>
      )}

      <div className="card overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left text-xs text-muted uppercase tracking-wider">
              <th className="p-3">ID</th>
              <th className="p-3">Expression</th>
              <th className="p-3 cursor-pointer select-none" onClick={() => handleSort("score")}>
                Score {sortKey === "score" ? (sortAsc ? "↑" : "↓") : ""}
              </th>
              <th className="p-3 cursor-pointer select-none" onClick={() => handleSort("sharpe")}>
                Sharpe {sortKey === "sharpe" ? (sortAsc ? "↑" : "↓") : ""}
              </th>
              <th className="p-3 cursor-pointer select-none" onClick={() => handleSort("fitness")}>
                Fitness {sortKey === "fitness" ? (sortAsc ? "↑" : "↓") : ""}
              </th>
              <th className="p-3 cursor-pointer select-none" onClick={() => handleSort("turnover")}>
                TO {sortKey === "turnover" ? (sortAsc ? "↑" : "↓") : ""}
              </th>
              <th className="p-3">Status</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr><td colSpan={8} className="p-6 text-center text-muted">No candidates found</td></tr>
            ) : (
              sorted.slice(0, 50).map((c) => (
                <tr key={c.alpha_id} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="p-3 text-brand-400 font-mono text-xs">{c.alpha_id?.slice(0, 12) || "-"}</td>
                  <td className="p-3 font-mono text-xs max-w-xs truncate" title={c.expression}>
                    {c.expression}
                  </td>
                  <td className="p-3 font-mono">{c.scorecard?.total_score?.toFixed(1) ?? "-"}</td>
                  <td className="p-3 font-mono">{c.official_metrics?.sharpe?.toFixed(2) ?? "-"}</td>
                  <td className="p-3 font-mono">{c.official_metrics?.fitness?.toFixed(2) ?? "-"}</td>
                  <td className="p-3 font-mono">{c.official_metrics?.turnover != null ? `${(c.official_metrics.turnover * 100).toFixed(1)}%` : "-"}</td>
                  <td className="p-3"><span className={`badge text-xs ${statusBadge(c.lifecycle_status)}`}>{c.lifecycle_status}</span></td>
                  <td className="p-3">
                    <button
                      type="button"
                      className="btn-secondary text-xs"
                      onClick={() => onScore?.(c)}
                      disabled={!onScore}
                    >
                      Score
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
