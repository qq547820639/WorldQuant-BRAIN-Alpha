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
 * If the user takes no action within 60s, auto-cancellation takes effect.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { cancelResultEventMessage, requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useSSE } from "@/hooks/useSSE";
import { useApi } from "@/hooks/useApi";
import { buildRunPayload, classifyJobState, jobStatusMessage, resolveJobEventState, hasCredentials } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress } from "@/types";
import { reportIgnoredError } from "@/utils/reportIgnoredError";
import { saveResumeState } from "@/utils/resumeState";

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

const WATCHDOG_POLL_INTERVAL = 2000;
// P0-1 fix: raised from 3 to 12 (~24s tolerance at 2s polls) to prevent
// premature job cancellation during long BRAIN backtest/simulation runs.
const WATCHDOG_MAX_FAILURES = 12;
const SESSION_KEY_JOB_ID = "brain_alpha_active_job_id";
const TRANSIENT_STATUS_REFRESH_PREFIX = "状态刷新失败:";
// P2-21 fix: recovery timeout so a stalled status call during session
// recovery does not leave the user stuck forever.
const RECOVERY_TIMEOUT_MS = 8000;
// P0-2: auto-cancel after 60s of no user response in disconnected state
const DISCONNECTED_AUTO_CANCEL_MS = 60000;

// P1-2: helper to send browser notification when page is hidden
function sendCompletionNotification(title: string, body: string): void {
  try {
    if (document.hidden && Notification.permission === "granted") {
      new Notification(title, { body });
    }
  } catch { console.warn("useJobState: Notification API not available"); }
}

