import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { cancelResultEventMessage, requestJobCancel, type CancelReason } from "@/api/jobCancel";
import { useApi } from "@/hooks/useApi";
import { classifyJobState, jobStatusMessage, resolveJobEventState } from "@/helpers/runPayload";
import type { BrainCredentials, JobStatus, SSEEvent, UnifiedProgress } from "@/types";
import { saveResumeState } from "@/utils/resumeState";
import { saveJobId as saveSessionJobId, clearSavedJobId } from "@/hooks/useJobRecovery";
import { useJobRecovery } from "@/hooks/useJobRecovery";
import { useJobSseConnection } from "@/hooks/useJobSseConnection";
import { useJobWatchdog } from "@/hooks/useJobWatchdog";
import { useJobDisconnectedState } from "@/hooks/useJobDisconnectedState";
import { sendCompletionNotification } from "./useJobNotifications";

const TRANSIENT_STATUS_REFRESH_PREFIX = "状态刷新失败:";

export interface JobStatusState {
  jobId: string | null;
  running: boolean;
  status: JobStatus | null;
  progress: UnifiedProgress | null;
  error: string | null;
  connected: boolean;
  events: string[];
  recovering: boolean;
  reconnectAttempts: number;
  disconnected: boolean;
  resumeWatchdog: () => void;
  forceCancelDisconnected: () => void;
}

export interface JobStatusDeps {
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
    action?: { label: string; onClick: () => void },
    secondaryAction?: { label: string; onClick: () => void },
  ) => void;
  credentials?: BrainCredentials;
}

export interface JobStatusHandlers extends JobStatusState {
  setJobId: React.Dispatch<React.SetStateAction<string | null>>;
  setRunning: React.Dispatch<React.SetStateAction<boolean>>;
  setStatus: React.Dispatch<React.SetStateAction<JobStatus | null>>;
  setProgressError: React.Dispatch<React.SetStateAction<string | null>>;
  setEvents: React.Dispatch<React.SetStateAction<string[]>>;
  setPollFailures: React.Dispatch<React.SetStateAction<number>>;
  addEvent: (msg: string) => void;
  addEventSlice: (msg: string) => void;
  failMonitor: (message: string) => void;
  cancelAmbiguousJob: (reason: CancelReason, message: string, targetJobId?: string | null) => Promise<Awaited<ReturnType<typeof requestJobCancel>> | null>;
  clearTransientProgressError: () => void;
  clearDisconnectedTimer?: () => void;
  setDisconnected?: (disconnected: boolean) => void;
  jobIdRef: React.MutableRefObject<string | null>;
  api: ReturnType<typeof useApi>;
}

export function useJobStatus(deps: JobStatusDeps): JobStatusHandlers {
  const { notify } = deps;
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

  const onReconnect = useCallback(() => {
    setPollFailures(0);
    setProgressError(null);
    setRunning(true);
  }, []);

  const reconnectJob = useCallback((jid: string) => {
    setJobId(jid);
    setRunning(true);
    setPollFailures(0);
    setProgressError(null);
  }, []);

  const {
    disconnected,
    enterDisconnectedState,
    resumeWatchdog,
    forceCancelDisconnected,
    clearDisconnectedTimer,
    setDisconnected,
  } = useJobDisconnectedState({
    jobId,
    callApi: api.call,
    notify,
    failMonitor,
    cancelAmbiguousJob,
    reconnectJob,
    onReconnect,
  });

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
      reconnectJob,
      notify,
    });
  }, [enterDisconnectedState, failMonitor, cancelAmbiguousJob, reconnectJob, notify, api.call]);

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

  useEffect(() => {
    if (pollFailures >= 12) {
      enterDisconnectedState("polling_watchdog", {
        jobId: jobIdRef.current,
        callApi: api.call,
        failMonitor,
        cancelAmbiguousJob,
        reconnectJob,
        notify,
      });
    }
  }, [pollFailures, enterDisconnectedState, failMonitor, cancelAmbiguousJob, reconnectJob, notify, api.call]);

  return {
    jobId,
    running,
    status,
    progress,
    error: progressError,
    connected,
    events,
    recovering,
    reconnectAttempts,
    disconnected,
    resumeWatchdog,
    forceCancelDisconnected,
    setJobId,
    setRunning,
    setStatus,
    setProgressError,
    setEvents,
    setPollFailures,
    addEvent,
    addEventSlice,
    failMonitor,
    cancelAmbiguousJob,
    clearTransientProgressError,
    clearDisconnectedTimer,
    setDisconnected,
    jobIdRef,
    api,
  };
}
