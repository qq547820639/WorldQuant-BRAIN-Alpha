/** Job monitor using SSE for real-time status updates. */

import { useState, useEffect, useCallback } from "react";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, SSEEvent } from "@/types";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function JobMonitor({ notify }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const api = useApi();

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    if (event.type === "progress") {
      setStatus((prev) => prev ? { ...prev, progress: event.data as unknown as JobStatus["progress"] } : null);
    } else if (event.type === "complete") {
      setRunning(false);
      notify("success", "Job completed successfully");
      setEvents((prev) => [...prev, `✓ Job completed`]);
    } else if (event.type === "error") {
      notify("error", String(event.data?.error || "Job error"));
      setEvents((prev) => [...prev, `✕ ${event.data?.error || "Error"}`]);
    } else if (event.type === "candidate") {
      setEvents((prev) => {
        const msg = `✓ Candidate ${(event.data as Record<string, unknown>)?.alpha_id || "?"} scored ${(event.data as Record<string, unknown>)?.score || 0}`;
        return [...prev.slice(-50), msg];
      });
    } else if (event.type === "submission") {
      notify("success", `Submitted: ${(event.data as Record<string, unknown>)?.alpha_id || "unknown"}`);
      setEvents((prev) => [...prev.slice(-50), `🚀 Submitted ${(event.data as Record<string, unknown>)?.alpha_id || "?"}`]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notify]);

  const sseUrl = jobId ? `/sse?job_id=${jobId}` : null;
  const { connected } = useSSE(sseUrl, { onEvent: handleSSEEvent });

  const startJob = useCallback(async () => {
    const result = await api.call<{ job_id: string }>("/api/run", {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (result?.ok && result.data) {
      const jid = (result.data as unknown as { job_id: string }).job_id;
      setJobId(jid);
      setRunning(true);
      notify("info", `Job started: ${jid}`);
    } else {
      notify("error", "Failed to start job");
    }
  }, [api, notify]);

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    await api.call(`/api/stop?job_id=${jobId}`, { method: "POST" });
    setRunning(false);
    setJobId(null);
    notify("info", "Job stopped");
  }, [api, jobId, notify]);

  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(`/api/status?job_id=${jobId || ""}`);
      if (result?.data) {
        setStatus(result.data as unknown as JobStatus);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, jobId, api]);

  const progress = status?.cycle && status?.max_cycles
    ? Math.round((status.cycle / status.max_cycles) * 100)
    : 0;

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-200">Pipeline Status</h3>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-success" : "bg-danger"}`} />
          <span className={`badge ${running ? "badge-success" : "badge-neutral"}`}>
            {running ? "Running" : "Idle"}
          </span>
        </div>
      </div>

      {running && (
        <>
          <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-brand-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs text-muted">
            <span>Cycle: {status?.cycle ?? 0}/{status?.max_cycles ?? 0}</span>
            <span>Phase: {status?.phase ?? "-"}</span>
            <span>Candidates: {status?.progress?.candidates_generated ?? 0}</span>
            <span>Backtests: {status?.progress?.backtests_completed ?? 0}</span>
          </div>
        </>
      )}

      <div className="flex gap-2">
        <button onClick={startJob} disabled={running} className="btn-primary text-sm">
          ▶ Start Pipeline
        </button>
        <button onClick={stopJob} disabled={!running} className="btn-secondary text-sm">
          ⏹ Stop
        </button>
      </div>

      {events.length > 0 && (
        <div className="max-h-32 overflow-y-auto bg-gray-950 rounded-lg p-3 font-mono text-xs text-gray-400 space-y-1">
          {events.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}
    </div>
  );
}
