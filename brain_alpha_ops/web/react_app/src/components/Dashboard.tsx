/** Main dashboard with KPIs, job monitor, and latest results. */

import { useEffect } from "react";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, CloudAlphaSummary, ResearchMemorySummary } from "@/types";
import KpiCard from "@/components/KpiCard";
import JobMonitor from "@/components/JobMonitor";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function Dashboard({ notify }: Props) {
  const statusApi = useApi<JobStatus>();
  const cloudApi = useApi<CloudAlphaSummary>();
  const memoryApi = useApi<ResearchMemorySummary>();

  useEffect(() => {
    statusApi.call("/api/status");
    cloudApi.call("/api/snapshot/cloud?limit=10");
    memoryApi.call("/api/snapshot/memory?limit=100&top_n=5");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const status = statusApi.data;
  const cloud = cloudApi.data;
  const memory = memoryApi.data;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          label="Total Candidates"
          value={memory?.total_candidates ?? status?.progress?.candidates_generated ?? "-"}
          subtitle={memory ? `${memory.families?.length ?? 0} families` : "Loading..."}
        />
        <KpiCard
          label="Cloud Alphas"
          value={cloud?.count ?? "-"}
          subtitle={cloud ? `${cloud.submitted_count} submitted` : "Loading..."}
          trend={cloud && cloud.submitted_count > 0 ? "up" : "neutral"}
        />
        <KpiCard
          label="Backtests"
          value={status?.progress?.backtests_completed ?? "-"}
          subtitle={status ? `${status.progress?.backtests_pending ?? 0} pending` : undefined}
        />
        <KpiCard
          label="Submissions"
          value={status?.progress?.submissions ?? cloud?.submitted_count ?? "-"}
          trend={cloud && cloud.passed_unsubmitted_count > 0 ? "up" : "neutral"}
        />
      </div>

      {/* Job Monitor + Cloud */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <JobMonitor notify={notify} />

        {/* Cloud Alpha Summary */}
        <div className="card space-y-3">
          <h3 className="text-sm font-semibold text-gray-200">Cloud Alpha Cache</h3>
          {cloudApi.loading ? (
            <p className="text-xs text-muted">Loading...</p>
          ) : cloudApi.error ? (
            <p className="text-xs text-danger">{cloudApi.error}</p>
          ) : cloud ? (
            <>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <span className="text-muted">Total cached</span>
                <span className="text-right">{cloud.count}</span>
                <span className="text-muted">Submitted</span>
                <span className="text-right text-success">{cloud.submitted_count}</span>
                <span className="text-muted">Passed (unsubmitted)</span>
                <span className="text-right text-warning">{cloud.passed_unsubmitted_count}</span>
                <span className="text-muted">Cache stale</span>
                <span className="text-right">{cloud.is_stale ? "⚠ Yes" : "✓ No"}</span>
              </div>
              {cloud.sample_alphas && cloud.sample_alphas.length > 0 && (
                <div className="max-h-40 overflow-y-auto bg-gray-950 rounded-lg p-2 text-xs font-mono">
                  {cloud.sample_alphas.slice(0, 5).map((a, i) => (
                    <div key={i} className="flex justify-between py-1 border-b border-gray-800 last:border-0">
                      <span className="text-brand-400">{a.alpha_id}</span>
                      <span className={a.pass_fail === "PASS" ? "text-success" : "text-danger"}>{a.pass_fail}</span>
                      <span>S:{a.sharpe?.toFixed(2)} F:{a.fitness?.toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>

      {/* Top Families & Fields */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Top Families</h3>
          {memory?.families?.slice(0, 5).map((f) => (
            <div key={f.name} className="flex justify-between text-xs py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-gray-300">{f.name}</span>
              <span className="text-muted">n={f.count} SR:{f.success_rate?.toFixed(2)}</span>
            </div>
          )) || <p className="text-xs text-muted">No data</p>}
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Top Fields</h3>
          {memory?.fields?.slice(0, 5).map((f) => (
            <div key={f.name} className="flex justify-between text-xs py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-gray-300">{f.name}</span>
              <span className="text-muted">n={f.count} SR:{f.success_rate?.toFixed(2)}</span>
            </div>
          )) || <p className="text-xs text-muted">No data</p>}
        </div>
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-200 mb-3">Failure Patterns</h3>
          {memory?.failure_patterns?.slice(0, 5).map((fp) => (
            <div key={fp.reason} className="flex justify-between text-xs py-1.5 border-b border-gray-800 last:border-0">
              <span className="text-danger/80">{fp.reason}</span>
              <span className="text-muted">x{fp.count}</span>
            </div>
          )) || <p className="text-xs text-muted">No failures</p>}
        </div>
      </div>
    </div>
  );
}
