/**
 * useJobState — App-level job state hook
 *
 * Lifts job monitoring state out of JobMonitor so it persists across page navigation.
 * The TopBar can display a running minibar, and any page can check job progress.
 *
 * Persistence: jobId is saved to sessionStorage so that page refresh or accidental
 * tab close can recover the running job when the page reopens (within the same
 * browser session).
 *
 * P0-2: When SSE stream exhausts or the polling watchdog fires, the hook now
 * sets a "disconnected" state instead of immediately cancelling the BRAIN job.
 * The user is shown a persistent toast with [继续等待] / [终止重试] buttons.
 * If the user takes no action within 5 minutes, auto-cancellation takes effect.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { cancelResultEventMessage, requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, classifyJobState, jobStatusMessage, resolveJobEventState, hasCredentials } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress } from "@/types";
import { saveResumeState } from "@/utils/resumeState";
import { useJobRecovery, saveJobId as saveSessionJobId, clearSavedJobId } from "@/hooks/useJobRecovery";
import { useJobSseConnection } from "@/hooks/useJobSseConnection";
import { useJobWatchdog } from "@/hooks/useJobWatchdog";
import { useJobDisconnectedState } from "@/hooks/useJobDisconnectedState";

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
  /** P0-2: True when the stream/polling watchdog has detected a disconnect and
   *  is waiting for user confirmation before cancelling the BRAIN job. */
  disconnected: boolean;
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
  /** P0-2: Reset the watchdog counter and resume waiting for reconnection. */
  resumeWatchdog: () => void;
  /** P0-2: Immediately cancel the ambiguous BRAIN job (user confirmed). */
  forceCancelDisconnected: () => void;
}

const TRANSIENT_STATUS_REFRESH_PREFIX = "状态刷新失败:";

function sendCompletionNotification(title: string, body: string): void {
  try {
    if (document.hidden && Notification.permission === "granted") {
      new Notification(title, { body });
    }
  } catch { console.warn("useJobState: Notification API not available"); }
}

function requestNotificationPermission(): void {
  try {
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  } catch { console.warn("useJobState: Notification API not available"); }
}

