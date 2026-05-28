/** Filterable, sortable candidate data table. */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useApi } from "@/hooks/useApi";
import type { Candidate } from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

type SortKey = "score" | "sharpe" | "fitness" | "turnover" | "status";

export default function CandidateTable({ notify }: Props) {
  const api = useApi<{ candidates: Candidate[] }>();
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);

  const load = useCallback(async () => {
    const result = await api.call("/api/candidates?limit=100");
    if (result?.ok) {
      const data = result as unknown as { candidates: Candidate[] };
      setCandidates(data.candidates || []);
    }
  }, [api]);

  useEffect(() => { load(); }, [load]);

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
    return <div className="card animate-pulse"><p className="text-muted text-sm">Loading candidates...</p></div>;
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
      </div>

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
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr><td colSpan={7} className="p-6 text-center text-muted">No candidates found</td></tr>
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
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
