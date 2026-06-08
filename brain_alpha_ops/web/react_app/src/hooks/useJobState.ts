/**
 * useJobState — App-level job state hook
 *
 * Lifts job monitoring state out of JobMonitor so it persists across page navigation.
 * The TopBar can display a running minibar, and any page can check job progress.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, hasCredentials, isTerminalStatus } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress } from "@/types";

export interface JobState {
  jobId: string | null;
  running: boolean;
  status: JobStatus | null;
  progress: UnifiedProgress | null;
  error: string | null;
  connected: boolean;
  events: string[];
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
}

const WATCHDOG_POLL_INTERVAL = 2000;
const WATCHDOG_MAX_FAILURES = 3;

export function useJobState(
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void,
  credentials?: BrainCredentials,
): JobState {
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progressError, setProgressError] = useState<string | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [pollFailures, setPollFailures] = useState(0);
  const autoCancelRequests = useRef<Set<string>>(new Set());
  const api = useApi();

  const progress = useMemo((): UnifiedProgress => status?.progress || {
    phase: status?.phase,
    percent_complete: status?.percent_complete,
    eta_seconds: status?.eta_seconds,
    status_message: status?.status_message,
  }, [status]);

  const failMonitor = useCallback((message: string, phase = "watchdog_failed") => {
    setRunning(false);
    setProgressError(message);
    setStatus((prev) => prev ? {
      ...prev, status: "failed", phase, error: message,
      progress: { ...(prev.progress || {}), phase, status_message: message, percent_complete: 100 },
    } : prev);
    setEvents((prev) => [...prev.slice(-50), message]);
  }, []);

  const cancelAmbiguousJob = useCallback(async (reason: CancelReason, message: string, targetJobId?: string | null) => {
    const id = targetJobId || jobId || status?.job_id;
    if (!id) return null;
    const key = `${id}:${reason}`;
    if (autoCancelRequests.current.has(key)) return null;
    autoCancelRequests.current.add(key);
    const result = await requestJobCancel({ jobId: id, reason, message });
    setEvents((prev) => [...prev.slice(-50), result?.ok === false ? "自动中断请求未确认" : "已安全停止状态不明确的流程。"]);
    return result;
  }, [jobId, status?.job_id]);

  // Stable deps: all setState functions are React-guaranteed stable;
  // `notify` is wrapped in useCallback by the caller
  const handleSSEEvent = useCallback((event: SSEEvent) => {
    if (event.type === "progress") {
      setPollFailures(0);
      setStatus((prev) => ({
        ...(prev || { job_id: event.job_id || event.task_id || "", status: "running" }),
        job_id: event.job_id || event.task_id || prev?.job_id || "",
        task_id: event.task_id || event.job_id || prev?.task_id,
        status: "running", phase: event.phase || event.progress?.phase || prev?.phase,
        percent_complete: event.percent_complete, eta_seconds: event.eta_seconds,
        status_message: event.status_message,
        progress: event.progress || (event.data as JobStatus["progress"]),
      }));
    } else if (event.type === "complete") {
      setRunning(false); setPollFailures(0);
      notify("success", "验证流程已完成");
      setEvents((prev) => [...prev, "验证流程完成"]);
      setStatus((prev) => prev ? { ...prev, status: "completed", result: event.result, progress: event.progress || prev.progress } : prev);
    } else if (event.type === "error") {
      setRunning(false); setPollFailures(0);
      setProgressError(String(event.error || event.data?.error || "验证流程错误"));
      notify("error", String(event.error || event.data?.error || "验证流程错误"));
    } else if (event.type === "candidate") {
      setEvents((prev) => [...prev.slice(-50), `候选 ${(event.data as Record<string, unknown>)?.alpha_id || "?"}`]);
    } else if (event.type === "submission") {
      notify("warning", `检测到真实提交安全事件: ${(event.data as Record<string, unknown>)?.alpha_id || "未知"}`);
    }
  }, [notify]);

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const handleStreamExhausted = useCallback(() => {
    const message = "页面暂时收不到最新进度，系统已安全停止本次验证。";
    notify("warning", message);
    failMonitor(message);
    void cancelAmbiguousJob("sse_exhausted", message);
  }, [cancelAmbiguousJob, failMonitor, notify]);

  const { connected } = useSSE(sseUrl, { onEvent: handleSSEEvent, onExhausted: handleStreamExhausted });

  const startJob = useCallback(async (resume = false) => {
    autoCancelRequests.current.clear(); setPollFailures(0); setProgressError(null);
    setStatus({
      job_id: "", task_id: "", status: "running", phase: "queued",
      progress: { phase: "queued", status_message: "正在启动非提交流水线验证。", percent_complete: 0 },
    });
    setRunning(true);
    const result = await api.call<{ job_id: string }>("/api/run", {
      method: "POST", body: JSON.stringify(buildRunPayload(resume, credentials)),
    });
    const jid = String(result?.job_id || "");
    if (result?.ok && jid) {
      setJobId(jid); setRunning(true); setPollFailures(0); setProgressError(null);
      setStatus({ job_id: jid, task_id: jid, status: "running", phase: "queued",
        progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 } });
      notify("info", `${resume ? "非提交续跑" : "非提交验证"}已启动`);
    } else {
      setRunning(false); setPollFailures(0);
      const message = result?.error || (!result ? "网络错误，请检查连接后重试" : "启动验证流程失败");
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
      setJobId(null);
    }
  }, [api, credentials, notify]);

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    const stoppedJobId = jobId;
    const result = await api.call("/api/production-validation/stop", { method: "POST", body: JSON.stringify({ job_id: stoppedJobId }) });
    setRunning(false); setJobId(null);
    setStatus((prev) => ({
      ...(prev || {}), job_id: stoppedJobId,
      status: result?.ok === false ? "failed" : "stopped",
      progress: { ...(prev?.progress || {}), phase: "stopped", status_message: "验证流程已停止", percent_complete: prev?.progress?.percent_complete },
    }));
    notify(result?.ok === false ? "error" : "info", result?.ok === false ? (result.error || "停止失败") : "验证流程已停止");
  }, [api, jobId, notify]);

  const recordStatusRefreshFailure = useCallback((message: string) => {
    setPollFailures((previous) => {
      const next = previous + 1;
      if (next >= WATCHDOG_MAX_FAILURES) {
        const failure = `状态连续刷新失败，系统已安全停止本次验证: ${message}`;
        failMonitor(failure);
        void cancelAmbiguousJob("status_failed", failure);
        notify("error", failure);
      } else {
        setProgressError(`状态刷新失败: ${message}`);
      }
      return next;
    });
  }, [cancelAmbiguousJob, failMonitor, notify]);

  // Polling watchdog: check job status while running
  useEffect(() => {
    if (!running || !jobId) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(`/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`);
      if (result?.status && isTerminalStatus(result.status)) {
        setStatus(result); setRunning(false);
        if (result.status === "failed") {
          const msg = result.error || result.progress?.status_message || "验证流程失败。";
          setProgressError(msg);
          if (result.phase === "watchdog_failed" || result.progress?.phase === "watchdog_failed") void cancelAmbiguousJob("watchdog_failed", msg, result.job_id || jobId);
          notify("error", msg);
        }
        setJobId(null);
      } else if (result?.ok) {
        setStatus(result); setPollFailures(0);
      } else if (result) {
        recordStatusRefreshFailure(result.error || result.error_code || "状态刷新失败");
      } else {
        recordStatusRefreshFailure("状态刷新失败或网络中断");
      }
    }, WATCHDOG_POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [running, jobId, api, cancelAmbiguousJob, failMonitor, notify, recordStatusRefreshFailure]);

  return {
    jobId, running, status, progress, error: progressError, connected, events,
    startJob, stopJob,
  };
}
