/**
 * useJobState — App-level job state hook
 *
 * Lifts job monitoring state out of JobMonitor so it persists across page navigation.
 * The TopBar can display a running minibar, and any page can check job progress.
 *
 * Persistence: jobId is saved to sessionStorage so that page refresh or accidental
 * tab close can recover the running job when the page reopens (within the same
 * browser session).
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { cancelResultEventMessage, requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, classifyJobState, jobStatusMessage, resolveJobEventState, hasCredentials } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress } from "@/types";
import { reportIgnoredError } from "@/utils/reportIgnoredError";

export interface JobState {
  jobId: string | null;
  running: boolean;
  status: JobStatus | null;
  progress: UnifiedProgress | null;
  error: string | null;
  connected: boolean;
  events: string[];
  recovering: boolean;
  reconnectAttempts: number;
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
}

const WATCHDOG_POLL_INTERVAL = 2000;
// P0-1 fix: raised from 3 to 12 (~24s tolerance at 2s polls) to prevent
// premature job cancellation during long BRAIN backtest/simulation runs.
const WATCHDOG_MAX_FAILURES = 12;
const SESSION_KEY_JOB_ID = "brain_alpha_active_job_id";
const TRANSIENT_STATUS_REFRESH_PREFIX = "状态刷新失败:";
// P2-21 fix: recovery timeout so a stalled status call during session
// recovery does not leave the user stuck forever.
const RECOVERY_TIMEOUT_MS = 15000;

function saveJobId(id: string): void {
  try {
    sessionStorage.setItem(SESSION_KEY_JOB_ID, id);
  } catch (err) {
    reportIgnoredError("job state sessionStorage save failed", err);
  }
}

function loadSavedJobId(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY_JOB_ID);
  } catch (err) {
    reportIgnoredError("job state sessionStorage load failed", err);
    return null;
  }
}

function clearSavedJobId(): void {
  try {
    sessionStorage.removeItem(SESSION_KEY_JOB_ID);
  } catch (err) {
    reportIgnoredError("job state sessionStorage clear failed", err);
  }
}

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
  const [recovering, setRecovering] = useState(false);
  const [recoveryAttempted, setRecoveryAttempted] = useState(false);
  const autoCancelRequests = useRef<Set<string>>(new Set());
  const api = useApi();

  const clearTransientProgressError = useCallback(() => {
    setProgressError((current) => (
      current?.startsWith(TRANSIENT_STATUS_REFRESH_PREFIX) ? null : current
    ));
  }, []);

  const progress = useMemo((): UnifiedProgress => status?.progress || {
    phase: status?.phase,
    percent_complete: status?.percent_complete,
    eta_seconds: status?.eta_seconds,
    status_message: status?.status_message,
  }, [status]);

  // ── Session recovery: on mount, check if there was a running job ──────
  useEffect(() => {
    if (recoveryAttempted) return;
    setRecoveryAttempted(true);
    let recoveryTimedOut = false;
    const recoveryTimer = window.setTimeout(() => {
      recoveryTimedOut = true;
      clearSavedJobId();
      setRecovering(false);
      setEvents((prev) => [...prev, "恢复超时，已清除挂起的任务会话。"]);
    }, RECOVERY_TIMEOUT_MS);
    const savedId = loadSavedJobId();
    if (!savedId) {
      window.clearTimeout(recoveryTimer);
      return;
    }

    setRecovering(true);
    setEvents((prev) => [...prev, "正在恢复上次的任务状态…"]);

    void (async () => {
      const result = await api.call<JobStatus>(
        `/api/production-validation/status?job_id=${encodeURIComponent(savedId)}`,
      );
      if (recoveryTimedOut) {
        window.clearTimeout(recoveryTimer);
        return;
      }
      if (!result || !result.status) {
        // No response — job may have been cleaned up
        clearSavedJobId();
        window.clearTimeout(recoveryTimer);
        setRecovering(false);
        return;
      }
      const resultState = classifyJobState(result);
      if (resultState.terminal) {
        // Already finished — show the final result
        clearSavedJobId();
        setStatus(result);
        if (resultState.failed || resultState.missing || resultState.interrupted) {
          const message = jobStatusMessage(result, resultState.interrupted ? "上次任务已停止，结果未确认完成。" : "任务在您离开期间失败。");
          setProgressError(message);
          notify(resultState.interrupted ? "warning" : "error", resultState.interrupted ? "上次任务已停止。" : "上次任务已失败。");
        } else {
          notify("info", "上次任务已完成。");
        }
        window.clearTimeout(recoveryTimer);
        setRecovering(false);
        return;
      }
      // Still running — reconnect
      window.clearTimeout(recoveryTimer);
      setJobId(savedId);
      setRunning(true);
      setStatus(result);
      setPollFailures(0);
      window.clearTimeout(recoveryTimer);
      notify("info", "已恢复正在运行的任务。");
      setRecovering(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const failMonitor = useCallback((message: string, phase = "watchdog_failed") => {
    clearSavedJobId();
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
      clearSavedJobId();
      setRunning(false); setPollFailures(0); setJobId(null);
      const eventFailed = eventOutcome.kind === "failed";
      const eventInterrupted = eventOutcome.kind === "interrupted";
      const nextStatus: JobStatus["status"] = eventOutcome.nextStatus;
      if (eventFailed || eventInterrupted) {
        const message = eventOutcome.message;
        setProgressError(message);
        // P1-5 [C12]: Log to events only; toast is for high-level summary
        setEvents((prev) => [...prev, eventInterrupted ? message : `错误: ${message}`]);
        notify("info", eventInterrupted ? "流程已中断，详见事件日志" : "发生错误，详见事件日志");
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
      setEvents((prev) => [...prev.slice(-50), `候选 ${(event.data as Record<string, unknown>)?.alpha_id || "?"}`]);
    } else if (event.type === "submission") {
      notify("warning", `检测到真实提交安全事件: ${(event.data as Record<string, unknown>)?.alpha_id || "未知"}`);
    }
  }, [clearTransientProgressError, notify]);

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const handleStreamExhausted = useCallback(() => {
    clearSavedJobId();
    const message = "页面暂时收不到最新进度，本次验证状态不明确，正在请求自动中断。";
    notify("warning", message);
    failMonitor(message);
    void cancelAmbiguousJob("sse_exhausted", message);
  }, [cancelAmbiguousJob, failMonitor, notify]);

  const { connected, reconnectAttempts } = useSSE(sseUrl, { onEvent: handleSSEEvent, onExhausted: handleStreamExhausted });

  const startJob = useCallback(async (resume = false) => {
    // P2-23 fix: validate credentials before sending the request so the
    // user gets a clear, actionable error instead of a generic message.
    if (!hasCredentials(credentials)) {
      const msg = "请先在左侧「连接与生产参数」面板填写 BRAIN 账户邮箱和密码，或粘贴 API Token，然后点击「测试连接」。";
      setProgressError(msg);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: msg, progress: { ...(prev.progress || {}), phase: "failed", status_message: msg, percent_complete: 100 } } : prev);
      setRunning(false);
      notify("warning", msg);
      return;
    }
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
      setJobId(jid); saveJobId(jid); setRunning(true); setPollFailures(0); setProgressError(null);
      setStatus({ job_id: jid, task_id: jid, status: "running", phase: "queued",
        progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 } });
      notify("info", `${resume ? "非提交续跑" : "非提交验证"}已启动`);
    } else {
      clearSavedJobId();
      setRunning(false); setPollFailures(0);
      const message = result ? jobStatusMessage(result, "启动验证流程失败") : "网络错误，请检查连接后重试";
      setProgressError(message);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: message, progress: { ...(prev.progress || {}), phase: "failed", status_message: message, percent_complete: 100 } } : prev);
      notify("error", message);
      setJobId(null);
    }
  }, [api, credentials, notify]);

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
    clearSavedJobId();
    setRunning(false); setJobId(null);
    setStatus((prev) => ({
      ...(prev || {}), job_id: stoppedJobId,
      status: "stopped",
      progress: { ...(prev?.progress || {}), phase: "stopped", status_message: "验证流程已停止", percent_complete: prev?.progress?.percent_complete },
    }));
    setProgressError(null);
    setEvents((prev) => [...prev.slice(-50), "验证流程已停止"]);
    notify("info", "验证流程已停止");
  }, [api, jobId, notify]);

  const recordStatusRefreshFailure = useCallback((message: string) => {
    setPollFailures((previous) => {
      const next = previous + 1;
      if (next >= WATCHDOG_MAX_FAILURES) {
        clearSavedJobId();
        const failure = `状态连续刷新失败，本次验证状态不明确，正在请求自动中断: ${message}`;
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
      const resultState = classifyJobState(result);
      if (result?.status && resultState.terminal) {
        clearSavedJobId();
        setStatus(result); setRunning(false);
        if (resultState.failed || resultState.missing || resultState.interrupted) {
          const msg = jobStatusMessage(result, resultState.interrupted ? "验证流程已停止，结果未确认完成。" : "验证流程失败。");
          setProgressError(msg);
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
    }, WATCHDOG_POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [running, jobId, api, cancelAmbiguousJob, clearTransientProgressError, failMonitor, notify, recordStatusRefreshFailure]);

  return {
    jobId, running, status, progress, error: progressError, connected, events,
    recovering, reconnectAttempts,
    startJob, stopJob,
  };
}
