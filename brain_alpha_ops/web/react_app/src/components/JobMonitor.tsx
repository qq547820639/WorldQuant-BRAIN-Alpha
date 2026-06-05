/** Job monitor using SSE for real-time status updates. */

import { useState, useEffect, useCallback } from "react";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import type { JobStatus, SSEEvent } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function JobMonitor({ notify }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);
  const api = useApi();

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    if (event.type === "progress") {
      setStatus((prev) => ({
        ...(prev || { job_id: event.job_id || event.task_id || "", status: "running" }),
        job_id: event.job_id || event.task_id || prev?.job_id || "",
        task_id: event.task_id || event.job_id || prev?.task_id,
        status: "running",
        phase: event.phase || event.progress?.phase || prev?.phase,
        percent_complete: event.percent_complete,
        eta_seconds: event.eta_seconds,
        status_message: event.status_message,
        progress: event.progress || (event.data as JobStatus["progress"]),
      }));
    } else if (event.type === "complete") {
      setRunning(false);
      notify("success", "任务已完成");
      setEvents((prev) => [...prev, `✓ 任务完成`]);
      setStatus((prev) => prev ? { ...prev, status: "completed", result: event.result, progress: event.progress || prev.progress } : prev);
    } else if (event.type === "error") {
      setRunning(false);
      setProgressError(String(event.error || event.data?.error || "任务错误"));
      notify("error", String(event.error || event.data?.error || "任务错误"));
      setEvents((prev) => [...prev, `✕ ${event.error || event.data?.error || "错误"}`]);
    } else if (event.type === "candidate") {
      setEvents((prev) => {
        const msg = `✓ 候选 ${(event.data as Record<string, unknown>)?.alpha_id || "?"} 得分 ${(event.data as Record<string, unknown>)?.score || 0}`;
        return [...prev.slice(-50), msg];
      });
    } else if (event.type === "submission") {
      notify("success", `已提交: ${(event.data as Record<string, unknown>)?.alpha_id || "未知"}`);
      setEvents((prev) => [...prev.slice(-50), `🚀 已提交 ${(event.data as Record<string, unknown>)?.alpha_id || "?"}`]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notify]);

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const { connected } = useSSE(sseUrl, { onEvent: handleSSEEvent });

  const startJob = useCallback(async () => {
    setRunning(true);
    setProgressError(null);
    setStatus({
      job_id: "",
      task_id: "",
      status: "running",
      phase: "queued",
      progress: { phase: "queued", status_message: "正在启动流水线。", percent_complete: 0 },
    });
    const result = await api.call<{ job_id: string }>("/api/run", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const jid = String((result as unknown as { job_id?: string; task_id?: string } | null)?.job_id || (result as unknown as { task_id?: string } | null)?.task_id || "");
    if (result?.ok && jid) {
      setJobId(jid);
      setRunning(true);
      setProgressError(null);
      setStatus({
        job_id: jid,
        task_id: jid,
        status: "running",
        phase: "queued",
        progress: { phase: "queued", status_message: "流水线已排队。", percent_complete: 0 },
      });
      notify("info", `任务已启动: ${jid}`);
    } else {
      setRunning(false);
      const message = result?.error || "启动任务失败";
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
    }
  }, [api, notify]);

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    await api.call("/api/stop", { method: "POST", body: JSON.stringify({ job_id: jobId }) });
    setRunning(false);
    setJobId(null);
    notify("info", "任务已停止");
  }, [api, jobId, notify]);

  useEffect(() => {
    if (!running) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(`/api/status?job_id=${encodeURIComponent(jobId || "")}`);
      if (result?.ok) {
        setStatus(result as unknown as JobStatus);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, jobId, api]);

  const cycleProgress = status?.cycle && status?.max_cycles
    ? Math.round((status.cycle / status.max_cycles) * 100)
    : 0;
  const progress = status?.progress || {
    phase: status?.phase,
    percent_complete: status?.percent_complete ?? cycleProgress,
    eta_seconds: status?.eta_seconds,
    status_message: status?.status_message,
  };

  return (
    <div className="card min-w-0 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-gray-200">流水线状态</h3>
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-success" : "bg-danger"}`} aria-hidden="true" />
          <span className={`badge ${running ? "badge-success" : "badge-neutral"}`} role="status" aria-label={`流水线${running ? "运行中" : "空闲"}`}>
            {running ? "运行中" : "空闲"}
          </span>
        </div>
      </div>

      {(running || api.loading) && (
        <div className="space-y-3">
          <ProgressFeedback
            state={progressError ? "error" : "progress"}
            title="流水线进度"
            progress={progress}
            error={progressError}
            compact
          />
          <div className="grid grid-cols-1 gap-3 text-xs text-muted sm:grid-cols-2">
            <span>轮次: {status?.cycle ?? 0}/{status?.max_cycles ?? 0}</span>
            <span>阶段: {status?.phase ?? "-"}</span>
            <span>候选数: {status?.progress?.candidates_generated ?? 0}</span>
            <span>回测数: {status?.progress?.backtests_completed ?? 0}</span>
          </div>
        </div>
      )}

      {!running && progressError && (
        <ProgressFeedback
          state="error"
          title="流水线进度"
          progress={status?.progress}
          error={progressError}
          onRetry={startJob}
          compact
        />
      )}

      <div className="flex flex-wrap gap-2">
        <button onClick={startJob} disabled={running} className="btn-primary text-sm">
          <span aria-hidden="true">▶</span> 启动流水线
        </button>
        <button onClick={stopJob} disabled={!running} className="btn-secondary text-sm">
          <span aria-hidden="true">⏹</span> 停止
        </button>
      </div>

      {events.length > 0 && (
        <div className="max-h-32 min-w-0 overflow-y-auto bg-gray-950 rounded-lg p-3 font-mono text-xs text-gray-400 space-y-1" role="log" aria-live="polite" aria-label="流水线事件日志">
          {events.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}
    </div>
  );
}
