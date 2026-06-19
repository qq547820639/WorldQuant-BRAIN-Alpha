/** Button-driven official operations panel for browser-only user workflows. */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { apiErrorMessage, knownApiErrorMessage, isSessionInvalidPayload } from "@/helpers/errorExperience";
import type { ApiErrorExperiencePayload } from "@/helpers/errorExperience";
import { readinessNextActionLabel, readinessProductionGapLabel, readinessReasonLabel } from "@/helpers/readinessLabels";
import { classifyJobState, jobStatusMessage } from "@/helpers/runPayload";
import { useApi } from "@/hooks/useApi";
import type { BrainCredentials, CloudAlphaCache, JobStatus, OfficialContextCache, SubmitReadinessResponse, SyncHistoryItem, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
import { reportIgnoredError } from "@/utils/reportIgnoredError";
import {
  ActionPanel,
  OperationLog,
  OperationMetric,
  OverviewCard,
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
  ACTIVE_SYNC_JOB_ID_KEY,
  formatClock,
  formatDuration,
  formatCount,
  firstPositiveFloat,
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

interface OperationLogEntry {
  time: string;
  tone: "info" | "success" | "warning" | "error";
  message: string;
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
  const allReadinessBlockers = readiness?.top_blocking_reasons || [];
  const allFamilyBlockers = readiness?.top_family_blocking_reasons || [];
  const allProductionGaps = readiness?.production_gaps || readiness?.findings || [];
  const allNextSteps = readiness?.required_next_steps || [];
  const bestCandidate = readiness?.best_candidate || {};
  const allBestCandidateReasons = bestCandidate.blocking_reasons || [];
  const readinessActionCodes = readinessActionSignals(
    allReadinessBlockers,
    allFamilyBlockers,
    allProductionGaps,
    allBestCandidateReasons,
    allNextSteps,
    bestCandidate.decision_band,
  );
  const needsOfficialEvidenceAction = Boolean(
    readiness && readinessActionCodes.some((code) => officialEvidenceActionCodes.has(code)),
  );
  const needsSubmitBandAction = Boolean(
    readiness && readinessActionCodes.some((code) => submitBandActionCodes.has(code)),
  );
  const hasBestCandidateEvidence = Boolean(
    bestCandidate.alpha_id ||
    bestCandidate.official_alpha_id ||
    bestCandidate.decision_band ||
    allBestCandidateReasons.length,
  );
	  const summaryCounts = readiness?.summary_counts || {};
		  const displaySyncStatus = syncStatusForDisplay(syncStatus, officialContextCache);
		  const syncOverview = syncDataOverview(displaySyncStatus, syncRunning, cloudAlphaCache);
      const syncHistory = displaySyncStatus?.sync_history || [];
      const syncHistoryError = displaySyncStatus?.sync_history_error || "";
      const syncHistoryErrorTitle = syncHistoryError ? syncHistoryReadErrorTitle(syncHistoryError) : "";
			  const officialContextSummary = officialContextSummaryMessage(displaySyncStatus);
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

        {/* Real-time ETA & Rate row — only shown during active sync */}
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

	        <details className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-3">
	          <summary className="cursor-pointer text-sm font-semibold text-text-primary">
	            操作日志（{logs.length} 条）
	          </summary>
	          <div className="mt-3 flex items-center justify-between gap-3">
	            <p className="text-xs text-text-tertiary">系统动作会写成可读事件，不展示命令或路径。</p>
	            <button type="button" className="btn btn-secondary text-sm" onClick={() => setLogs([])}>
	              清空
	            </button>
	          </div>
	          <div className="mt-3 max-h-40 min-w-0 overflow-y-auto rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3 text-sm leading-6 text-text-secondary" role="status" aria-live="polite" aria-label="官方操作时间线">
	            {logs.length ? logs.map((entry, index) => (
	              <div key={`${entry.time}_${index}`} className="grid grid-cols-[auto_minmax(0,1fr)] gap-3 border-l border-border-subtle pb-3 pl-3 last:pb-0">
	                <span className={`mt-1 ${logDotTone(entry.tone)}`} aria-hidden="true" />
	                <div className="min-w-0">
	                  <p className="text-xs text-text-tertiary">{entry.time}</p>
	                  <p className={`break-words ${logTone(entry.tone)}`}>{entry.message}</p>
	                </div>
	              </div>
	            )) : (
	              <div className="text-text-tertiary">事件已清空。</div>
	            )}
	          </div>
	        </details>
	      </section>

	      <section className="grid gap-4 lg:grid-cols-3">
	        <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
	          <h3 className="text-sm font-semibold text-text-primary">阻断复核摘要</h3>
	          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
	            <SummaryMetric label="复核通过" value={readiness?.ready_to_submit ? "是" : "否"} />
	            <SummaryMetric label="复核候选" value={String(readiness?.eligible_count ?? 0)} />
	            <SummaryMetric label="候选总数" value={String(readiness?.candidate_count ?? 0)} />
	            <SummaryMetric label="最近验证" value={readiness?.latest_job_id ? shortOperationId(readiness.latest_job_id) : "-"} title={readiness?.latest_job_id} mono />
	          </dl>
	          <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
	            <BlockerList title={countTitle("当前阻断", allReadinessBlockers.length)} rows={allReadinessBlockers.map(reasonCountText)} empty="暂无就绪数据" />
	            <BlockerList title={countTitle("候选族阻断", allFamilyBlockers.length)} rows={allFamilyBlockers.map(reasonCountText)} empty="暂无候选族阻断" />
	            <BlockerList title={countTitle("下一步", allNextSteps.length)} rows={allNextSteps.map(actionStepLabel)} empty="先读取阻断复核证据" />
	          </div>
            {(needsOfficialEvidenceAction || needsSubmitBandAction) && (
              <div className="mt-3 border-l-2 border-accent pl-3 text-sm leading-6 text-text-secondary">
                <p className="font-semibold text-text-primary">补齐官方证据</p>
                {needsOfficialEvidenceAction && (
                  <p className="mt-1">
                    前往「候选管理」，优先点击「自动推进候选池」；仅当官方证据缺失时，使用「运行官方验证队列」或候选行「单行补模拟」补齐 official_alpha_id 与 official_metrics。完成后回到这里点击「读取复核」。
                  </p>
                )}
                {needsSubmitBandAction && (
                  <p className="mt-1">
                    当前候选尚未进入 submit_candidate 复核带；先让候选管理自动维护主池并继续筛选/评分，进入复核带后由自动流程补齐官方模拟证据。
                  </p>
                )}
                {onNavigateToCandidates && (
                  <button type="button" className="btn btn-secondary mt-2 text-sm" onClick={onNavigateToCandidates}>
                    前往候选管理
                  </button>
                )}
              </div>
            )}
	        </section>

	        <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
	          <h3 className="text-sm font-semibold text-text-primary">收敛诊断</h3>
	          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
	            <SummaryMetric label="官方验证" value={String(summaryCounts.official_validation_passed ?? 0)} />
	            <SummaryMetric label="官方仿真" value={String(summaryCounts.officially_simulated ?? 0)} />
	            <SummaryMetric label="复核带" value={String(summaryCounts.submission_ready ?? 0)} />
	            <SummaryMetric label="候选族" value={String(readiness?.job_family_candidate_count ?? 0)} />
	          </dl>
	          <div className="mt-3 space-y-2 text-sm leading-6 text-text-secondary">
	            <BlockerList title={countTitle("生产缺口", allProductionGaps.length)} rows={allProductionGaps.map(findingText)} empty="先读取阻断复核证据" />
		            <BlockerList title={countTitle("最佳候选阻断", allBestCandidateReasons.length)} rows={allBestCandidateReasons.map((reason) => readinessReasonLabel(reason))} empty="暂无最佳候选阻断" />
	          </div>
	          <div className="mt-3 rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3 text-sm leading-6 text-text-secondary">
	            <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">最佳候选证据</p>
	            <dl className="mt-2 grid grid-cols-2 gap-3">
	              <SummaryMetric label="Alpha" value={hasBestCandidateEvidence ? bestCandidate.alpha_id || "-" : "-"} mono />
	              <SummaryMetric label="分数" value={hasBestCandidateEvidence ? formatOptionalNumber(bestCandidate.score) : "-"} />
	              <SummaryMetric label="决策" value={hasBestCandidateEvidence ? readinessReasonLabel(bestCandidate.decision_band || "") : "-"} />
	              <SummaryMetric label="相似度" value={hasBestCandidateEvidence ? formatOptionalNumber(bestCandidate.max_similarity) : "-"} />
	              <SummaryMetric label="本地回测" value={formatLocalBacktestStatus(bestCandidate.local_backtest_passed, hasBestCandidateEvidence)} />
	              <SummaryMetric label="风险" value={hasBestCandidateEvidence ? riskLevelLabel(bestCandidate.risk_level || "") : "-"} />
	            </dl>
	          </div>
	        </section>

	        <section className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
	          <h3 className="text-sm font-semibold text-text-primary">官方上下文摘要</h3>
	          <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
	            <SummaryMetric label="字段" value={contextSummaryField(displaySyncStatus, "fields_count")} />
	            <SummaryMetric label="算子" value={contextSummaryField(displaySyncStatus, "operators_count")} />
	            <SummaryMetric label="数据集" value={contextSummaryField(displaySyncStatus, "datasets_count")} />
	          </dl>
	          <p className="mt-3 text-sm leading-6 text-text-secondary">
	            {officialContextSummary}
	          </p>
	        </section>
	      </section>
    </div>
  );
}

function ActionPanel({
  title,
  description,
  status,
  primaryLabel,
  disabled,
  onPrimary,
  secondaryLabel,
  secondaryDisabled,
  onSecondary,
  children,
}: {
  title: string;
  description: string;
  status: string;
  primaryLabel: string;
  disabled?: boolean;
  onPrimary: () => void;
  secondaryLabel?: string;
  secondaryDisabled?: boolean;
  onSecondary?: () => void;
  children?: ReactNode;
}) {
  return (
    <article className="min-w-0 rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-text-secondary">{description}</p>
        </div>
        <span className="badge badge-neutral shrink-0 text-xs">{status}</span>
      </div>
      {children}
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="btn btn-primary text-sm" disabled={disabled} onClick={onPrimary}>
          {primaryLabel}
        </button>
        {secondaryLabel && onSecondary && (
          <button type="button" className="btn btn-secondary text-sm" disabled={secondaryDisabled} onClick={onSecondary}>
            {secondaryLabel}
          </button>
        )}
      </div>
    </article>
  );
}

function OperationMetric({ label, value, tone = "neutral" }: { label: string; value: string; tone?: "success" | "warning" | "neutral" }) {
  return (
    <div className="rounded-md border border-border-subtle bg-[oklch(0.100_0.007_45)] px-3 py-2">
      <p className="text-xs text-text-tertiary">{label}</p>
      <p className={`mt-1 truncate text-sm font-semibold ${tone === "success" ? "text-positive" : tone === "warning" ? "text-warning" : "text-text-primary"}`}>{value}</p>
    </div>
  );
}

function OverviewCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: OverviewTone;
}) {
  const toneClass = tone === "success"
    ? "border-border-subtle bg-positive-subtle text-positive"
    : tone === "warning"
      ? "border-[oklch(0.65_0.06_85/0.25)] bg-warning-subtle text-warning"
      : "border-border-subtle bg-[oklch(0.115_0.007_45)] text-text-primary";
  return (
    <article className={`min-w-0 rounded-md border p-4 ${toneClass}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-70">{label}</p>
      <p className="mt-2 truncate text-xl font-semibold tracking-tight" title={value}>{value}</p>
      <p className="mt-1 min-h-10 break-words text-sm leading-5 opacity-80">{detail}</p>
    </article>
  );
}

function SummaryMetric({ label, value, title, mono = false }: { label: string; value: string; title?: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-text-tertiary">{label}</dt>
      <dd className={`mt-1 truncate text-sm font-semibold text-text-primary ${mono ? "font-mono-value" : ""}`} title={title || value}>{value}</dd>
    </div>
  );
}

function BlockerList({ title, rows, empty }: { title: string; rows: string[]; empty: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">{title}</p>
      <ul className="mt-1 space-y-1">
        {(rows.length ? rows : [empty]).map((row, index) => (
          <li key={`${title}_${index}`} className="break-words">{row}</li>
        ))}
      </ul>
    </div>
  );
}

function SyncHistoryList({ rows }: { rows: SyncHistoryItem[] }) {
  return (
    <ul className="mt-3 divide-y divide-border-subtle rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)]" aria-label="最近官方同步列表">
      {rows.slice(0, 5).map((row) => (
        <li key={row.job_id} className="grid gap-3 p-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`status-dot ${syncHistoryDotTone(row.status)}`} aria-hidden="true" />
              <span className="text-sm font-semibold text-text-primary">{syncHistoryStatusLabel(row.status)}</span>
              <span className="badge badge-neutral text-xs">{row.context_only ? "仅上下文" : "云端同步"}</span>
              <span className="font-mono-value text-xs text-text-tertiary" title={row.job_id}>{shortOperationId(row.job_id)}</span>
            </div>
            <p className="mt-1 break-words text-sm leading-6 text-text-secondary">
              {syncHistoryMessage(row)}
            </p>
          </div>
          <time className="text-xs text-text-tertiary sm:text-right" dateTime={syncHistoryDate(row)?.toISOString()}>
            {syncHistoryDate(row) ? formatClock(syncHistoryDate(row) as Date) : "-"}
          </time>
        </li>
      ))}
    </ul>
  );
}

function countTitle(label: string, total: number) {
  return total > 0 ? `${label}（共 ${total}）` : label;
}

function reasonCountText(row: { reason: string; count: number }) {
  return `${readinessReasonLabel(row.reason)} (${row.count})`;
}

const officialEvidenceActionCodes = new Set([
  "candidate_family_missing_cloud_similarity",
  "candidate_family_missing_official_alpha_id",
  "candidate_family_missing_official_metrics",
  "missing_cloud_similarity",
  "missing_official_alpha_id",
  "missing_official_metrics",
  "official_validation_without_simulation",
  "run official simulation/check in a trusted environment",
]);

const submitBandActionCodes = new Set([
  "candidate_family_not_submit_band",
  "decision_band_not_submit_candidate",
  "optimize",
  "research_only",
]);

function readinessActionSignals(
  blockers: Array<{ reason?: string }>,
  familyBlockers: Array<{ reason?: string }>,
  gaps: Array<{ code?: string; message?: string }>,
  bestCandidateReasons: string[],
  nextSteps: string[],
  decisionBand?: string,
) {
  return [
    ...blockers.map((row) => row.reason || ""),
    ...familyBlockers.map((row) => row.reason || ""),
    ...gaps.flatMap((row) => [row.code || "", row.message || ""]),
    ...bestCandidateReasons,
    ...nextSteps,
    decisionBand || "",
  ].map((item) => String(item || "").trim()).filter(Boolean);
}

function syncHistoryStatusLabel(status: string) {
  const value = String(status || "").toLowerCase();
  const labels: Record<string, string> = {
    completed: "已完成",
    completed_with_warnings: "带警告",
    failed: "失败",
    running: "进行中",
    queued: "已排队",
    stopping: "停止中",
    stopped: "已停止",
    cancelled: "已取消",
    canceled: "已取消",
    idle: "待启动",
  };
  return labels[value] || "状态待确认";
}

function syncHistoryDotTone(status: string) {
  const state = classifyJobState({ status });
  if (state.successful && !state.warning) return "status-dot-active";
  if (state.warning || state.active) return "status-dot-warning";
  if (state.failed || state.interrupted || state.missing) return "status-dot-error";
  return "status-dot-idle";
}

function syncHistoryMessage(row: SyncHistoryItem) {
  const explicit = readableBackendText(row.status_message || "");
  const scanned = firstPositiveNumber(row.scanned);
  const total = firstPositiveNumber(row.api_reported_total, row.filter_window_count, row.total);
  const deltas = [
    row.added && row.added > 0 ? `新增 ${formatCount(row.added)}` : "",
    row.updated && row.updated > 0 ? `更新 ${formatCount(row.updated)}` : "",
    row.skipped && row.skipped > 0 ? `跳过 ${formatCount(row.skipped)}` : "",
    row.failed && row.failed > 0 ? `失败 ${formatCount(row.failed)}` : "",
  ].filter(Boolean);
  const scanText = scanned > 0 && total > 0
    ? `已拉取 ${formatCount(scanned)} 条；分页参考数 ${formatCount(total)} 条`
    : scanned > 0
      ? `已拉取 ${formatCount(scanned)} 条`
      : "";
  const parts = [scanText, deltas.length ? deltas.join("，") : ""].filter(Boolean);
  if (explicit && parts.length) return `${explicit}；${parts.join("；")}。`;
  if (explicit) return explicit;
  if (parts.length) return `${parts.join("；")}。`;
  return row.phase ? `阶段: ${phaseLabel({ job_id: row.job_id, status: "idle", phase: row.phase })}` : "暂无同步摘要。";
}

function syncHistoryReadErrorTitle(raw: unknown) {
  return readableBackendText(raw) || "同步历史读取受限，无法展示原始错误详情。";
}

function syncHistoryDate(row: SyncHistoryItem) {
  const ms = firstPositiveNumber(row.updated_at_ms, row.updated_at ? row.updated_at * 1000 : 0);
  return ms > 0 ? new Date(ms) : null;
}

function findingText(row: { code?: string; message?: string }) {
  return readinessProductionGapLabel(row);
}

function riskLevelLabel(level: string) {
  const normalized = String(level || "").toLowerCase();
  const labels: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低",
  };
  return labels[normalized] || (normalized ? "风险待确认" : "-");
}

function actionStepLabel(step: string) {
  return readinessNextActionLabel(step);
}



function readableBackendText(raw: unknown) {
  const value = String(raw || "").trim();
  const sharedMessage = knownApiErrorMessage(value);
  if (sharedMessage) return sharedMessage;
  const fieldRefreshMatch = value.match(/^Updating official fields cache:\s*(.+)$/);
  if (fieldRefreshMatch) return `正在刷新官方字段缓存: ${fieldRefreshMatch[1]}`;
  const operatorRefreshMatch = value.match(/^Updating official operators cache:\s*(.+)$/);
  if (operatorRefreshMatch) return `正在刷新官方算子缓存: ${operatorRefreshMatch[1]}`;
  const labels: Record<string, string> = {
    "Official context refreshed.": "官方上下文已刷新。",
    "candidate family lacks official simulation metrics": "候选族缺少官方仿真指标",
    "official context timeout": "官方上下文刷新超时，请稍后重试。",
    "unknown sync job": "找不到本次同步任务，请重新启动刷新。",
    "unknown job": "找不到本次任务，请重新启动流程。",
    JOB_NOT_FOUND: "找不到本次任务，请重新启动流程。",
    SESSION_INVALID: "本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。",
    "invalid local session": "本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。",
    OFFICIAL_CONTEXT_REFRESH_TIMEOUT: "官方上下文刷新超时，请稍后重试。",
  };
  if (labels[value]) return labels[value];
  if (isAllowedOfficialStatusText(value)) return value;
  return null;
}

function isAllowedOfficialStatusText(value: string) {
  if (!value) return false;
  return [
    /^官方上下文已刷新/,
    /^官方上下文刷新/,
    /^官方上下文刷新已停止/,
    /^正在刷新官方字段缓存/,
    /^正在刷新官方算子缓存/,
    /^云端同步完成/,
    /^连续读取刷新状态失败/,
    /^用户已停止本次官方上下文刷新/,
  ].some((pattern) => pattern.test(value));
}

function formatOptionalNumber(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(3);
}

function formatLocalBacktestStatus(value: unknown, hasEvidence: boolean) {
  if (!hasEvidence) return "-";
  if (value === true) return "通过";
  if (value === false) return "未通过";
  return "-";
}



function syncStatusForDisplay(status: JobStatus | null, officialContextCache?: OfficialContextCache): JobStatus | null {
  const cache = status?.official_context_cache || officialContextCache;
  if (status) {
    return cache && status.official_context_cache !== cache
      ? { ...status, official_context_cache: cache }
      : status;
  }
  if (!cache) return null;
  return {
    job_id: "",
    task_id: "",
    status: "idle",
    phase: "local_cache",
    progress: {
      phase: "local_cache",
      status_code: contextCacheComplete(cache) ? "LOCAL_CACHE" : "LOCAL_CACHE_INVALID",
      status_message: contextCacheComplete(cache)
        ? "本地官方上下文缓存已加载。"
        : "本地官方上下文缓存完整性未通过，需要手动刷新。",
    },
    official_context_cache: cache,
  };
}

function syncDataOverview(syncStatus: JobStatus | null, syncRunning: boolean, cloudAlphaCache?: CloudAlphaCache) {
  const localCacheReady = !syncRunning && cloudAlphaCacheReady(cloudAlphaCache) && contextCacheComplete(syncStatus?.official_context_cache);
  const statusValue = syncRunning ? "同步中" : syncContextStatus(syncStatus);
  const stage = syncStageMetric(syncStatus);
  const statusDetail = localCacheReady
    ? "本地云端 Alpha 快照与官方能力集缓存已通过完整性校验；需要最新数据时可手动刷新。"
    : syncStatus
    ? `${phaseLabel(syncStatus)}: ${operationStatusMessage(syncStatus)}`
    : "等待启动云端 Alpha 同步。";
  let statusTone: OverviewTone = "neutral";
  if (syncRunning) statusTone = "warning";
  else if (localCacheReady) statusTone = "success";
  else if (isSuccessfulSyncStatus(syncStatus)) statusTone = "success";
  else if (classifyJobState(syncStatus).failed || classifyJobState(syncStatus).missing) statusTone = "warning";
  const updatedAt = syncStatusUpdatedAt(syncStatus) || cloudAlphaCacheUpdatedAt(cloudAlphaCache);
  const total = syncDataTotal(syncStatus, cloudAlphaCache);

  const hasLiveMetrics = syncRunning && (stage.current > 0 || stage.elapsedSeconds > 0);
  const scanIndeterminate = syncRunning && stage.kind === "scan";
  const scanHasTotal = stage.kind === "scan" && stage.total > 0;
  const etaValue = scanIndeterminate
    ? (scanHasTotal ? "分页继续确认" : "等待分页参考数")
    : stage.etaSeconds > 0
      ? formatDuration(stage.etaSeconds)
      : stage.elapsedSeconds > 0
        ? "计算中..."
        : "-";
  const etaDetail = scanIndeterminate
    ? scanEtaDetail(stage)
    : stage.etaSeconds > 0
      ? (stage.total > 0
        ? `预计 ${formatDuration(stage.etaSeconds)} 后完成${stage.label}（${formatCount(stage.current)} / ${formatCount(stage.total)} ${stage.unit}）。`
        : `预计 ${formatDuration(stage.etaSeconds)} 后完成${stage.label}。`)
      : stage.elapsedSeconds > 0
        ? `已用时 ${formatDuration(stage.elapsedSeconds)}，正在刷新${stage.label}，剩余时间计算中。`
        : `等待${stage.label}进度更新。`;
  const rateValue = stage.ratePerSecond > 0 ? `${stage.ratePerSecond.toFixed(1)} ${stage.rateUnit}` : "-";
  const rateDetail = stage.current > 0 && stage.elapsedSeconds > 0
    ? `${stage.label}已处理 ${formatCount(stage.current)} ${stage.unit}，历时 ${formatDuration(stage.elapsedSeconds)}。`
    : `${stage.rateLabel}来自当前阶段的官方 API 进度反馈。`;

  return {
    statusValue,
    statusDetail,
    statusTone,
    updatedAtValue: updatedAt ? formatClock(updatedAt) : "-",
    updatedAtDetail: updatedAt ? (localCacheReady ? "来自本地云端 Alpha 快照。" : "来自本次同步进度。") : "暂无同步更新时间。",
    ...total,
    hasLiveMetrics,
    etaLabel: stage.kind === "scan" ? "分页进度" : "阶段估算",
    etaValue,
    etaDetail,
    rateLabel: stage.rateLabel,
    rateValue,
    rateDetail,
  };
}

function syncDataTotal(syncStatus: JobStatus | null, cloudAlphaCache?: CloudAlphaCache) {
  const terminal = isTerminalSyncStatus(syncStatus);
  const successful = isSuccessfulSyncStatus(syncStatus);
  const scanned = firstPositiveNumber(
    numberField(syncStatus?.progress, "scanned"),
    resultNumberField(syncStatus, "scanned"),
    resultNumberField(syncStatus, "count"),
  );
  const reportedTotal = firstPositiveNumber(
    numberField(syncStatus?.progress, "api_reported_total"),
    numberField(syncStatus?.progress, "filter_window_count"),
    resultNumberField(syncStatus, "api_reported_total"),
    resultNumberField(syncStatus, "filter_window_count"),
  );
  const completedCount = firstPositiveNumber(
    resultNumberField(syncStatus, "count"),
    resultNumberField(syncStatus, "scanned"),
    numberField(syncStatus?.progress, "scanned"),
  );
  if (successful && completedCount > 0) {
      const detail = reportedTotal > 0 && reportedTotal !== completedCount
        ? `本次同步实际保存 ${formatCount(completedCount)} 条；接口分页参考数 ${formatCount(reportedTotal)} 条仅用于分页边界判断。`
        : "本次同步实际保存数量；来自本地同步结果。";
    return {
      totalValue: formatCount(completedCount),
      totalDetail: detail,
      totalTone: "success" as const,
    };
  }
  if (scanned > 0) {
    if (terminal && !successful) {
      return {
        totalValue: `已拉取 ${formatCount(scanned)}`,
        totalDetail: "本次未完成；结果未确认完成，官方分页参考值不作为完成判断。",
        totalTone: "warning" as const,
      };
    }
    return {
      totalValue: `已拉取 ${formatCount(scanned)}`,
      totalDetail: terminal
        ? (reportedTotal > 0
          ? `本次未完成；接口分页参考数 ${formatCount(reportedTotal)} 条仅用于分页边界判断，已拉取 ${formatCount(scanned)} 条。`
          : "本次未完成；接口分页参考数仍在确认。")
        : reportedTotal > 0
        ? `接口分页参考数 ${formatCount(reportedTotal)} 条，不是云端 Alpha 总量；${syncScanPageSummary(syncStatus)}`
        : "接口分页参考数仍在确认；会按官方分页继续读取。",
      totalTone: "warning" as const,
    };
  }
  if (terminal && !successful) {
    return {
      totalValue: "-",
      totalDetail: "本次未完成；结果未确认完成，官方分页参考值不作为完成判断。",
      totalTone: "warning" as const,
    };
  }
  if (reportedTotal > 0) {
    return {
      totalValue: `分页参考数 ${formatCount(reportedTotal)}`,
      totalDetail: "接口分页参考数；尚未完成实际同步确认，不是云端 Alpha 总量。",
      totalTone: "neutral" as const,
    };
  }
  if (cloudAlphaCacheReady(cloudAlphaCache)) {
    const count = firstPositiveNumber(cloudAlphaCache?.count, cloudAlphaCache?.total);
    if (count <= 0) {
      return {
        totalValue: "本地快照可用",
        totalDetail: cloudAlphaCache?.is_stale
          ? "本地云端 Alpha 快照可用但已过期；精确数量请刷新云端快照。"
          : "本地云端 Alpha 快照已确认可用；精确数量由云端快照页加载。",
        totalTone: (cloudAlphaCache?.is_stale ? "warning" : "success") as OverviewTone,
      };
    }
    return {
      totalValue: `本地保存 ${formatCount(count)}`,
      totalDetail: cloudAlphaCache?.is_stale
        ? "本地云端 Alpha 快照可用但已过期；需要最新数据时点击开始刷新。"
        : "来自本地云端 Alpha 快照；后续登录默认直接使用该缓存。",
      totalTone: (cloudAlphaCache?.is_stale ? "warning" : "success") as OverviewTone,
    };
  }
  return {
    totalValue: "-",
    totalDetail: "等待云端 Alpha 同步；会先读取接口分页参考数，再按分页参数循环拉取。",
    totalTone: "neutral" as const,
  };
}

function operationProgress(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  readiness: SubmitReadinessResponse | null,
  checks: CheckResultsResponse | null,
): UnifiedProgress {
  if (mode === "context_refresh") {
    const stage = syncStageMetric(syncStatus);
    const terminal = isTerminalSyncStatus(syncStatus);
    const successful = isSuccessfulSyncStatus(syncStatus);
    const terminalFailure = terminal && !successful;
    const scanStillRunning = stage.kind === "scan" && !terminal;
    const hasStageTotal = stage.total > 0;
    const syncProgress = syncStatus?.progress;
    const stagePercent = terminalFailure
      ? null
      : stage.total > 0
      ? boundedProgressPercent((stage.current / stage.total) * 100, terminal)
      : terminal
        ? normalizedProgressPercent(syncStatus)
        : null;
    return {
      operation: scanStillRunning ? "sync_alphas" : undefined,
      status_code: scanStillRunning ? "SCAN" : stringField(syncProgress, "status_code"),
      status: syncStatus?.status,
      status_kind: syncStatus?.status_kind || stringField(syncProgress, "status_kind"),
      terminal: syncStatus?.terminal ?? booleanField(syncProgress, "terminal"),
      active: syncStatus?.active ?? booleanField(syncProgress, "active"),
      interrupted: syncStatus?.interrupted ?? booleanField(syncProgress, "interrupted"),
      recoverable: syncStatus?.recoverable ?? booleanField(syncProgress, "recoverable"),
      retryable: syncStatus?.retryable ?? booleanField(syncProgress, "retryable"),
      error: syncStatus?.error || stringField(syncProgress, "error"),
      error_code: stringField(syncProgress, "error_code"),
      user_error: syncStatus?.user_error || userErrorField(syncProgress),
      user_error_kind: syncStatus?.user_error_kind || stringField(syncProgress, "user_error_kind"),
      user_message: syncStatus?.user_message || stringField(syncProgress, "user_message"),
      next_action: syncStatus?.next_action || stringField(syncProgress, "next_action"),
      phase: scanStillRunning ? "scan" : syncStatus?.phase || syncStatus?.progress?.phase || "context_refresh",
      phase_label: phaseLabel(syncStatus),
      status_message: operationStatusMessage(syncStatus),
      percent_complete: scanStillRunning ? null : stagePercent,
      eta_seconds: terminalFailure ? null : stage.etaSeconds || null,
      eta_deadline_at_ms: stage.kind === "scan" || terminalFailure || !hasStageTotal ? null : firstPositiveNumber(numberField(syncStatus?.progress, "eta_deadline_at_ms"), resultNumberField(syncStatus, "eta_deadline_at_ms")) || null,
      done: stage.kind === "scan" ? undefined : stage.current || undefined,
      scanned: stage.kind === "scan" && !terminalFailure ? stage.current : undefined,
      total: stage.kind === "scan" || terminalFailure || stage.total <= 0 ? undefined : stage.total,
      api_reported_total: numberField(syncStatus?.progress, "api_reported_total") || undefined,
      remaining_items: numberField(syncStatus?.progress, "remaining_items") || undefined,
      has_more: typeof syncStatus?.progress?.has_more === "boolean" ? syncStatus.progress.has_more : undefined,
      pagination_complete: typeof syncStatus?.progress?.pagination_complete === "boolean" ? syncStatus.progress.pagination_complete : undefined,
      pagination_target: typeof syncStatus?.progress?.pagination_target === "string" ? syncStatus.progress.pagination_target : undefined,
      stop_reason: typeof syncStatus?.progress?.stop_reason === "string" ? syncStatus.progress.stop_reason : undefined,
      page_number: stage.pageNumber || undefined,
      pages_fetched: stage.pageNumber || undefined,
      expected_pages: stage.expectedPages || undefined,
      page_size: stage.pageSize || undefined,
      page_limit: stage.pageLimit || undefined,
      next_offset: stage.nextOffset || undefined,
      new_unique_items: stage.newUniqueItems || undefined,
      unique_items: stage.uniqueItems || undefined,
      confirming_total_boundary: stage.confirmingTotalBoundary || undefined,
      indeterminate: scanStillRunning || undefined,
      open_ended: scanStillRunning || undefined,
      job_id: syncStatus?.job_id,
      task_id: syncStatus?.task_id,
    };
  }
  if (mode === "readiness") {
    return {
      phase: "submit_readiness",
      phase_label: "阻断复核",
      status_message: readiness ? `阻断复核 ${readiness.eligible_count ?? 0} / 候选 ${readiness.candidate_count ?? 0}` : "正在读取提交前阻断复核证据。",
      percent_complete: readiness ? 100 : 35,
      checked: readiness?.candidate_count ?? 0,
      total: readiness?.candidate_count ?? 0,
    };
  }
  if (mode === "checks") {
    const count = checkResultCount(checks);
    return {
      phase: "check_results",
      phase_label: "检查结果",
      status_message: checks ? `已加载 ${count} 条检查结果。` : "正在读取检查结果。",
      percent_complete: checks ? 100 : 35,
      checked: count,
      total: count,
    };
  }
  return {
    phase: "idle",
    phase_label: "等待操作",
    status_message: "选择一个操作后，系统会在这里展示真实进度。",
    percent_complete: 0,
  };
}

function progressState(
  mode: OperationMode,
  syncRunning: boolean,
  syncStatus: JobStatus | null,
  readinessLoading: boolean,
  checksLoading: boolean,
  error: string | null,
) {
  if (error) return "error";
  if (syncRunning || readinessLoading || checksLoading) return "progress";
  const syncState = classifyJobState(syncStatus);
  if (mode === "context_refresh" && (syncState.failed || syncState.missing || syncState.interrupted)) return "error";
  if (mode !== "idle") return "success";
  return "idle";
}

function currentModeError(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  errors: { syncStart: string | null; syncStatus: string | null; readiness: string | null; checks: string | null },
) {
  if (mode === "context_refresh") {
    const syncState = classifyJobState(syncStatus);
    const stopped = syncState.interrupted;
    const recoverableMessage = stopped
      ? (syncStatus?.progress?.status_message || syncStatus?.status_message || "官方上下文刷新已停止，可重新刷新。")
      : "";
    if (syncStatus && (syncState.failed || syncState.missing || syncState.interrupted)) {
      return operationFailureMessage(syncStatus, "") || operationFailureMessage(errors.syncStart || errors.syncStatus || recoverableMessage, "");
    }
    return operationFailureMessage(
      syncStatus?.error || errors.syncStart || errors.syncStatus || recoverableMessage,
      "",
    );
  }
  if (mode === "readiness") return operationFailureMessage(errors.readiness, "");
  if (mode === "checks") return operationFailureMessage(errors.checks, "");
  return null;
}

function operationStatusMessage(status: JobStatus | null) {
  if (!status) return "尚未启动。";
  const scanMessage = runningScanStatusMessage(status);
  if (scanMessage) return scanMessage;
  const state = classifyJobState(status);
  const apiMessage = apiErrorMessage(status, "");
  if (apiMessage) return readableBackendText(apiMessage) || apiMessage;
  if (state.interrupted) return "官方上下文刷新已停止，结果未确认完成。";
  if (state.failed || state.missing) return "官方上下文刷新失败，请稍后重试或重新启动流程。";
  const sharedMessage = jobStatusMessage(status, "");
  const readableSharedMessage = readableBackendText(sharedMessage);
  if (readableSharedMessage) return readableSharedMessage;
  const message = (
    status.progress?.status_message ||
    status.status_message ||
    status.error ||
	    `当前状态: ${status.status || "未知"}`
  );
  const readableMessage = readableBackendText(message);
  if (readableMessage) return readableMessage;
  if (state.active || status.status === "running") return "官方上下文刷新正在运行，等待下一次状态更新。";
  return "官方上下文状态暂不明确，请刷新状态或重新启动流程。";
}

function normalizedProgressPercent(status: JobStatus | null) {
  const terminal = isTerminalSyncStatus(status);
  const raw = status?.progress?.percent_complete ?? status?.progress?.percent ?? status?.percent_complete;
  const value = Number(raw);
  if (Number.isFinite(value)) return boundedProgressPercent(value, terminal);
  const scanned = numberField(status?.progress, "scanned");
  const total = numberField(status?.progress, "total");
  if (total > 0) return boundedProgressPercent((scanned / total) * 100, terminal);
  if (terminal) return 100;
  if (status?.status === "running") return 35;
  return 0;
}

function boundedProgressPercent(value: number, terminal: boolean) {
  const upperBound = terminal ? 100 : 99;
  return Math.max(0, Math.min(upperBound, value));
}



function isSuccessfulSyncStatus(status: JobStatus | null) {
  return classifyJobState(status).successful;
}

function isRunningScanStatus(status: JobStatus | null) {
  return !isTerminalSyncStatus(status) && syncStageCode(status) === "SCAN";
}



function runningScanStatusMessage(status: JobStatus | null) {
  if (!isRunningScanStatus(status)) return "";
  const scanned = numberField(status?.progress, "scanned");
  const apiTotal = firstPositiveNumber(
    numberField(status?.progress, "api_reported_total"),
    numberField(status?.progress, "filter_window_count"),
  );
  if (scanned <= 0) return "正在扫描云端 Alpha，等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。";
  if (apiTotal > 0) {
    return `已拉取 ${formatCount(scanned)} 条云端 Alpha；接口分页参考数 ${formatCount(apiTotal)} 条，不是云端 Alpha 总量，会继续按分页自动确认边界；${syncScanPageSummary(status)}`;
  }
  return `已拉取 ${formatCount(scanned)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

function syncStageMetric(status: JobStatus | null): SyncStageMetric {
  const progress = status?.progress;
  const code = syncStageCode(status);
  const elapsedSeconds = firstPositiveNumber(
    numberField(progress, "elapsed_seconds"),
    resultNumberField(status, "elapsed_seconds"),
  );
  if (code === "SCAN") {
    return buildSyncStageMetric({
      kind: "scan",
      label: "云端 Alpha 扫描",
      rateLabel: "扫描速率",
      unit: "条云端 Alpha",
      rateUnit: "条/秒",
      current: firstPositiveNumber(numberField(progress, "scanned"), resultNumberField(status, "scanned")),
      total: firstPositiveNumber(
        numberField(progress, "api_reported_total"),
        numberField(progress, "filter_window_count"),
        resultNumberField(status, "api_reported_total"),
        resultNumberField(status, "filter_window_count"),
      ),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === "CONTEXT_FIELDS") {
    return buildSyncStageMetric({
      kind: "fields",
      label: "官方字段缓存",
      rateLabel: "字段刷新速率",
      unit: "个官方字段",
      rateUnit: "个/秒",
      current: firstPositiveNumber(numberField(progress, "fields_count"), resultNumberField(status, "fields_count")),
      total: firstPositiveNumber(numberField(progress, "fields_total"), resultNumberField(status, "fields_total")),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === "CONTEXT_OPERATORS") {
    return buildSyncStageMetric({
      kind: "operators",
      label: "官方算子缓存",
      rateLabel: "算子刷新速率",
      unit: "个官方算子",
      rateUnit: "个/秒",
      current: firstPositiveNumber(numberField(progress, "operators_count"), resultNumberField(status, "operators_count")),
      total: firstPositiveNumber(numberField(progress, "operators_total"), resultNumberField(status, "operators_total")),
      elapsedSeconds,
      progress,
      status,
    });
  }
  if (code === "CONTEXT_DATASETS") {
    return buildSyncStageMetric({
      kind: "datasets",
      label: "官方数据集缓存",
      rateLabel: "数据集刷新速率",
      unit: "个官方数据集",
      rateUnit: "个/秒",
      current: firstPositiveNumber(numberField(progress, "datasets_count"), resultNumberField(status, "datasets_count")),
      total: firstPositiveNumber(numberField(progress, "datasets_total"), resultNumberField(status, "datasets_total")),
      elapsedSeconds,
      progress,
      status,
    });
  }
  return buildSyncStageMetric({
    kind: "other",
    label: "当前阶段",
    rateLabel: "处理速率",
    unit: "项",
    rateUnit: "项/秒",
    current: 0,
    total: 0,
    elapsedSeconds,
    progress,
    status,
  });
}

function buildSyncStageMetric({
  kind,
  label,
  rateLabel,
  unit,
  rateUnit,
  current,
  total,
  elapsedSeconds,
  progress,
  status,
}: {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  progress?: Record<string, unknown>;
  status: JobStatus | null;
}): SyncStageMetric {
  const etaSeconds = kind !== "scan" && current > 0 && total > current
    ? firstPositiveNumber(numberField(progress, "eta_seconds"), resultNumberField(status, "eta_seconds"))
    : 0;
  const reportedRate = firstPositiveFloat(numberField(progress, "rate_per_second"), resultNumberField(status, "rate_per_second"));
  const derivedRate = current > 0 && elapsedSeconds > 0 ? current / elapsedSeconds : 0;
  return {
    kind,
    label,
    rateLabel,
    unit,
    rateUnit,
    current: Math.max(0, Math.trunc(current || 0)),
    total: Math.max(0, Math.trunc(total || 0)),
    elapsedSeconds,
    etaSeconds,
    ratePerSecond: firstPositiveFloat(reportedRate, derivedRate),
    pageNumber: firstPositiveNumber(numberField(progress, "pages_fetched"), numberField(progress, "page_number")),
    expectedPages: firstPositiveNumber(numberField(progress, "expected_pages")),
    pageSize: firstPositiveNumber(numberField(progress, "page_size")),
    pageLimit: firstPositiveNumber(numberField(progress, "page_limit")),
    nextOffset: firstPositiveNumber(numberField(progress, "next_offset")),
    newUniqueItems: firstPositiveNumber(numberField(progress, "new_unique_items")),
    uniqueItems: firstPositiveNumber(numberField(progress, "unique_items")),
    confirmingTotalBoundary: Boolean(progress?.confirming_total_boundary),
  };
}

function scanEtaDetail(stage: SyncStageMetric) {
  if (stage.current <= 0) {
    return "正在扫描云端 Alpha；等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。";
  }
  if (stage.total > 0) {
    return `接口分页参考数 ${formatCount(stage.total)} 条；${syncStagePageSummary(stage)}`;
  }
  return `已拉取 ${formatCount(stage.current)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。`;
}

function syncScanPageSummary(status: JobStatus | null) {
  return syncStagePageSummary(syncStageMetric(status));
}

function syncStagePageSummary(stage: SyncStageMetric) {
  const page = stage.pageNumber > 0
    ? `当前第 ${formatCount(stage.pageNumber)} 页`
    : "分页页码确认中";
  const parts = [page];
  if (stage.pageSize > 0) parts.push(`本页 ${formatCount(stage.pageSize)} 条`);
  if (stage.pageLimit > 0) parts.push(`分页参数 ${formatCount(stage.pageLimit)} 条/页`);
  if (stage.nextOffset > 0) parts.push(syncNextOffsetLabel(stage.nextOffset, stage.total));
  if (stage.newUniqueItems > 0) parts.push(`本页新增 ${formatCount(stage.newUniqueItems)} 条`);
  if (stage.uniqueItems > 0) parts.push(`已确认唯一 ${formatCount(stage.uniqueItems)} 条`);
  if (stage.confirmingTotalBoundary) parts.push("本页已满，继续确认下一页");
  return parts.join("；");
}

function syncNextOffsetLabel(nextOffset: number, filterWindowCount: number) {
  if (filterWindowCount > 0 && nextOffset >= filterWindowCount) {
    return "下一请求确认分页边界";
  }
  return "下一轮继续拉取";
}

function syncStageCode(status: JobStatus | null) {
  return String(status?.progress?.status_code || status?.phase || status?.progress?.phase || "context_refresh").toUpperCase();
}

function phaseLabel(status: JobStatus | null) {
  const code = String(status?.progress?.status_code || status?.phase || status?.progress?.phase || "context_refresh");
  const normalizedCode = code.toUpperCase();
  const labels: Record<string, string> = {
    AUTH: "认证",
    SCAN: "扫描云端",
    MERGE: "合并快照",
    CONTEXT_FIELDS: "刷新字段",
    CONTEXT_OPERATORS: "刷新算子",
    CONTEXT_DATASETS: "刷新数据集",
    CONTEXT_FAILED: "上下文失败",
    CONTEXT_REFRESH: "刷新上下文",
    REFRESH_CONTEXT: "刷新上下文",
    LOCAL_CACHE: "本地缓存",
    LOCAL_CACHE_INVALID: "缓存需刷新",
    SESSION_INVALID: "需要重新连接",
    COMPLETED: "完成",
    COMPLETED_WITH_WARNINGS: "带警告完成",
    QUEUED: "已排队",
    RUNNING: "运行中",
    STOPPED: "已停止",
    FAILED: "失败",
  };
  return labels[normalizedCode] || "当前阶段";
}



function isSessionInvalidResult(result: ({ ok?: boolean; error_code?: string; error?: string } & Partial<JobStatus>) | null) {
  if (!result || result.ok !== false) return false;
  return isSessionInvalidPayload(result);
}

function fieldFromProgress(status: JobStatus | null, field: string) {
  const fromProgress = numberField(status?.progress, field);
  if (fromProgress > 0) return String(fromProgress);
  const result = status?.result as Record<string, unknown> | undefined;
  const fromResult = Number(result?.[field]);
  if (Number.isFinite(fromResult) && fromResult > 0) return String(fromResult);
  const fromCache = contextCacheNumber(status?.official_context_cache, field);
  return fromCache > 0 ? String(fromCache) : "-";
}

function contextSummaryField(status: JobStatus | null, field: string) {
  const value = contextSummaryNumber(status, field);
  return value > 0 ? String(value) : "-";
}

function officialContextSummaryMessage(status: JobStatus | null) {
  const cache = status?.official_context_cache;
  const cacheCounts = {
    fields: contextCacheNumber(cache, "fields_count"),
    operators: contextCacheNumber(cache, "operators_count"),
    datasets: contextCacheNumber(cache, "datasets_count"),
  };
  const displayCounts = {
    fields: contextSummaryNumber(status, "fields_count"),
    operators: contextSummaryNumber(status, "operators_count"),
    datasets: contextSummaryNumber(status, "datasets_count"),
  };
  const hasCache = cacheCounts.fields > 0 || cacheCounts.operators > 0 || cacheCounts.datasets > 0;
  const hasDisplayCounts = displayCounts.fields > 0 || displayCounts.operators > 0 || displayCounts.datasets > 0;
  const cacheError = typeof cache?.error === "string" ? cache.error.trim() : "";
  const cacheComplete = contextCacheComplete(cache);
  const statusMessage = status
    ? operationStatusMessage(status)
    : "尚未启动官方上下文刷新。";
  if (cacheError && !hasCache) {
    return `${statusMessage} 本地官方上下文缓存摘要读取失败，请点击开始刷新或稍后重试。`;
  }
  if (cache && !cacheComplete && !hasDisplayCounts) {
    const invalid = cache.manifest?.invalid_files?.length
      ? `异常文件: ${cache.manifest.invalid_files.join("、")}`
      : "缓存文件数量或校验和不一致";
    return `${statusMessage} 本地官方上下文缓存完整性未通过，已停止加载展示；请点击开始刷新。${invalid}。`;
  }
  if (!hasCache && !hasDisplayCounts) return statusMessage;
  const stale = Boolean(cache?.manifest?.is_stale);
  const cacheLabel = stale ? "本地缓存存在但需要刷新" : "本地缓存可用";
  const countSourceLabel = cacheComplete ? cacheLabel : "本次刷新结果";
  const counts = cacheComplete ? cacheCounts : displayCounts;
  const cacheText = `${countSourceLabel}: 字段 ${formatCount(counts.fields)}，算子 ${formatCount(counts.operators)}，数据集 ${formatCount(counts.datasets)}`;
  const statusText = String(status?.status || "");
  const state = classifyJobState(status);
  if (state.failed || state.interrupted) {
    return `最近刷新未完成: ${statusMessage}；${cacheText}。`;
  }
  if (!status || statusText === "idle") return `${statusMessage} ${cacheText}。`;
  return `${statusMessage} ${cacheText}。`;
}

function officialContextInlineSummary(status: JobStatus | null) {
  const fields = contextSummaryField(status, "fields_count");
  const operators = contextSummaryField(status, "operators_count");
  const datasets = contextSummaryField(status, "datasets_count");
  const contextError = String(status?.progress?.context_error || resultStringField(status, "context_error") || "").trim();
  if (fields === "-" && operators === "-" && datasets === "-") {
    return "暂无通过完整性校验的官方上下文缓存统计，等待同步状态返回或手动刷新。";
  }
  if (contextError) {
    return `上下文刷新未完成，可仅重试上下文；当前缓存：字段 ${fields}，算子 ${operators}，数据集 ${datasets}。`;
  }
  if (!status) return "启动后这里会显示字段、算子和数据集缓存的快速摘要。";
  return `快速摘要：字段 ${fields}，算子 ${operators}，数据集 ${datasets}。`;
}

function canRetryContextOnly(status: JobStatus | null) {
  if (!status) return false;
  const result = status.result && typeof status.result === "object" && !Array.isArray(status.result)
    ? status.result as Record<string, unknown>
    : {};
  const contextStatus = String(status.progress?.context_status || result.context_status || "").toLowerCase();
  const contextError = String(status.progress?.context_error || result.context_error || "").trim();
  return Boolean(contextError || contextStatus === "failed");
}

function contextSummaryNumber(status: JobStatus | null, field: string) {
  return firstPositiveNumber(
    contextCacheNumber(status?.official_context_cache, field),
    numberField(status?.progress, field),
    resultNumberField(status, field),
  );
}

function contextCacheNumber(cache: OfficialContextCache | undefined, field: string) {
  if (!contextCacheComplete(cache)) return 0;
  return firstPositiveNumber(
    numberField(cache as Record<string, unknown> | undefined, field),
    contextCacheManifestRecordCount(cache, field),
  );
}



function contextCacheManifestRecordCount(cache: OfficialContextCache | undefined, field: string) {
  const filename = {
    fields_count: "official_fields.json",
    operators_count: "official_operators.json",
    datasets_count: "official_datasets.json",
  }[field];
  return filename ? numberField(cache?.manifest?.record_counts, filename) : 0;
}

function cloudAlphaCacheReady(cache: CloudAlphaCache | undefined) {
  if (!cache?.ok) return false;
  const count = firstPositiveNumber(cache.count, cache.total);
  return count > 0 || (cache.count == null && cache.total == null);
}

function cloudAlphaCacheUpdatedAt(cache: CloudAlphaCache | undefined) {
  const loadedAt = Date.parse(String(cache?.loaded_at || ""));
  return Number.isFinite(loadedAt) ? new Date(loadedAt) : null;
}

function resultNumberField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return 0;
  const value = Number((result as Record<string, unknown>)[field]);
  return Number.isFinite(value) ? value : 0;
}

function resultStringField(status: JobStatus | null, field: string) {
  const result = status?.result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return "";
  return String((result as Record<string, unknown>)[field] || "");
}

function firstPositiveNumber(...values: Array<number | null | undefined>) {
  const value = values.find((item) => Number.isFinite(item) && Number(item) > 0);
  return Number.isFinite(value) ? Number(value) : 0;
}

function numberField(source: Record<string, unknown> | undefined, field: string) {
  const value = Number(source?.[field]);
  return Number.isFinite(value) ? value : 0;
}

function stringField(source: Record<string, unknown> | undefined, field: string) {
  const value = source?.[field];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function booleanField(source: Record<string, unknown> | undefined, field: string) {
  const value = source?.[field];
  return typeof value === "boolean" ? value : undefined;
}

function userErrorField(source: Record<string, unknown> | undefined) {
  const value = source?.user_error;
  return value && typeof value === "object" ? value as UnifiedProgress["user_error"] : undefined;
}

function syncStatusUpdatedAt(status: JobStatus | null) {
  const progressUpdated = numberField(status?.progress, "updated_at_ms");
  if (progressUpdated > 0) return new Date(progressUpdated);
  const resultUpdated = resultNumberField(status, "updated_at_ms");
  if (resultUpdated > 0) return new Date(resultUpdated);
  const startedAt = Date.parse(String(status?.started_at || ""));
  if (Number.isFinite(startedAt)) return new Date(startedAt);
  return status ? new Date() : null;
}
