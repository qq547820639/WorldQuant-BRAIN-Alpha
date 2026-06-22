/** Button-driven official operations panel for browser-only user workflows. */

import { useCallback, useEffect, useRef, useState } from "react";
import { classifyJobState } from "@/helpers/runPayload";
import { useApi } from "@/hooks/useApi";
import type { BrainCredentials, CloudAlphaCache, JobStatus, OfficialContextCache, SubmitReadinessResponse } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
import {
  ActionPanel,
  OperationLog,
  OperationMetric,
  OverviewCard,
  SummaryMetric,
  SummarySections,
  SyncHistoryList,
  type OperationLogEntry,
  type OperationMode,
  type SyncRange,
  type SyncProgressMonitorState,
  POLL_INTERVAL_MS,
  SYNC_STATUS_FAILURE_LIMIT,
  SYNC_PROGRESS_STALL_WARNING_MS,
  SYNC_PROGRESS_STALL_STOP_MS,
  STOP_RETRY_AFTER_MS,
  MAX_LOG_ROWS,
  formatClock,
  formatDuration,
  formatCount,
  shortOperationId,
  credentialsPayload,
  hasPageCredentials,
  saveStoredSyncJobId,
  loadStoredSyncJobId,
  clearStoredSyncJobId,
  syncProgressMonitorSignature,
  isTerminalSyncStatus,
  operationFailureMessage,
  requestDeadline,
  syncContextStatus,
  contextCacheComplete,
  checkResultCount,
  syncStatusForDisplay,
  syncDataOverview,
  operationProgress,
  progressState,
  currentModeError,
  contextSummaryField,
  officialContextInlineSummary,
  canRetryContextOnly,
  syncHistoryReadErrorTitle,
  isSessionInvalidResult,
  numberField,
  operationStatusMessage,
} from "./OfficialOperations";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  autoStart?: boolean;
  connectionReady?: boolean;
  officialContextCache?: OfficialContextCache;
  cloudAlphaCache?: CloudAlphaCache;
  onAutoStartConsumed?: () => void;
  onSyncCompleted?: () => void;
  onReconnectRequested?: () => void;
  onNavigateToCandidates?: () => void;
}

interface CheckResultsResponse {
  items?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
  count?: number;
  ok?: boolean;
  data?: CheckResultsResponse;
}

