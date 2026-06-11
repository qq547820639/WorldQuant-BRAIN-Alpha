/** Button-driven official operations panel for browser-only user workflows. */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useApi } from "@/hooks/useApi";
import type { BrainCredentials, JobStatus, SubmitReadinessResponse, UnifiedProgress } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";
import { reportIgnoredError } from "@/utils/reportIgnoredError";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  credentials?: BrainCredentials;
  autoStart?: boolean;
  connectionReady?: boolean;
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

type OperationMode = "idle" | "context_refresh" | "readiness" | "checks";
type OverviewTone = "success" | "warning" | "neutral";
type SyncStageKind = "scan" | "fields" | "operators" | "datasets" | "other";
type SyncRange = "3d" | "7d" | "recent" | "6months" | "all";

interface SyncStageMetric {
  kind: SyncStageKind;
  label: string;
  rateLabel: string;
  unit: string;
  rateUnit: string;
  current: number;
  total: number;
  elapsedSeconds: number;
  etaSeconds: number;
  ratePerSecond: number;
  pageNumber: number;
  expectedPages: number;
  pageSize: number;
  pageLimit: number;
  nextOffset: number;
  newUniqueItems: number;
  uniqueItems: number;
  confirmingTotalBoundary: boolean;
}

interface SyncProgressMonitorState {
  jobId: string;
  signature: string;
  sinceMs: number;
  warned: boolean;
  interrupting: boolean;
}

const POLL_INTERVAL_MS = 2000;
const SYNC_STATUS_FAILURE_LIMIT = 3;
const SYNC_PROGRESS_STALL_WARNING_MS = 30_000;
const SYNC_PROGRESS_STALL_STOP_MS = 90_000;
const OPERATION_REQUEST_TIMEOUT_MS = 10000;
const STOP_RETRY_AFTER_MS = 60_000;
const MAX_LOG_ROWS = 80;
const ACTIVE_SYNC_JOB_ID_KEY = "brain_alpha_active_sync_job_id";