// P1-2: request notification permission (call on user gesture like startJob)
function requestNotificationPermission(): void {
  try {
    if (Notification.permission === "default") {
      Notification.requestPermission();
    }
  } catch { console.warn("useJobState: Notification API not available"); }
}

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
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
    action?: { label: string; onClick: () => void },
  ) => void,
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
  // P0-2: disconnected state — true when waiting for user confirmation
  const [disconnected, setDisconnected] = useState(false);
  const autoCancelRequests = useRef<Set<string>>(new Set());
  const disconnectedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disconnectedNotifyRef = useRef(false);
  // P3-2: ref to track current jobId so the retry timer closure always sees
  // the latest value.
  const jobIdRef = useRef<string | null>(null);
  const api = useApi();

  // P3-2: keep jobIdRef in sync with current jobId for the retry timer closure.
  useEffect(() => {
    jobIdRef.current = jobId;
  }, [jobId]);

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
    setEvents((prev) => [...prev, "正在检查任务状态…"]);

    void (async () => {
      // Step 1: Check job status from backend
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
        setEvents((prev) => [...prev, "任务状态已失效，已清除挂起的任务会话。"]);
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
        setEvents((prev) => [...prev, resultState.failed ? "恢复检查完成：上次任务已失败。" : "恢复检查完成：上次任务已结束。"]);
        return;
      }
      // Step 2: Still running — reconnect SSE
      setEvents((prev) => [...prev, "正在重新连接 SSE 进度流…"]);
      window.clearTimeout(recoveryTimer);
      setJobId(savedId);
      setRunning(true);
      setStatus(result);
      setPollFailures(0);
      window.clearTimeout(recoveryTimer);
      setEvents((prev) => [...prev, "正在恢复任务上下文…"]);
      saveResumeState({ lastPipelineJob: savedId, lastPhase: "evaluate", lastConnectionOk: true });
      notify("info", "已恢复正在运行的任务。");
      setEvents((prev) => [...prev, "任务会话已恢复，正在监听进度。"]);
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
    // P0-4: save error state so user can resume on next visit
    saveResumeState({ lastError: message, lastConnectionOk: false, lastPipelineJob: null });
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
      // P0-4: save resume state on terminal events
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
        // P1-2: send browser notification if page hidden
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
    } else if (event.type === "progress") {
      setPollFailures(0);
      clearTransientProgressError();
      // P0-4: update resume state with cycle progress if available
      const progressData = event.progress || (event.data as Record<string, unknown>);
      const currentCycle = typeof progressData?.current === "number" ? progressData.current : undefined;
      const totalCycles = typeof progressData?.total === "number" ? progressData.total : undefined;
      if (currentCycle != null && currentCycle > 0) {
        saveResumeState({
          totalCyclesCompleted: currentCycle,
          lastPhase: "evaluate",
          lastConnectionOk: true,
        });
      }
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

  // P0-2 helper: enter the "disconnected" state with user-prompted cancellation
  const enterDisconnectedState = useCallback((trigger: "sse_exhausted" | "polling_watchdog") => {
    if (disconnected) return; // already in disconnected state
    setDisconnected(true);
    disconnectedNotifyRef.current = true;

    const message = trigger === "sse_exhausted"
      ? "检测到 SSE 连接中断（已与服务器失去联系超过 40 秒）。BRAIN 平台上的任务可能仍在运行。要终止并重试，还是继续等待自动重连？"
      : "状态连续刷新失败（已与服务器失去联系超过 24 秒）。BRAIN 平台上的任务可能仍在运行。要终止并重试，还是继续等待自动重连？";

    const cancelFn = () => {
      clearDisconnectedTimer();
      setDisconnected(false);
      disconnectedNotifyRef.current = false;
      const failureMsg = trigger === "sse_exhausted"
        ? "页面暂时收不到最新进度，用户确认终止。"
        : "状态连续刷新失败，用户确认终止。";
      failMonitor(failureMsg);
      void cancelAmbiguousJob(
        trigger === "sse_exhausted" ? "sse_exhausted" : "status_failed",
        failureMsg,
      );
      notify("error", "BRAIN 平台任务已被终止。");
    };

    const resumeFn = () => {
      clearDisconnectedTimer();
      setDisconnected(false);
      disconnectedNotifyRef.current = false;
      // Reset watchdog counter so it starts fresh
      setPollFailures(0);
      setProgressError(null);
      setRunning(true);
      notify("info", "已恢复等待。系统将继续尝试重连…");
    };

    notify("warning", message, { label: "终止重试", onClick: cancelFn });
    // P0-2: also show the "continue waiting" button as a second toast
    notify("info", "点击「继续等待」重置倒计时，系统将继续尝试重连。", { label: "继续等待", onClick: resumeFn });

    // Start the 60s auto-cancel timer
    disconnectedTimerRef.current = setTimeout(async () => {
      if (!disconnectedNotifyRef.current) return;
      // P3-2: before auto-cancelling, check if the job is still running on
      // the backend.  If it is, just reconnect SSE instead of cancelling.
      const jid = jobIdRef.current || status?.job_id;
      if (jid) {
        try {
          const statusResult = await api.call<{ status?: string; ok?: boolean }>(
            `/api/status?job_id=${encodeURIComponent(jid)}`,
          );
          if (statusResult?.ok && statusResult?.status === "running") {
            // Job is still alive — reconnect SSE without restarting.
            setJobId(jid);
            setRunning(true);
            setPollFailures(0);
            setDisconnected(false);
            disconnectedNotifyRef.current = false;
            setProgressError(null);
            notify("info", "任务仍在运行，已重新连接 SSE 进度流。");
            return;
          }
        } catch { console.warn("useJobState: status check failed, falling through"); }
      }
      const autoMsg = trigger === "sse_exhausted"
        ? "连接中断超过 60 秒未响应，自动终止 BRAIN 平台任务。"
        : "状态刷新失败超过 60 秒未响应，自动终止 BRAIN 平台任务。";
      failMonitor(autoMsg);
      void cancelAmbiguousJob(
        trigger === "sse_exhausted" ? "sse_exhausted" : "status_failed",
        autoMsg,
      );
      setDisconnected(false);
      disconnectedNotifyRef.current = false;
      notify("error", autoMsg);
    }, DISCONNECTED_AUTO_CANCEL_MS);
  }, [cancelAmbiguousJob, disconnected, failMonitor, notify, api, status?.job_id]);

  const clearDisconnectedTimer = useCallback(() => {
    if (disconnectedTimerRef.current) {
      clearTimeout(disconnectedTimerRef.current);
      disconnectedTimerRef.current = null;
    }
  }, []);

  // P0-2: resumeWatchdog — user chose to continue waiting
  const resumeWatchdog = useCallback(() => {
    if (!disconnected) return;
    clearDisconnectedTimer();
    setDisconnected(false);
    disconnectedNotifyRef.current = false;
    setPollFailures(0);
    setProgressError(null);
    setRunning(true);
    notify("info", "已恢复等待。系统将继续尝试重连…");
  }, [disconnected, clearDisconnectedTimer, notify]);

  // P0-2: forceCancelDisconnected — user chose to terminate
  const forceCancelDisconnected = useCallback(() => {
    if (!disconnected) return;
    clearDisconnectedTimer();
    const failureMsg = "用户确认终止连接中断的任务。";
    failMonitor(failureMsg);
    void cancelAmbiguousJob("sse_exhausted", failureMsg);
    setDisconnected(false);
    disconnectedNotifyRef.current = false;
    notify("error", "BRAIN 平台任务已被终止。");
  }, [disconnected, clearDisconnectedTimer, cancelAmbiguousJob, failMonitor, notify]);

  const handleStreamExhausted = useCallback(() => {
    // P0-2: enter disconnected state instead of immediately cancelling
    enterDisconnectedState("sse_exhausted");
  }, [enterDisconnectedState]);

  const { connected, reconnectAttempts } = useSSE(sseUrl, { onEvent: handleSSEEvent, onExhausted: handleStreamExhausted });

  const startJob = useCallback(async (resume = false) => {
    // P1-2: request notification permission on user gesture
    requestNotificationPermission();

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
    // P0-2: clear any disconnected state when starting a new job
    clearDisconnectedTimer();
    setDisconnected(false);
    disconnectedNotifyRef.current = false;
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
        // P0-2: enter disconnected state instead of immediately cancelling
        enterDisconnectedState("polling_watchdog");
      } else {
        setProgressError(`状态刷新失败: ${message}`);
      }
      return next;
    });
  }, [enterDisconnectedState]);

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
          // P0-4: save error state on failure
          saveResumeState({ lastError: msg, lastConnectionOk: false, lastPipelineJob: null });
          notify(resultState.interrupted ? "warning" : "error", msg);
        } else {
          setProgressError(null);
          // P0-4: save success state — clear error, bump cycle count
          saveResumeState({
            lastError: null,
            lastConnectionOk: true,
            lastPipelineJob: null,
            totalCyclesCompleted: (result.cycle ?? 0) > 0 ? result.cycle : undefined,
          });
          // P1-2: send browser notification if page hidden
          sendCompletionNotification("BRAIN Alpha Ops", "管线运行完成！");
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

  // P0-2: Cleanup disconnected timer on unmount
  useEffect(() => {
    return () => {
      if (disconnectedTimerRef.current) {
        clearTimeout(disconnectedTimerRef.current);
      }
    };
  }, []);

  return {
    jobId, running, status, progress, error: progressError, connected, events,
    recovering, reconnectAttempts,
    disconnected,
    startJob, stopJob,
    resumeWatchdog,
    forceCancelDisconnected,
  };
}