export default function OfficialOperationsPanel({
  notify,
  credentials,
  autoStart = false,
  connectionReady = true,
  officialContextCache,
  cloudAlphaCache,
  onAutoStartConsumed,
  onSyncCompleted,
  onReconnectRequested,
  onNavigateToCandidates,
}: Props) {
  const [mode, setMode] = useState<OperationMode>("idle");
  const [syncJobId, setSyncJobId] = useState("");
  const [syncStatus, setSyncStatus] = useState<JobStatus | null>(null);
  const [syncRunning, setSyncRunning] = useState(false);
  const [syncRange, setSyncRange] = useState<SyncRange>("all");
  const [contextOnlyMode, setContextOnlyMode] = useState(false);
  const [stoppingSinceMs, setStoppingSinceMs] = useState(0);
  const [stoppingNowMs, setStoppingNowMs] = useState(0);
  const syncPollInFlightRef = useRef(false);
  const activeSyncJobIdRef = useRef("");
  const syncPollGenerationRef = useRef(0);
  const syncPollFailureCountRef = useRef(0);
  const syncProgressMonitorRef = useRef<SyncProgressMonitorState>({
    jobId: "",
    signature: "",
    sinceMs: 0,
    warned: false,
    interrupting: false,
  });
  const syncRecoveryAttemptedRef = useRef(false);
  const autoStartConsumedRef = useRef(false);
  const stopRetryStartedAtRef = useRef(0);
  const [logs, setLogs] = useState<OperationLogEntry[]>([
    {
      time: formatClock(),
      tone: "info",
      message: "官方操作已就绪。请选择要执行的操作。",
    },
  ]);

  const syncStartApi = useApi<{ job_id?: string; task_id?: string; status_url?: string }>();
  const syncStatusApi = useApi<JobStatus>();
  const syncCancelApi = useApi();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const checkResultsApi = useApi<CheckResultsResponse>();
  const callSyncStart = syncStartApi.call;
  const resetSyncStart = syncStartApi.reset;
  const callSyncStatus = syncStatusApi.call;
  const callSyncCancel = syncCancelApi.call;
  const callReadiness = readinessApi.call;
  const callCheckResults = checkResultsApi.call;

  const updateSyncJobId = useCallback((jobId: string) => {
    activeSyncJobIdRef.current = jobId;
    syncPollGenerationRef.current += 1;
    syncPollInFlightRef.current = false;
    setSyncJobId(jobId);
  }, []);

  const appendLog = useCallback((tone: OperationLogEntry["tone"], message: string) => {
    setLogs((previous) => [...previous.slice(-(MAX_LOG_ROWS - 1)), { time: formatClock(), tone, message }]);
  }, []);

  const resetSyncProgressMonitor = useCallback(() => {
    syncProgressMonitorRef.current = {
      jobId: "",
      signature: "",
      sinceMs: 0,
      warned: false,
      interrupting: false,
    };
  }, []);

  const inspectSyncProgressMonitor = useCallback((result: JobStatus) => {
    const jobId = String(result?.job_id || result?.task_id || syncJobId || "");
    const signature = syncProgressMonitorSignature(result);
    if (!jobId || !signature) {
      resetSyncProgressMonitor();
      return null;
    }
    const now = Date.now();
    const previous = syncProgressMonitorRef.current;
    if (previous.jobId !== jobId || previous.signature !== signature) {
      syncProgressMonitorRef.current = {
        jobId,
        signature,
        sinceMs: now,
        warned: false,
        interrupting: false,
      };
      return null;
    }
    const stalledMs = Math.max(0, now - previous.sinceMs);
    if (stalledMs >= SYNC_PROGRESS_STALL_STOP_MS && !previous.interrupting) {
      syncProgressMonitorRef.current = { ...previous, interrupting: true };
      return {
        level: "stop" as const,
        message: `扫描指标已 ${formatDuration(stalledMs / 1000)} 未更新，状态不明确，已自动停止本次刷新。请稍后重试或缩小同步范围。`,
      };
    }
    if (stalledMs >= SYNC_PROGRESS_STALL_WARNING_MS && !previous.warned) {
      syncProgressMonitorRef.current = { ...previous, warned: true };
      return {
        level: "warning" as const,
        message: `扫描指标已 ${formatDuration(stalledMs / 1000)} 未更新；系统会继续监控，若继续不变将自动停止本次刷新。`,
      };
    }
    return null;
  }, [resetSyncProgressMonitor, syncJobId]);

  const applySyncRecoveryFailure = useCallback((jobId: string, result: JobStatus | null) => {
    const message = operationFailureMessage(
      result,
      "本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。",
    );
    setMode("context_refresh");
    setContextOnlyMode(false);
    updateSyncJobId(jobId);
    setSyncRunning(false);
    setSyncStatus({
      job_id: jobId,
      task_id: jobId || undefined,
      status: "missing",
      phase: "session_invalid",
      error: message,
      progress: {
        job_id: jobId || undefined,
        task_id: jobId || undefined,
        phase: "session_invalid",
        status_code: "SESSION_INVALID",
        phase_label: "需要重新连接",
        status_message: message,
      },
    });
    appendLog("warning", message);
    notify("warning", message);
    return true;
  }, [appendLog, notify, updateSyncJobId]);

  const applyRecoveredSyncStatus = useCallback((result: JobStatus) => {
    const jobId = String(result?.job_id || result?.task_id || "");
    if (!jobId) return false;
    const terminal = isTerminalSyncStatus(result);
    setMode("context_refresh");
    setContextOnlyMode(Boolean(result?.progress?.context_only || (result?.result as Record<string, unknown> | undefined)?.context_only));
    updateSyncJobId(jobId);
    setSyncStatus(result);
    setSyncRunning(!terminal);
    syncPollFailureCountRef.current = 0;
    if (terminal) {
      resetSyncProgressMonitor();
      clearStoredSyncJobId();
      appendLog("info", `已恢复最近官方刷新结果: ${shortOperationId(jobId)}`);
    } else {
      saveStoredSyncJobId(jobId);
      appendLog("info", `已恢复正在运行的官方刷新: ${shortOperationId(jobId)}`);
      notify("info", "已恢复正在运行的官方上下文刷新");
    }
    return true;
  }, [appendLog, notify, resetSyncProgressMonitor, updateSyncJobId]);

  useEffect(() => {
    if (syncRecoveryAttemptedRef.current) return;
    syncRecoveryAttemptedRef.current = true;
    let active = true;
    void (async () => {
      const storedJobId = loadStoredSyncJobId();
      let storedTerminalStatus: JobStatus | null = null;
      if (storedJobId) {
        const stored = await callSyncStatus<JobStatus>(`/api/sync_status?job_id=${encodeURIComponent(storedJobId)}&compact=1`);
        if (!active) return;
        if (isSessionInvalidResult(stored)) {
          applySyncRecoveryFailure(storedJobId, stored);
          return;
        }
        if (stored?.ok && !isTerminalSyncStatus(stored) && applyRecoveredSyncStatus(stored)) return;
        clearStoredSyncJobId();
        if (stored?.ok && isTerminalSyncStatus(stored)) storedTerminalStatus = stored;
      }
      const current = await callSyncStatus<JobStatus>("/api/sync_status?compact=1");
      if (!active) return;
      if (isSessionInvalidResult(current)) {
        applySyncRecoveryFailure("", current);
        return;
      }
      if (current?.ok && applyRecoveredSyncStatus(current)) return;
      if (storedTerminalStatus) applyRecoveredSyncStatus(storedTerminalStatus);
      else if (current?.ok) {
        setSyncStatus((previous) => previous || current);
      }
    })();
    return () => {
      active = false;
    };
  }, [applyRecoveredSyncStatus, applySyncRecoveryFailure, callSyncStatus]);

  const loadReadiness = useCallback(async () => {
    setMode("readiness");
    appendLog("info", "正在读取提交前阻断复核证据。");
    const deadline = requestDeadline();
    try {
      const result = await callReadiness<SubmitReadinessResponse>("/api/submit_readiness", { signal: deadline.signal });
      if (!result?.ok) {
        const message = operationFailureMessage(result, "提交前阻断复核证据读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
        appendLog("error", message);
        notify("error", message);
        return;
      }
      const ready = Boolean((result as SubmitReadinessResponse).ready_to_submit);
      appendLog(ready ? "success" : "warning", ready ? "已检测到可进入人工复核的候选证据。" : "当前仍未达到提交前阻断复核通过标准。");
      notify(ready ? "success" : "warning", ready ? "阻断复核通过" : "阻断复核仍未通过");
    } finally {
      deadline.clear();
    }
  }, [appendLog, callReadiness, notify]);

  const loadChecks = useCallback(async () => {
    setMode("checks");
    appendLog("info", "正在读取质量检查结果。");
    const deadline = requestDeadline();
    try {
      const result = await callCheckResults<CheckResultsResponse>("/api/check_results", { signal: deadline.signal });
      if (!result?.ok) {
        const message = operationFailureMessage(result, "质量检查结果读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
        appendLog("error", message);
        notify("error", message);
        return;
      }
      appendLog("success", `质量检查结果已加载: ${checkResultCount(result)} 条。`);
      notify("success", "质量检查结果已加载");
    } finally {
      deadline.clear();
    }
  }, [appendLog, callCheckResults, notify]);

  const startOfficialContextRefresh = useCallback(async (options?: { contextOnly?: boolean }) => {
    const contextOnly = Boolean(options?.contextOnly);
    setContextOnlyMode(contextOnly);
    if (!connectionReady && !hasPageCredentials(credentials)) {
      const message = "未检测到可用 BRAIN 凭证。请先在 Dashboard 测试 BRAIN 连接，或在系统配置里填写本次会话凭证。";
      appendLog("error", message);
      notify("warning", message);
      return;
    }
    updateSyncJobId("");
    clearStoredSyncJobId();
    setMode("context_refresh");
    setSyncRunning(true);
    setStoppingSinceMs(0);
    resetSyncProgressMonitor();
    syncPollFailureCountRef.current = 0;
    setSyncStatus({
      job_id: "",
      task_id: "",
      status: "queued",
      phase: "queued",
      progress: {
          phase: "queued",
          phase_label: "等待启动",
          context_only: contextOnly,
	        status_message: contextOnly ? "官方上下文局部重试正在排队。" : "官方上下文刷新正在排队。",
	        percent_complete: 0,
	      },
	    });
	    appendLog("info", contextOnly ? "已发送仅重试官方上下文请求。" : "已发送官方上下文刷新请求。");
	    const endpoint = contextOnly ? "/api/sync_context_only" : "/api/sync_alphas";
	    const result = await callSyncStart<{ job_id?: string; task_id?: string; status_url?: string }>(endpoint, {
	      method: "POST",
		      body: JSON.stringify({
		        syncRange,
		        refreshOfficialContext: true,
		        userFacingOperation: "official_operations_context_refresh",
		        ...(contextOnly ? { contextOnly: true } : {}),
		        ...credentialsPayload(credentials),
		      }),
	    });
    const jobId = String(result?.job_id || result?.task_id || "");
    if (!result?.ok && jobId) {
      const message = operationFailureMessage(
        result,
        "已有官方上下文刷新正在运行，已接管当前任务状态。",
      );
      saveStoredSyncJobId(jobId);
      resetSyncStart();
      updateSyncJobId(jobId);
      setSyncRunning(true);
      syncPollFailureCountRef.current = 0;
      setSyncStatus({
        job_id: jobId,
        task_id: jobId,
        status: "running",
        phase: "running",
        progress: {
          job_id: jobId,
          task_id: jobId,
          phase: "running",
          phase_label: "已接管",
          context_only: contextOnly,
          status_message: message,
        },
      });
      appendLog("warning", `${message}: ${shortOperationId(jobId)}`);
      notify("info", "已接管正在运行的官方上下文刷新");
      return;
    }
    if (!result?.ok || !jobId) {
      const message = operationFailureMessage(result, "官方上下文刷新启动失败。请重试；若连续失败，请重新打开页面或联系维护者。");
      setSyncRunning(false);
      setSyncStatus((previous) => ({
        ...(previous || { job_id: "", status: "failed" }),
        status: "failed",
        phase: "failed",
        error: message,
        progress: {
          ...(previous?.progress || {}),
          phase: "failed",
          context_only: contextOnly,
          status_message: message,
          percent_complete: 100,
        },
      }));
      appendLog("error", message);
	      notify("error", message);
	      return;
	    }
    updateSyncJobId(jobId);
    saveStoredSyncJobId(jobId);
    setSyncStatus({
      job_id: jobId,
      task_id: jobId,
      status: "queued",
      phase: "queued",
      progress: {
        job_id: jobId,
        task_id: jobId,
        phase: "queued",
        phase_label: "已排队",
        context_only: contextOnly,
	        status_message: contextOnly ? "官方上下文局部重试已排队，正在等待页面进度更新。" : "官方上下文刷新已排队，正在等待页面进度更新。",
	        percent_complete: 0,
	      },
	    });
	    appendLog("success", `刷新流程已启动: ${shortOperationId(jobId)}`);
	    notify("info", contextOnly ? "官方上下文局部重试已启动" : "官方上下文刷新已启动");
  }, [appendLog, callSyncStart, connectionReady, credentials, notify, resetSyncProgressMonitor, resetSyncStart, syncRange, updateSyncJobId]);

  const startContextOnlyRefresh = useCallback(() => {
    void startOfficialContextRefresh({ contextOnly: true });
  }, [startOfficialContextRefresh]);

  useEffect(() => {
    if (!autoStart || autoStartConsumedRef.current) return;
    if (syncRunning || syncJobId) return;
    autoStartConsumedRef.current = true;
    onAutoStartConsumed?.();
    void startOfficialContextRefresh();
  }, [autoStart, onAutoStartConsumed, startOfficialContextRefresh, syncJobId, syncRunning]);

  const interruptOfficialContextRefresh = useCallback(async (message: string) => {
    if (!syncJobId) return;
    setSyncRunning(false);
    setSyncStatus((previous) => ({
      ...(previous || { job_id: syncJobId, task_id: syncJobId, status: "stopped" }),
      job_id: previous?.job_id || syncJobId,
      task_id: previous?.task_id || syncJobId,
      status: "stopped",
      phase: "stopped",
      error: message,
      progress: {
        ...(previous?.progress || {}),
        job_id: previous?.progress?.job_id || syncJobId,
        task_id: previous?.progress?.task_id || syncJobId,
        phase: "stopped",
        phase_label: "已自动停止",
        status_message: message,
        percent_complete: 100,
      },
    }));
	    const result = await callSyncCancel<{ stopping_since_ms?: number | string }>("/api/sync_cancel", {
      method: "POST",
      body: JSON.stringify({ job_id: syncJobId }),
    });
    if (!result?.ok) {
      const cancelMessage = operationFailureMessage(result, "停止请求暂未确认。请稍后重新读取状态。");
      appendLog("error", cancelMessage);
      notify("error", cancelMessage);
      return;
    }
    clearStoredSyncJobId();
    resetSyncProgressMonitor();
    appendLog("warning", message);
    notify("warning", message);
  }, [appendLog, callSyncCancel, notify, resetSyncProgressMonitor, syncJobId]);

  const pollSyncStatus = useCallback(async () => {
    if (!syncJobId) return;
    if (syncPollInFlightRef.current) return;
    const requestedJobId = syncJobId;
    const pollGeneration = syncPollGenerationRef.current;
    syncPollInFlightRef.current = true;
    try {
      const result = await callSyncStatus<JobStatus>(`/api/sync_status?job_id=${encodeURIComponent(requestedJobId)}&compact=1`);
      if (activeSyncJobIdRef.current !== requestedJobId || syncPollGenerationRef.current !== pollGeneration) {
        return;
      }
      if (!result?.ok) {
        const message = operationFailureMessage(result, "刷新状态读取失败。");
        const failures = syncPollFailureCountRef.current + 1;
        syncPollFailureCountRef.current = failures;
        appendLog("warning", `刷新状态读取失败 (${failures}/${SYNC_STATUS_FAILURE_LIMIT}): ${message}`);
        if (failures >= SYNC_STATUS_FAILURE_LIMIT) {
          await interruptOfficialContextRefresh("连续读取刷新状态失败，已自动停止本次刷新。请检查网络或稍后重试。");
        }
        return;
      }
      syncPollFailureCountRef.current = 0;
      setSyncStatus(result);
      const stall = inspectSyncProgressMonitor(result);
      if (stall?.level === "warning") {
        appendLog("warning", stall.message);
        notify("warning", stall.message);
      } else if (stall?.level === "stop") {
        await interruptOfficialContextRefresh(stall.message);
        return;
      }
      const resultState = classifyJobState(result);
	      if (resultState.successful) {
	        clearStoredSyncJobId();
	        setSyncRunning(false);
	        setStoppingSinceMs(0);
	        syncPollFailureCountRef.current = 0;
	        resetSyncProgressMonitor();
	        appendLog(resultState.warning ? "warning" : "success", operationStatusMessage(result));
	        notify(resultState.warning ? "warning" : "success", "官方上下文刷新完成");
	        onSyncCompleted?.();
      } else if (resultState.failed || resultState.interrupted || resultState.missing) {
	        clearStoredSyncJobId();
	        setSyncRunning(false);
	        setStoppingSinceMs(0);
	        syncPollFailureCountRef.current = 0;
	        resetSyncProgressMonitor();
	        appendLog(resultState.failed || resultState.missing ? "error" : "warning", operationStatusMessage(result));
	        notify(resultState.failed || resultState.missing ? "error" : "warning", operationStatusMessage(result));
	      } else if (resultState.status === "stopping") {
	        const since = numberField(result.progress, "stopping_since_ms") || stoppingSinceMs || Date.now();
	        setStoppingSinceMs(since);
	      }
	    } finally {
	      if (syncPollGenerationRef.current === pollGeneration) {
	        syncPollInFlightRef.current = false;
	      }
	    }
	  }, [appendLog, callSyncStatus, inspectSyncProgressMonitor, interruptOfficialContextRefresh, notify, onSyncCompleted, resetSyncProgressMonitor, stoppingSinceMs, syncJobId]);

  useEffect(() => {
    if (!syncRunning || !syncJobId) return;
    const timer = window.setInterval(() => {
      void pollSyncStatus();
    }, POLL_INTERVAL_MS);
    void pollSyncStatus();
    return () => window.clearInterval(timer);
  }, [pollSyncStatus, syncJobId, syncRunning]);

	  const stopOfficialContextRefresh = useCallback(async () => {
	    if (!syncJobId) return;
	    const requestedAt = Date.now();
	    setStoppingSinceMs(requestedAt);
	    setStoppingNowMs(requestedAt);
	    setSyncStatus((previous) => ({
	      ...(previous || { job_id: syncJobId, task_id: syncJobId, status: "stopping" }),
	      job_id: previous?.job_id || syncJobId,
	      task_id: previous?.task_id || syncJobId,
	      status: "stopping",
	      phase: "stopping",
	      progress: {
	        ...(previous?.progress || {}),
	        job_id: previous?.progress?.job_id || syncJobId,
	        task_id: previous?.progress?.task_id || syncJobId,
	        phase: "stopping",
	        status_code: "STOPPING",
	        phase_label: "停止中",
	        status_message: "停止请求已发送，等待当前官方接口返回后结束。",
	        stopping_since_ms: requestedAt,
	      },
	    }));
	    const result = await callSyncCancel<{ stopping_since_ms?: number | string }>("/api/sync_cancel", {
	      method: "POST",
	      body: JSON.stringify({ job_id: syncJobId }),
	    });
    if (!result?.ok) {
      const message = operationFailureMessage(result, "停止请求失败。请稍后重试。");
      appendLog("error", message);
      notify("error", message);
      return;
    }
	    clearStoredSyncJobId();
	    resetSyncProgressMonitor();
	    syncPollFailureCountRef.current = 0;
	    const serverStoppingSince = Number(result?.stopping_since_ms);
	    if (Number.isFinite(serverStoppingSince) && serverStoppingSince > 0) {
	      setStoppingSinceMs(serverStoppingSince);
	    }
	    setSyncStatus((previous) => ({
      ...(previous || { job_id: syncJobId, task_id: syncJobId, status: "stopping" }),
      job_id: previous?.job_id || syncJobId,
      task_id: previous?.task_id || syncJobId,
      status: "stopping",
      phase: "stopping",
      progress: {
        ...(previous?.progress || {}),
        job_id: previous?.progress?.job_id || syncJobId,
        task_id: previous?.progress?.task_id || syncJobId,
        phase: "stopping",
        phase_label: "停止中",
	        status_message: "停止请求已发送，等待当前官方接口返回后结束。",
	        stopping_since_ms: Number.isFinite(serverStoppingSince) && serverStoppingSince > 0 ? serverStoppingSince : requestedAt,
	      },
	    }));
	    appendLog("warning", "已发送停止请求，系统会在当前官方接口返回后结束。");
	    notify("info", "停止请求已发送");
	  }, [appendLog, callSyncCancel, notify, resetSyncProgressMonitor, syncJobId]);

  useEffect(() => {
    if (syncStatus?.status !== "stopping") return;
    const timer = window.setInterval(() => setStoppingNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [syncStatus?.status]);

  useEffect(() => {
    if (syncStatus?.status !== "stopping" || !syncJobId || !stoppingSinceMs) return;
    const waitMs = Math.max(0, STOP_RETRY_AFTER_MS - (Date.now() - stoppingSinceMs));
    const timer = window.setTimeout(() => {
      if (stopRetryStartedAtRef.current >= stoppingSinceMs) return;
      stopRetryStartedAtRef.current = stoppingSinceMs;
      appendLog("warning", "停止等待超过 60 秒，正在重新发送停止请求。");
      void callSyncCancel("/api/sync_cancel", {
        method: "POST",
        body: JSON.stringify({ job_id: syncJobId }),
      });
    }, waitMs);
    return () => window.clearTimeout(timer);
  }, [appendLog, callSyncCancel, stoppingSinceMs, syncJobId, syncStatus?.status]);

  const currentProgress = operationProgress(mode, syncStatus, readinessApi.data, checkResultsApi.data);
  const currentError = currentModeError(mode, syncStatus, {
    syncStart: syncStartApi.error,
    syncStatus: syncStatusApi.error,
    readiness: readinessApi.error,
    checks: checkResultsApi.error,
  });
  const currentState = progressState(mode, syncRunning, syncStatus, readinessApi.loading, checkResultsApi.loading, currentError);
  const readiness = readinessApi.data;
  const checkRows = checkResultsApi.data?.items || checkResultsApi.data?.checks || [];
	  const displaySyncStatus = syncStatusForDisplay(syncStatus, officialContextCache);
		  const syncOverview = syncDataOverview(displaySyncStatus, syncRunning, cloudAlphaCache);
      const syncHistory = displaySyncStatus?.sync_history || [];
      const syncHistoryError = displaySyncStatus?.sync_history_error || "";
      const syncHistoryErrorTitle = syncHistoryError ? syncHistoryReadErrorTitle(syncHistoryError) : "";
	  const canRetryContext = canRetryContextOnly(syncStatus);
  const syncState = classifyJobState(syncStatus);
  const displaySyncState = classifyJobState(displaySyncStatus);
  const syncNeedsRetry = syncState.failed || syncState.interrupted || syncState.missing;
  const refreshPanelTitle = contextOnlyMode ? "仅刷新官方能力集" : "刷新官方能力集";
  const refreshPanelDescription = contextOnlyMode
    ? "仅刷新官方字段、算子与 Dataset 上下文，不拉取云端 Alpha 快照。"
    : "同步云端 Alpha 快照，并刷新官方字段、算子与 Dataset 上下文。";
	  const stoppingElapsedSeconds = syncStatus?.status === "stopping" && stoppingSinceMs
	    ? Math.max(0, Math.floor(((stoppingNowMs || Date.now()) - stoppingSinceMs) / 1000))
	    : 0;

  return (
    <div className="min-w-0 space-y-5 animate-fade-in">
      <section className="panel min-w-0 space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="badge badge-info">官方操作入口</span>
              <span className="badge badge-neutral">按钮驱动</span>
              <span className="badge badge-neutral">非提交</span>
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text-primary">官方同步与阻断复核</h2>
            <p className="mt-2 max-w-4xl text-base leading-7 text-text-secondary">
              这里把官方上下文刷新、提交前阻断复核和质量结果放在同一个页面里：点击按钮、看进度、读记录、处理阻断。系统会自动处理请求，用户只需留在浏览器里查看进度和结果。
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4 lg:min-w-[420px]">
            <OperationMetric label="官方上下文" value={syncContextStatus(displaySyncStatus)} tone={syncRunning ? "warning" : contextCacheComplete(displaySyncStatus?.official_context_cache) || displaySyncState.successful ? "success" : "neutral"} />
            <OperationMetric label="复核候选" value={String(readiness?.eligible_count ?? "-")} tone={readiness?.ready_to_submit ? "success" : "warning"} />
            <OperationMetric label="检查记录" value={String(checkRows.length || "-")} />
            <OperationMetric label="真实提交" value="关闭" tone="success" />
          </div>
        </div>

        <section className="grid gap-3 md:grid-cols-3" aria-label="官方同步数据总览">
          <OverviewCard
            label="同步状态"
            value={syncOverview.statusValue}
            detail={syncOverview.statusDetail}
            tone={syncOverview.statusTone}
          />
          <OverviewCard
            label="更新时间"
            value={syncOverview.updatedAtValue}
            detail={syncOverview.updatedAtDetail}
          />
          <OverviewCard
            label="分页拉取"
            value={syncOverview.totalValue}
            detail={syncOverview.totalDetail}
            tone={syncOverview.totalTone}
          />
        </section>

        {syncRunning && syncOverview.hasLiveMetrics && (
          <section className="grid gap-3 md:grid-cols-2" aria-label="同步实时指标">
            <OverviewCard
              label={syncOverview.etaLabel}
              value={syncOverview.etaValue}
              detail={syncOverview.etaDetail}
              tone="warning"
            />
            <OverviewCard
              label={syncOverview.rateLabel}
              value={syncOverview.rateValue}
              detail={syncOverview.rateDetail}
            />
          </section>
        )}

        <div className="grid gap-3 lg:grid-cols-3">
	          <ActionPanel
	            title={refreshPanelTitle}
	            description={refreshPanelDescription}
            status={syncStatus?.status === "stopping" ? "停止中" : syncRunning ? "运行中" : displaySyncStatus ? syncContextStatus(displaySyncStatus) : "待启动"}
	            primaryLabel={syncRunning ? "刷新中..." : syncNeedsRetry ? "重新刷新" : "开始刷新"}
	            disabled={syncRunning || syncStartApi.loading}
	            onPrimary={() => void startOfficialContextRefresh()}
	            secondaryLabel="停止"
	            secondaryDisabled={!syncRunning || !syncJobId || syncStatus?.status === "stopping"}
	            onSecondary={stopOfficialContextRefresh}
	          >
	            <label className="mt-3 block text-xs text-text-secondary">
	              <span className="mb-1 block text-text-tertiary">同步范围</span>
	              <select
	                className="input w-full text-sm"
	                value={syncRange}
	                disabled={syncRunning || syncStartApi.loading}
	                onChange={(event) => setSyncRange(event.target.value as SyncRange)}
	                aria-label="同步范围"
	              >
	                <option value="all">全部（推荐）</option>
	                <option value="3d">近 3 天（快速检查）</option>
	                <option value="7d">近 7 天</option>
	                <option value="recent">近期 30 天</option>
	                <option value="6months">近 6 个月</option>
	              </select>
	              <span className="mt-1 block text-text-tertiary">
	                默认完整同步；小范围同步更快，适合快速检查最近变化。
	              </span>
	            </label>
	          </ActionPanel>
          <ActionPanel
            title="检查阻断复核"
            description="读取本地提交前阻断复核门禁，不调用真实提交。"
            status={readiness?.ready_to_submit ? "有候选" : readiness ? "仍阻断" : "待检查"}
            primaryLabel={readinessApi.loading ? "检查中..." : "读取复核"}
            disabled={readinessApi.loading}
            onPrimary={loadReadiness}
          />
          <ActionPanel
            title="回看检查结果"
            description="读取质量检查结果和阻断原因，方便继续迭代候选。"
            status={checkRows.length ? `${checkRows.length} 条记录` : "待读取"}
            primaryLabel={checkResultsApi.loading ? "加载中..." : "查看结果"}
            disabled={checkResultsApi.loading}
            onPrimary={loadChecks}
          />
	        </div>

	        {(syncJobId || displaySyncStatus?.official_context_cache) && (
	          <section className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3" aria-label="官方上下文快速摘要">
	            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
	              <dl className="grid min-w-0 flex-1 grid-cols-3 gap-3 text-sm">
	                <SummaryMetric label="字段" value={contextSummaryField(displaySyncStatus, "fields_count")} />
	                <SummaryMetric label="算子" value={contextSummaryField(displaySyncStatus, "operators_count")} />
	                <SummaryMetric label="数据集" value={contextSummaryField(displaySyncStatus, "datasets_count")} />
	              </dl>
	              {canRetryContext && (
	                <button type="button" className="btn btn-secondary text-sm" onClick={startContextOnlyRefresh} disabled={syncRunning || syncStartApi.loading}>
	                  仅重试上下文
	                </button>
	              )}
	            </div>
	            <p className="mt-2 text-sm leading-6 text-text-secondary">{officialContextInlineSummary(displaySyncStatus)}</p>
	          </section>
	        )}

        {(syncHistory.length > 0 || syncHistoryError) && (
          <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4" aria-label="最近官方同步">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">最近官方同步</h3>
                <p className="mt-1 text-sm leading-6 text-text-secondary">
                  最近任务只展示状态摘要和增量，不展示请求载荷或凭证。
                </p>
              </div>
              {syncHistoryError && (
                <span className="badge badge-warning text-xs" title={syncHistoryErrorTitle}>历史读取受限</span>
              )}
            </div>
            {syncHistory.length > 0 ? (
              <SyncHistoryList rows={syncHistory} />
            ) : (
              <p className="mt-3 text-sm text-text-tertiary">暂无可展示的官方同步历史。</p>
            )}
          </section>
        )}

		        {syncStatus?.status === "stopping" && (
		          <div className="rounded-md border border-[oklch(0.65_0.06_85/0.25)] bg-warning-subtle p-3 text-sm leading-6 text-warning">
	            停止请求已发送，等待当前官方接口返回后结束。已等待 {formatDuration(stoppingElapsedSeconds)}；通常在 15 秒内生效，超过 60 秒会自动重试一次。
	          </div>
	        )}

        {syncStatus?.phase === "session_invalid" && (
          <div className="rounded-md border border-[oklch(0.62_0.10_35/0.35)] bg-negative-subtle p-3 text-sm leading-6 text-negative" role="alert">
            <p className="font-medium">本地会话需要重新连接</p>
            <p className="mt-1 text-text-secondary">
              同步任务可能仍在后台运行，但当前页面无法继续读取状态。请回到运行总览重新测试连接，再回到官方操作页恢复监控。
            </p>
            {onReconnectRequested && (
              <button type="button" className="btn btn-secondary mt-2 text-sm" onClick={onReconnectRequested}>
                前往运行总览重新连接
              </button>
            )}
          </div>
        )}

	        <ProgressFeedback
	          state={currentState}
	          title="操作进度"
	          progress={currentProgress}
	          error={currentError}
	          onRetry={mode === "context_refresh" ? (canRetryContext ? startContextOnlyRefresh : () => void startOfficialContextRefresh()) : mode === "readiness" ? loadReadiness : mode === "checks" ? loadChecks : undefined}
	        />

	        <OperationLog logs={logs} onClear={() => setLogs([])} />

	      </section>

	      <SummarySections
	        readiness={readiness}
	        displaySyncStatus={displaySyncStatus}
	        onNavigateToCandidates={onNavigateToCandidates}
	      />
    </div>
  );
}