export function useJobState(
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
    action?: { label: string; onClick: () => void },
    secondaryAction?: { label: string; onClick: () => void },
  ) => void,
  credentials?: BrainCredentials,
): JobState {
  const [jobId, setJobId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [progressError, setProgressError] = useState<string | null>(null);
  const [events, setEvents] = useState<string[]>([]);
  const [pollFailures, setPollFailures] = useState(0);
  const jobIdRef = useRef<string | null>(null);
  const api = useApi();

  useEffect(() => { jobIdRef.current = jobId; }, [jobId]);

  const clearTransientProgressError = useCallback(() => {
    setProgressError((current) =>
      current?.startsWith(TRANSIENT_STATUS_REFRESH_PREFIX) ? null : current,
    );
  }, []);

  const progress = useMemo((): UnifiedProgress => status?.progress || {
    phase: status?.phase,
    percent_complete: status?.percent_complete,
    eta_seconds: status?.eta_seconds,
    status_message: status?.status_message,
  }, [status]);

  const addEvent = useCallback((msg: string) => {
    setEvents((prev) => [...prev.slice(-999), msg]);
  }, []);

  const addEventSlice = useCallback((msg: string) => {
    setEvents((prev) => [...prev.slice(-50), msg]);
  }, []);

  const failMonitor = useCallback((message: string) => {
    clearSavedJobId();
    setRunning(false);
    setProgressError(message);
    setStatus((prev) => prev ? {
      ...prev, status: "failed", phase: "watchdog_failed", error: message,
      progress: { ...(prev.progress || {}), phase: "watchdog_failed", status_message: message, percent_complete: 100 },
    } : prev);
    setEvents((prev) => [...prev.slice(-50), message]);
    saveResumeState({ lastError: message, lastConnectionOk: false, lastPipelineJob: null });
  }, []);

  const cancelAmbiguousJob = useCallback(async (reason: CancelReason, message: string, targetJobId?: string | null) => {
    const id = targetJobId || jobId || status?.job_id;
    if (!id) return null;
    const result = await requestJobCancel({ jobId: id, reason, message });
    addEventSlice(cancelResultEventMessage(result));
    return result;
  }, [jobId, status?.job_id, addEventSlice]);

  // ── Sub-hook: disconnected state ─────────────────────────────────────
  const onReconnect = useCallback(() => {
    setPollFailures(0);
    setProgressError(null);
    setRunning(true);
  }, []);

  const {
    disconnected,
    enterDisconnectedState,
    resumeWatchdog,
    forceCancelDisconnected,
    clearDisconnectedTimer,
    setDisconnected,
  } = useJobDisconnectedState({
    notify,
    failMonitor,
    cancelAmbiguousJob,
    onReconnect,
  });

  // ── Sub-hook: session recovery ───────────────────────────────────────
  const onRecovered = useCallback((savedId: string, result: JobStatus) => {
    setJobId(savedId);
    setRunning(true);
    setStatus(result);
    setPollFailures(0);
  }, []);

  const onTerminalRecovery = useCallback((result: JobStatus) => {
    const resultState = classifyJobState(result);
    setStatus(result);
    if (resultState.failed || resultState.missing || resultState.interrupted) {
      const message = jobStatusMessage(result, resultState.interrupted ? "上次任务已停止，结果未确认完成。" : "任务在您离开期间失败。");
      setProgressError(message);
      notify(resultState.interrupted ? "warning" : "error", resultState.interrupted ? "上次任务已停止。" : "上次任务已失败。");
    } else {
      notify("info", "上次任务已完成。");
    }
  }, [notify]);

  const { recovering } = useJobRecovery({
    notify,
    callApi: api.call,
    onRecovered,
    onTerminal: onTerminalRecovery,
    addEvent,
  });

  // ── Sub-hook: SSE connection ─────────────────────────────────────────
  const onSseTerminal = useCallback((event: SSEEvent, eventOutcome: ReturnType<typeof resolveJobEventState>) => {
    clearSavedJobId();
    setRunning(false);
    setPollFailures(0);
    setJobId(null);
    const eventFailed = eventOutcome.kind === "failed";
    const eventInterrupted = eventOutcome.kind === "interrupted";
    const nextStatus: JobStatus["status"] = eventOutcome.nextStatus;
    if (eventFailed || eventInterrupted) {
      saveResumeState({ lastError: eventOutcome.message, lastConnectionOk: false });
    } else {
      saveResumeState({ lastError: null, lastConnectionOk: true });
    }
    if (eventFailed || eventInterrupted) {
      const message = eventOutcome.message;
      setProgressError(message);
      setEvents((prev) => [...prev, eventInterrupted ? message : `错误: ${message}`]);
      notify(eventOutcome.notifyType, message);
    } else {
      setProgressError(null);
      notify(eventOutcome.notifyType, eventOutcome.message);
      setEvents((prev) => [...prev, eventOutcome.message]);
      sendCompletionNotification("BRAIN Alpha Ops", "管线运行完成！");
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
  }, [notify]);

  const onSseProgress = useCallback((event: SSEEvent) => {
    saveResumeState({
      totalCyclesCompleted: typeof event.progress?.current === "number" && event.progress.current > 0
        ? event.progress.current : undefined,
      lastPhase: "evaluate",
      lastConnectionOk: true,
    });
    setStatus((prev) => ({
      ...(prev || { job_id: event.job_id || event.task_id || "", status: "running" }),
      job_id: event.job_id || event.task_id || prev?.job_id || "",
      task_id: event.task_id || event.job_id || prev?.task_id,
      status: "running", phase: event.phase || event.progress?.phase || prev?.phase,
      percent_complete: event.percent_complete, eta_seconds: event.eta_seconds,
      status_message: event.status_message,
      progress: event.progress || (event.data as JobStatus["progress"]),
    }));
  }, []);

  const onSseCandidate = useCallback((alphaId: string) => {
    addEventSlice(`候选 ${alphaId}`);
  }, [addEventSlice]);

  const onSseSubmission = useCallback((alphaId: string) => {
    notify("warning", `检测到真实提交安全事件: ${alphaId}`);
  }, [notify]);

  const onSseExhausted = useCallback(() => {
    enterDisconnectedState("sse_exhausted", {
      jobId: jobIdRef.current,
      callApi: api.call,
      failMonitor,
      cancelAmbiguousJob,
      reconnectJob: (jid: string) => {
        setJobId(jid);
        setRunning(true);
        setPollFailures(0);
        setProgressError(null);
      },
      notify,
    });
  }, [enterDisconnectedState, failMonitor, cancelAmbiguousJob, notify, api.call]);

  const { connected, reconnectAttempts } = useJobSseConnection(jobId, {
    notify,
    onTerminal: onSseTerminal,
    onProgress: onSseProgress,
    onCandidate: onSseCandidate,
    onSubmission: onSseSubmission,
    onExhausted: onSseExhausted,
    setPollFailures,
    clearTransientProgressError,
  });

  // ── Sub-hook: polling watchdog ───────────────────────────────────────
  const onWatchdogTerminal = useCallback((result: JobStatus) => {
    clearSavedJobId();
    setStatus(result);
    setRunning(false);
    setJobId(null);
  }, []);

  const onWatchdogProgress = useCallback((result: JobStatus) => {
    setStatus(result);
  }, []);

  useJobWatchdog(running, jobId, connected, {
    pollFailures,
    setPollFailures,
    callApi: api.call,
    notify,
    cancelAmbiguousJob,
    onTerminal: onWatchdogTerminal,
    onProgressUpdate: onWatchdogProgress,
    clearTransientProgressError,
  });

  // P0-2: trigger disconnected when pollFailures hits threshold
  useEffect(() => {
    if (pollFailures >= 12) {
      enterDisconnectedState("polling_watchdog", {
        jobId: jobIdRef.current,
        callApi: api.call,
        failMonitor,
        cancelAmbiguousJob,
        reconnectJob: (jid: string) => {
          setJobId(jid);
          setRunning(true);
          setPollFailures(0);
          setProgressError(null);
        },
        notify,
      });
    }
  }, [pollFailures, enterDisconnectedState, failMonitor, cancelAmbiguousJob, notify, api.call]);

  // ── startJob ─────────────────────────────────────────────────────────
  const startJob = useCallback(async (resume = false) => {
    requestNotificationPermission();

    if (!hasCredentials(credentials)) {
      const msg = "请先在左侧「连接与生产参数」面板填写 BRAIN 账户邮箱和密码，或粘贴 API Token，然后点击「测试连接」。";
      setProgressError(msg);
      setStatus((prev) => prev ? { ...prev, status: "failed", error: msg, progress: { ...(prev.progress || {}), phase: "failed", status_message: msg, percent_complete: 100 } } : prev);
      setRunning(false);
      notify("warning", msg);
      return;
    }
    setPollFailures(0);
    setProgressError(null);
    clearDisconnectedTimer();
    setDisconnected(false);
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
      setJobId(jid); saveSessionJobId(jid); setRunning(true); setPollFailures(0); setProgressError(null);
      setStatus({ job_id: jid, task_id: jid, status: "running", phase: "queued",
        progress: { phase: "queued", status_message: "非提交流水线已排队。", percent_complete: 0 } });
      saveResumeState({ lastPhase: "evaluate", lastPipelineJob: jid, lastError: null, lastConnectionOk: true });
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
  }, [api, credentials, notify, clearDisconnectedTimer, setDisconnected]);

  // ── stopJob ──────────────────────────────────────────────────────────
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

  return {
    jobId, running, status, progress, error: progressError, connected, events,
    recovering, reconnectAttempts,
    disconnected,
    startJob, stopJob,
    resumeWatchdog,
    forceCancelDisconnected,
  };
}
