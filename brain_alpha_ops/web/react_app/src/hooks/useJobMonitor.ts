import { useState, useEffect, useCallback, useRef } from "react";
import { cancelResultEventMessage, requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, classifyJobState, hasCredentials, jobStatusMessage, resolveJobEventState } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress, SSECandidateEventData } from "@/types";
import { isSSECandidateData } from "@/types";

const TRANSIENT_STATUS_REFRESH_PREFIX = "状态刷新失败:";

export interface UseJobMonitorOptions {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
}

export interface UseJobMonitorResult {
  jobId: string | null;
  status: JobStatus | null;
  running: boolean;
  connected: boolean;
  progress: UnifiedProgress | null;
  error: string | null;
  events: string[];
  loading: boolean;
  reconnectAttempts: number;
  sseRetryExhausted: boolean;
  sseRetryCountdown: number;
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
  onSseExhaustedRetry: () => void;
}

export function useJobMonitor({ notify, credentials }: UseJobMonitorOptions): UseJobMonitorResult {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);

  const sseRetryCountRef = useRef(0);
  const sseRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sseRetryCountdown, setSseRetryCountdown] = useState(0);
  const [sseRetryExhausted, setSseRetryExhausted] = useState(false);
  const sseRetryCountdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const SSE_RETRY_DELAYS = [5000, 10000, 20000];
  const SSE_MAX_RETRIES = SSE_RETRY_DELAYS.length;

  const clearSseRetryTimers = useCallback(() => {
    if (sseRetryTimerRef.current) {
      clearTimeout(sseRetryTimerRef.current);
      sseRetryTimerRef.current = null;
    }
    if (sseRetryCountdownIntervalRef.current) {
      clearInterval(sseRetryCountdownIntervalRef.current);
      sseRetryCountdownIntervalRef.current = null;
    }
  }, []);

  const [pollFailures, setPollFailures] = useState(0);
  const autoCancelRequests = useRef<Set<string>>(new Set());
  const api = useApi();
  const startJobRef = useRef<((resume?: boolean) => Promise<void>) | null>(null);

  const clearTransientProgressError = useCallback(() => {
    setProgressError((current) => (
      current?.startsWith(TRANSIENT_STATUS_REFRESH_PREFIX) ? null : current
    ));
  }, []);

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
    setEvents((prev) => [...prev.slice(-50), cancelResultEventMessage(result)]);
    return result;
  }, [jobId, status?.job_id]);

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    const eventOutcome = resolveJobEventState(event, event.progress || event.data, {
      failed: "验证流程错误",
      interrupted: "验证流程已停止，结果未确认完成。",
      success: "验证流程已完成",
    });
    if (eventOutcome.terminal) {
      setRunning(false); setPollFailures(0); setJobId(null);
      const eventFailed = eventOutcome.kind === "failed";
      const eventInterrupted = eventOutcome.kind === "interrupted";
      const nextStatus: JobStatus["status"] = eventOutcome.nextStatus;
      if (eventFailed || eventInterrupted) {
        const message = eventOutcome.message;
        setProgressError(message);
        setEvents((prev) => [...prev, eventInterrupted ? message : `错误: ${message}`]);
        notify(eventOutcome.notifyType, message);
      } else {
        setProgressError(null);
        notify(eventOutcome.notifyType, eventOutcome.message);
        setEvents((prev) => [...prev, eventOutcome.message]);
      }
      setStatus((prev) => prev ? {
        ...prev,
        job_id: event.job_id || event.task_id || prev.job_id,
        task_id: event.task_id || event.job_id || prev.task_id,
        status: nextStatus,
        phase: event.phase || event.progress?.phase || prev.phase,
        result: event.result,
        error: eventFailed || eventInterrupted ? eventOutcome.message : prev.error,
        progress: event.progress || prev.progress,
      } : {
        job_id: event.job_id || event.task_id || "",
        task_id: event.task_id || event.job_id,
        status: nextStatus,
        phase: event.phase || event.progress?.phase,
        result: event.result,
        error: eventFailed || eventInterrupted ? eventOutcome.message : undefined,
        progress: event.progress || (event.data as JobStatus["progress"]),
      });
    } else if (event.type === "progress") {
      setPollFailures(0);
      clearTransientProgressError();
      setStatus((prev) => ({
        ...(prev || { job_id: event.job_id || event.task_id || "", status: "running" }),
        job_id: event.job_id || event.task_id || prev?.job_id || "",
        task_id: event.task_id || event.job_id || prev?.task_id,
        status: "running", phase: event.phase || event.progress?.phase || prev?.phase,
        percent_complete: event.percent_complete, eta_seconds: event.eta_seconds,
        status_message: event.status_message,
        progress: event.progress || (event.data as JobStatus["progress"]),
      }));
    } else if (event.type === "candidate") {
      const d = isSSECandidateData(event.data) ? event.data : ({} as SSECandidateEventData);
      setEvents((prev) => [...prev.slice(-50), `候选 ${d.alpha_id || "?"} 得分 ${d.score || 0}`]);
    } else if (event.type === "submission") {
      const d = isSSECandidateData(event.data) ? event.data : ({} as SSECandidateEventData);
      notify("warning", `检测到真实提交安全事件: ${d.alpha_id || "未知"}`);
      setEvents((prev) => [...prev.slice(-50), `真实提交安全事件 ${d.alpha_id || "?"}`]);
    }
  }, [clearTransientProgressError, notify]);

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;

  const handleStreamExhausted = useCallback(() => {
    const retryCount = sseRetryCountRef.current;
    if (retryCount < SSE_MAX_RETRIES) {
      sseRetryCountRef.current = retryCount + 1;
      const delay = SSE_RETRY_DELAYS[retryCount];
      const delaySeconds = Math.ceil(delay / 1000);
      setSseRetryCountdown(delaySeconds);
      notify("warning", `同步进度通道中断，${delaySeconds}秒后自动重试 (${retryCount + 1}/${SSE_MAX_RETRIES})`);

      sseRetryCountdownIntervalRef.current = setInterval(() => {
        setSseRetryCountdown((c) => {
          if (c <= 1) {
            if (sseRetryCountdownIntervalRef.current) {
              clearInterval(sseRetryCountdownIntervalRef.current);
              sseRetryCountdownIntervalRef.current = null;
            }
            return 0;
          }
          return c - 1;
        });
      }, 1000);

      sseRetryTimerRef.current = setTimeout(() => {
        sseRetryTimerRef.current = null;
        setSseRetryCountdown(0);
        void startJobRef.current?.(true);
      }, delay);
      return;
    }

    sseRetryCountRef.current = 0;
    setSseRetryCountdown(0);
    setSseRetryExhausted(true);
    const msg = `同步进度通道已中断 ${SSE_MAX_RETRIES} 次自动重试均未恢复，正在请求自动中断。`;
    notify("warning", msg);
    failMonitor(msg);
    void cancelAmbiguousJob("sse_exhausted", msg);
  }, [cancelAmbiguousJob, failMonitor, notify]);

  const handleSseExhaustedManualRetry = useCallback(() => {
    sseRetryCountRef.current = 0;
    setSseRetryExhausted(false);
    setSseRetryCountdown(0);
    clearSseRetryTimers();
    void startJobRef.current?.(true);
  }, [clearSseRetryTimers]);

  const { connected, reconnectAttempts } = useSSE(sseUrl, { onEvent: handleSSEEvent, onExhausted: handleStreamExhausted });

  const startJob = useCallback(async (resume = false) => {
    if (!hasCredentials(credentials)) notify("info", "未填写页面凭证，将使用维护者配置的托管凭证启动非提交验证。");
    setRunning(true); autoCancelRequests.current.clear(); setPollFailures(0); setProgressError(null);
    sseRetryCountRef.current = 0;
    setSseRetryCountdown(0);
    setSseRetryExhausted(false);
    clearSseRetryTimers();
    setStatus({ job_id: "", task_id: "", status: "running", phase: "queued", progress: { phase: "queued", status_message: "正在启动非提交流水线验证。", percent_complete: 0 } });
    const result = await api.call<{ job_id: string }>("/api/run", { method: "POST", body: JSON.stringify(buildRunPayload(resume, credentials)) });
    const jid = String(result?.job_id || "");
    if (result?.ok && jid) {
      setJobId(jid); setRunning(true); setPollFailures(0); setProgressError(null);
      setStatus({ job_id: jid, task_id: jid, status: "running", phase: "queued", progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 } });
      notify("info", `${resume ? "非提交续跑" : "非提交验证"}已启动`);
    } else {
      setRunning(false); setPollFailures(0);
      const message = result ? jobStatusMessage(result, "启动验证流程失败") : "网络错误，请检查连接后重试";
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
      setJobId(null);
    }
  }, [api, credentials, notify]);

  startJobRef.current = startJob;

  const stopJob = useCallback(async () => {
    if (!jobId) return;
    const stoppedJobId = jobId;
    const result = await api.call<{ ok?: boolean; error?: string; error_code?: string }>("/api/production-validation/stop", { method: "POST", body: JSON.stringify({ job_id: stoppedJobId }) });
    if (!result || result.ok === false) {
      const message = result ? jobStatusMessage(result, "停止请求失败，后台状态仍未确认。") : "停止请求失败，后台状态仍未确认。";
      setProgressError(message);
      setStatus((prev) => ({
        ...(prev || {}), job_id: stoppedJobId,
        status: "running",
        progress: {
          ...(prev?.progress || {}),
          phase: prev?.progress?.phase || prev?.phase || "running",
          status_message: message,
          percent_complete: prev?.progress?.percent_complete,
        },
      }));
      setEvents((prev) => [...prev.slice(-50), `停止失败: ${message}`]);
      notify("error", message);
      return;
    }
    setRunning(false);
    setStatus((prev) => ({
      ...(prev || {}), job_id: stoppedJobId,
      status: "stopped",
      progress: { ...(prev?.progress || {}), phase: "stopped", status_message: "验证流程已停止", percent_complete: prev?.progress?.percent_complete },
    }));
    setProgressError(null);
    setEvents((prev) => [...prev.slice(-50), "停止请求已发送"]);
    notify("info", "验证流程已停止");
  }, [api, jobId, notify]);

  const recordStatusRefreshFailure = useCallback((message: string) => {
    setPollFailures((previous) => {
      const next = previous + 1;
      if (next >= 12) {
        const failure = `状态连续刷新失败，本次验证状态不明确，正在请求自动中断: ${message}`;
        failMonitor(failure);
        void cancelAmbiguousJob("status_failed", failure);
        notify("error", failure);
      } else {
        setProgressError(`状态刷新失败: ${message}`);
        setEvents((prev) => [...prev.slice(-50), `状态刷新失败: ${message}`]);
      }
      return next;
    });
  }, [cancelAmbiguousJob, failMonitor, notify]);

  useEffect(() => {
    if (!running || !jobId) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(`/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`);
      const resultState = classifyJobState(result);
      if (result?.status && resultState.terminal) {
        setStatus(result); setPollFailures(0); setRunning(false);
        if (resultState.failed || resultState.missing || resultState.interrupted) {
          const msg = jobStatusMessage(result, resultState.interrupted ? "验证流程已停止，结果未确认完成。" : "验证流程失败。");
          setProgressError(msg); setEvents((prev) => [...prev.slice(-50), `验证流程失败: ${msg}`]);
          if (result.phase === "watchdog_failed" || result.progress?.phase === "watchdog_failed") void cancelAmbiguousJob("watchdog_failed", msg, result.job_id || jobId);
          notify(resultState.interrupted ? "warning" : "error", msg);
        } else {
          setProgressError(null);
        }
        setJobId(null);
      } else if (result?.ok) {
        clearTransientProgressError();
        setStatus(result); setPollFailures(0);
      } else if (result) {
        recordStatusRefreshFailure(jobStatusMessage(result, "状态刷新失败"));
      } else {
        recordStatusRefreshFailure("状态刷新失败或网络中断");
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, jobId, api, cancelAmbiguousJob, clearTransientProgressError, failMonitor, notify, recordStatusRefreshFailure]);

  useEffect(() => {
    return () => {
      clearSseRetryTimers();
    };
  }, [clearSseRetryTimers]);

  const cycleProgress = status?.cycle && status?.max_cycles ? Math.round((status.cycle / status.max_cycles) * 100) : 0;
  const progress = status?.progress || { phase: status?.phase, percent_complete: status?.percent_complete ?? cycleProgress, eta_seconds: status?.eta_seconds, status_message: status?.status_message };

  return {
    jobId,
    status,
    running,
    connected,
    progress,
    error: progressError,
    events,
    loading: api.loading,
    reconnectAttempts,
    sseRetryExhausted,
    sseRetryCountdown,
    startJob,
    stopJob,
    onSseExhaustedRetry: handleSseExhaustedManualRetry,
  };
}