export default function OfficialOperationsPanel({
  notify,
  credentials,
  autoStart = false,
  connectionReady = true,
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
      result?.error || (result as { error_code?: string } | null)?.error_code,
      "本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。",
    );
    setMode("context_refresh");
    setContextOnlyMode(false);
    setSyncJobId(jobId);
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
  }, [appendLog, notify]);

  const applyRecoveredSyncStatus = useCallback((result: JobStatus) => {
    const jobId = String(result?.job_id || result?.task_id || "");
    if (!jobId) return false;
    const terminal = isTerminalSyncStatus(result);
    setMode("context_refresh");
    setContextOnlyMode(Boolean(result?.progress?.context_only || (result?.result as Record<string, unknown> | undefined)?.context_only));
    setSyncJobId(jobId);
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
  }, [appendLog, notify, resetSyncProgressMonitor]);

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
        const message = operationFailureMessage(result?.error || result?.error_code, "提交前阻断复核证据读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
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
        const message = operationFailureMessage(result?.error || result?.error_code, "质量检查结果读取失败。请重试；若连续失败，请重新打开页面或联系维护者。");
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
        result?.error || result?.error_code,
        "已有官方上下文刷新正在运行，已接管当前任务状态。",
      );
      saveStoredSyncJobId(jobId);
      resetSyncStart();
      setSyncJobId(jobId);
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
      const message = operationFailureMessage(result?.error || result?.error_code, "官方上下文刷新启动失败。请重试；若连续失败，请重新打开页面或联系维护者。");
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
    setSyncJobId(jobId);
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
  }, [appendLog, callSyncStart, connectionReady, credentials, notify, resetSyncProgressMonitor, resetSyncStart, syncRange]);

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
      const cancelMessage = operationFailureMessage(result?.error || result?.error_code, "停止请求暂未确认。请稍后重新读取状态。");
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
    syncPollInFlightRef.current = true;
    try {
      const result = await callSyncStatus<JobStatus>(`/api/sync_status?job_id=${encodeURIComponent(syncJobId)}&compact=1`);
      if (!result?.ok) {
        const message = operationFailureMessage(result?.error || result?.error_code, "刷新状态读取失败。");
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
      const statusText = String(result?.status || "");
	      if (["completed", "completed_with_warnings"].includes(statusText)) {
	        clearStoredSyncJobId();
	        setSyncRunning(false);
	        setStoppingSinceMs(0);
	        syncPollFailureCountRef.current = 0;
	        resetSyncProgressMonitor();
	        appendLog(statusText === "completed" ? "success" : "warning", operationStatusMessage(result));
	        notify(statusText === "completed" ? "success" : "warning", "官方上下文刷新完成");
	        onSyncCompleted?.();
      } else if (["failed", "cancelled", "canceled", "stopped"].includes(statusText)) {
	        clearStoredSyncJobId();
	        setSyncRunning(false);
	        setStoppingSinceMs(0);
	        syncPollFailureCountRef.current = 0;
	        resetSyncProgressMonitor();
	        appendLog(statusText === "failed" ? "error" : "warning", operationStatusMessage(result));
	        notify(statusText === "failed" ? "error" : "warning", operationStatusMessage(result));
	      } else if (statusText === "stopping") {
	        const since = numberField(result.progress, "stopping_since_ms") || stoppingSinceMs || Date.now();
	        setStoppingSinceMs(since);
	      }
	    } finally {
	      syncPollInFlightRef.current = false;
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
      const message = operationFailureMessage(result?.error || result?.error_code, "停止请求失败。请稍后重试。");
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
	  const syncOverview = syncDataOverview(syncStatus, syncRunning);
	  const officialContextSummary = officialContextSummaryMessage(syncStatus);
	  const canRetryContext = canRetryContextOnly(syncStatus);
  const syncNeedsRetry = ["failed", "stopped", "cancelled", "canceled"].includes(String(syncStatus?.status || ""));
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
            <OperationMetric label="官方上下文" value={syncContextStatus(syncStatus)} tone={syncRunning ? "warning" : syncStatus?.status === "completed" ? "success" : "neutral"} />
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
            status={syncStatus?.status === "stopping" ? "停止中" : syncRunning ? "运行中" : syncStatus ? syncContextStatus(syncStatus) : "待启动"}
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

	        {(syncJobId || syncStatus?.official_context_cache) && (
	          <section className="rounded-md border border-border-subtle bg-[oklch(0.115_0.007_45)] p-3" aria-label="官方上下文快速摘要">
	            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
	              <dl className="grid min-w-0 flex-1 grid-cols-3 gap-3 text-sm">
	                <SummaryMetric label="字段" value={contextSummaryField(syncStatus, "fields_count")} />
	                <SummaryMetric label="算子" value={contextSummaryField(syncStatus, "operators_count")} />
	                <SummaryMetric label="数据集" value={contextSummaryField(syncStatus, "datasets_count")} />
	              </dl>
	              {canRetryContext && (
	                <button type="button" className="btn btn-secondary text-sm" onClick={startContextOnlyRefresh} disabled={syncRunning || syncStartApi.loading}>
	                  仅重试上下文
	                </button>
	              )}
	            </div>
		            <p className="mt-2 text-sm leading-6 text-text-secondary">{officialContextInlineSummary(syncStatus)}</p>
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
                    前往「候选管理」，点击「运行官方模拟」或候选行「单个模拟」，补齐 official_alpha_id 与 official_metrics。完成后回到这里点击「读取复核」。
                  </p>
                )}
                {needsSubmitBandAction && (
                  <p className="mt-1">
                    当前候选尚未进入 submit_candidate 复核带；先在候选管理继续筛选/评分，进入复核带后再运行官方模拟。
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
	            <BlockerList title={countTitle("最佳候选阻断", allBestCandidateReasons.length)} rows={allBestCandidateReasons.map(readinessReasonLabel)} empty="暂无最佳候选阻断" />
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
	            <SummaryMetric label="字段" value={contextSummaryField(syncStatus, "fields_count")} />
	            <SummaryMetric label="算子" value={contextSummaryField(syncStatus, "operators_count")} />
	            <SummaryMetric label="数据集" value={contextSummaryField(syncStatus, "datasets_count")} />
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

function findingText(row: { code?: string; message?: string }) {
  const code = readinessReasonLabel(row.code || "");
  const message = readableBackendText(row.message || "");
  if (message && message !== code) return `${code}: ${message}`;
  return code;
}

function readinessReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    candidate_family_missing_official_alpha_id: "候选族缺少官方 Alpha ID",
    candidate_family_missing_official_metrics: "候选族缺少官方仿真指标",
    candidate_family_not_submit_band: "候选族尚未进入复核带",
    decision_band_not_submit_candidate: "评分决策仍非提交候选",
    optimize: "需要继续优化",
    research_only: "仅限研究",
    submit_candidate: "提交前复核候选",
    high_cloud_similarity: "云端相似度过高",
    high_turnover_generation_risk: "生成表达式存在高换手风险",
    local_backtest_failed: "本地回测未通过",
    missing_cloud_similarity: "缺少云端相似度证据",
    missing_official_alpha_id: "缺少官方 Alpha ID",
    missing_official_metrics: "缺少官方仿真指标",
    no_submit_ready_candidate: "没有提交前复核候选",
    not_submission_ready: "尚未达到阻断复核通过标准",
    official_validation_without_simulation: "有官方验证但缺少官方仿真指标",
  };
  return labels[reason] || reason || "-";
}

function riskLevelLabel(level: string) {
  const labels: Record<string, string> = {
    high: "高",
    medium: "中",
    low: "低",
  };
  return labels[level] || level || "-";
}

function actionStepLabel(step: string) {
  const labels: Record<string, string> = {
    "review final submission intent before any real submit": "真实提交前先人工复核最终提交意图",
    "resolve local blockers before submit review": "先修复本地阻断，再进入提交复核",
    "run official simulation/check in a trusted environment": "在可信环境运行官方仿真/检查",
  };
  return labels[step] || readableBackendText(step) || step;
}

function operationFailureMessage(raw: unknown, fallback: string) {
  const message = readableBackendText(raw);
  return message || fallback;
}

function readableBackendText(raw: unknown) {
  const value = String(raw || "").trim();
  if (value === "official context timeout" || value === "OFFICIAL_CONTEXT_REFRESH_TIMEOUT") {
    return "官方上下文刷新超时，请稍后重试。";
  }
  const httpMatch = value.match(/^HTTP[_\s-]?(\d{3})\b/i);
  if (httpMatch) {
    const status = httpMatch[1];
    if (status === "429") return "BRAIN 官方接口请求过于频繁，请稍后重试。";
    if (status === "401" || status === "403") return "BRAIN 连接已失效，请重新测试连接后继续。";
    if (status === "408") return "BRAIN 官方接口响应超时，请稍后重试。";
    if (status === "500" || status === "502" || status === "503" || status === "504") {
      return `BRAIN 官方接口暂时不可用（HTTP ${status}），请稍后重试。`;
    }
  }
  if (/network error|urlopen error|connection reset|connection aborted|remote end closed/i.test(value)) {
    return "网络连接异常，无法读取 BRAIN 官方接口。请检查网络后重试。";
  }
  if (/timed out|timeout/i.test(value)) {
    return "请求超时，BRAIN 官方接口仍未返回。请稍后重试或缩小同步范围。";
  }
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
  return labels[value] || value;
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

function requestDeadline() {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), OPERATION_REQUEST_TIMEOUT_MS);
  return {
    signal: controller.signal,
    clear: () => window.clearTimeout(timer),
  };
}

function syncDataOverview(syncStatus: JobStatus | null, syncRunning: boolean) {
  const statusValue = syncRunning ? "同步中" : syncContextStatus(syncStatus);
  const stage = syncStageMetric(syncStatus);
  const statusDetail = syncStatus
    ? `${phaseLabel(syncStatus)}: ${operationStatusMessage(syncStatus)}`
    : "等待启动云端 Alpha 同步。";
  let statusTone: OverviewTone = "neutral";
  if (syncRunning) statusTone = "warning";
  else if (syncStatus?.status === "completed" || syncStatus?.status === "completed_with_warnings") statusTone = "success";
  else if (syncStatus?.status === "failed" || syncStatus?.status === "missing") statusTone = "warning";
  const updatedAt = syncStatusUpdatedAt(syncStatus);
  const total = syncDataTotal(syncStatus);

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
    updatedAtDetail: updatedAt ? "来自本次同步进度。" : "暂无同步更新时间。",
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

function syncDataTotal(syncStatus: JobStatus | null) {
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
  if (reportedTotal > 0) {
    return {
      totalValue: `分页参考数 ${formatCount(reportedTotal)}`,
      totalDetail: "接口分页参考数；尚未完成实际同步确认，不是云端 Alpha 总量。",
      totalTone: "neutral" as const,
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
    const stagePercent = terminalFailure
      ? null
      : stage.total > 0
      ? boundedProgressPercent((stage.current / stage.total) * 100, terminal)
      : terminal
        ? normalizedProgressPercent(syncStatus)
        : null;
    return {
      operation: scanStillRunning ? "sync_alphas" : undefined,
      status_code: scanStillRunning ? "SCAN" : undefined,
      status: syncStatus?.status,
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
  if (mode === "context_refresh" && syncStatus?.status === "failed") return "error";
  if (mode === "context_refresh" && (syncStatus?.status === "missing" || syncStatus?.phase === "session_invalid")) return "error";
  if (mode === "context_refresh" && ["stopped", "cancelled", "canceled"].includes(String(syncStatus?.status || ""))) return "error";
  if (mode !== "idle") return "success";
  return "idle";
}

function currentModeError(
  mode: OperationMode,
  syncStatus: JobStatus | null,
  errors: { syncStart: string | null; syncStatus: string | null; readiness: string | null; checks: string | null },
) {
  if (mode === "context_refresh") {
    const stopped = ["stopped", "cancelled", "canceled"].includes(String(syncStatus?.status || ""));
    const recoverableMessage = stopped
      ? (syncStatus?.progress?.status_message || syncStatus?.status_message || "官方上下文刷新已停止，可重新刷新。")
      : "";
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
  const message = (
    status.progress?.status_message ||
    status.status_message ||
    status.error ||
	    `当前状态: ${status.status || "未知"}`
  );
  return readableBackendText(message) || message;
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

function isTerminalSyncStatus(status: JobStatus | null) {
  return ["completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled"].includes(String(status?.status || ""));
}

function isSuccessfulSyncStatus(status: JobStatus | null) {
  return ["completed", "completed_with_warnings"].includes(String(status?.status || ""));
}

function isRunningScanStatus(status: JobStatus | null) {
  return !isTerminalSyncStatus(status) && syncStageCode(status) === "SCAN";
}

function syncProgressMonitorSignature(status: JobStatus | null) {
  if (!isRunningScanStatus(status)) return "";
  const progress = status?.progress;
  const parts = [
    syncStageCode(status),
    numberField(progress, "scanned"),
    numberField(progress, "pages_fetched") || numberField(progress, "page_number"),
    numberField(progress, "next_offset"),
    numberField(progress, "new_unique_items"),
    numberField(progress, "unique_items"),
    numberField(progress, "page_size"),
  ];
  return parts.join(":");
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
    SESSION_INVALID: "需要重新连接",
    session_invalid: "需要重新连接",
    COMPLETED: "完成",
    COMPLETED_WITH_WARNINGS: "带警告完成",
    QUEUED: "已排队",
    STOPPED: "已停止",
    FAILED: "失败",
  };
  return labels[normalizedCode] || code;
}

function syncContextStatus(status: JobStatus | null) {
  const text = String(status?.status || "");
  if (!text) return "待启动";
  if (text === "completed_with_warnings") return "带警告";
  if (text === "completed") return "已刷新";
  if (text === "running" || text === "queued") return "进行中";
  if (text === "failed") return "失败";
  if (text === "missing" || status?.phase === "session_invalid") return "监控受阻";
  if (text === "stopped" || text === "cancelled") return "已停止";
  return text;
}

function isSessionInvalidResult(result: ({ ok?: boolean; error_code?: string; error?: string } & Partial<JobStatus>) | null) {
  if (!result || result.ok !== false) return false;
  return String(result.error_code || result.error || "") === "SESSION_INVALID"
    || String(result.error || "") === "invalid local session";
}

function fieldFromProgress(status: JobStatus | null, field: string) {
  const fromProgress = numberField(status?.progress, field);
  if (fromProgress > 0) return String(fromProgress);
  const result = status?.result as Record<string, unknown> | undefined;
  const fromResult = Number(result?.[field]);
  if (Number.isFinite(fromResult) && fromResult > 0) return String(fromResult);
  const fromCache = contextCacheNumber(status, field);
  return fromCache > 0 ? String(fromCache) : "-";
}

function contextSummaryField(status: JobStatus | null, field: string) {
  const fromCache = contextCacheNumber(status, field);
  if (fromCache > 0) return String(fromCache);
  const code = syncStageCode(status);
  if (code === "CONTEXT_FIELDS" || code === "CONTEXT_OPERATORS" || code === "CONTEXT_DATASETS" || code === "CONTEXT_FAILED") {
    return fieldFromProgress(status, field);
  }
  return "-";
}

function officialContextSummaryMessage(status: JobStatus | null) {
  const cache = status?.official_context_cache;
  const cacheCounts = {
    fields: contextCacheNumber(status, "fields_count"),
    operators: contextCacheNumber(status, "operators_count"),
    datasets: contextCacheNumber(status, "datasets_count"),
  };
  const hasCache = cacheCounts.fields > 0 || cacheCounts.operators > 0 || cacheCounts.datasets > 0;
  const cacheError = typeof cache?.error === "string" ? cache.error.trim() : "";
  const statusMessage = status
    ? operationStatusMessage(status)
    : "尚未启动官方上下文刷新。";
  if (cacheError && !hasCache) {
    return `${statusMessage} 本地官方上下文缓存摘要读取失败: ${cacheError}`;
  }
  if (!hasCache) return statusMessage;
  const stale = Boolean(cache?.manifest?.is_stale);
  const complete = cache?.manifest?.complete !== false;
  const cacheLabel = stale || !complete ? "本地缓存存在但需要刷新" : "本地缓存可用";
  const cacheText = `${cacheLabel}: 字段 ${formatCount(cacheCounts.fields)}，算子 ${formatCount(cacheCounts.operators)}，数据集 ${formatCount(cacheCounts.datasets)}`;
  const statusText = String(status?.status || "");
  if (["failed", "stopped", "cancelled", "canceled"].includes(statusText)) {
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

function contextCacheNumber(status: JobStatus | null, field: string) {
  return numberField(status?.official_context_cache as Record<string, unknown> | undefined, field);
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

function firstPositiveNumber(...values: number[]) {
  return values.find((value) => Number.isFinite(value) && value > 0) || 0;
}

function numberField(source: Record<string, unknown> | undefined, field: string) {
  const value = Number(source?.[field]);
  return Number.isFinite(value) ? value : 0;
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

function formatCount(value: number) {
  return Math.max(0, Math.trunc(value)).toLocaleString("zh-CN");
}

function formatDuration(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds <= 0) return "0s";
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = Math.round(totalSeconds % 60);
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

function firstPositiveFloat(...values: number[]) {
  return values.find((value) => Number.isFinite(value) && value > 0) || 0;
}

function checkResultCount(payload: CheckResultsResponse | null | { count?: number; items?: unknown; checks?: unknown }) {
  if (!payload) return 0;
  const direct = Number(payload.count);
  if (Number.isFinite(direct) && direct >= 0) return direct;
  if (Array.isArray(payload.items)) return payload.items.length;
  if (Array.isArray(payload.checks)) return payload.checks.length;
  return 0;
}

function credentialsPayload(credentials?: BrainCredentials) {
  const payload: Record<string, string> = {};
  const username = credentials?.username.trim() || "";
  const password = credentials?.password || "";
  const token = credentials?.token.trim() || "";
  if (username) payload.username = username;
  if (password) payload.password = password;
  if (token) payload.token = token;
  return payload;
}

function hasPageCredentials(credentials?: BrainCredentials) {
  return Boolean(
    credentials?.username.trim() ||
    credentials?.password ||
    credentials?.token.trim()
  );
}

function saveStoredSyncJobId(jobId: string): void {
  const value = String(jobId || "").trim();
  if (!value) return;
  try {
    sessionStorage.setItem(ACTIVE_SYNC_JOB_ID_KEY, value);
  } catch (error) {
    reportIgnoredError("official sync job id sessionStorage save failed", error);
  }
}

function loadStoredSyncJobId(): string {
  try {
    return String(sessionStorage.getItem(ACTIVE_SYNC_JOB_ID_KEY) || "").trim();
  } catch (error) {
    reportIgnoredError("official sync job id sessionStorage load failed", error);
    return "";
  }
}

function clearStoredSyncJobId(): void {
  try {
    sessionStorage.removeItem(ACTIVE_SYNC_JOB_ID_KEY);
  } catch (error) {
    reportIgnoredError("official sync job id sessionStorage clear failed", error);
  }
}

function logTone(tone: OperationLogEntry["tone"]) {
  if (tone === "success") return "text-positive";
  if (tone === "warning") return "text-warning";
  if (tone === "error") return "text-negative";
  return "text-text-secondary";
}

function logDotTone(tone: OperationLogEntry["tone"]) {
  if (tone === "success") return "status-dot status-dot-active";
  if (tone === "warning") return "status-dot status-dot-warning";
  if (tone === "error") return "status-dot status-dot-error";
  return "status-dot status-dot-idle";
}

function formatClock(date = new Date()) {
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

function shortOperationId(value: string) {
  const text = String(value || "").trim();
  if (text.length <= 12) return text;
  return `${text.slice(0, 6)}...${text.slice(-4)}`;
}
