/** OfficialOperations orchestration hook plus log and state hooks. */

import { useCallback, useRef, useState } from 'react';
import { useApi } from '@/hooks/useApi';
import { classifyJobState } from '@/helpers/runPayload';
import type {
  BrainCredentials,
  CloudAlphaCache,
  JobStatus,
  OfficialContextCache,
  SubmitReadinessResponse,
} from '@/types';
import { useSyncRecovery, useSyncStop } from './useSyncControl';
import { useReadinessChecks, useSyncOperations } from './useSyncWorkflow';
import type {
  OperationLogEntry,
  OperationMode,
  SyncProgressMonitorState,
  SyncRange,
} from './utils';
import {
  MAX_LOG_ROWS,
  SYNC_PROGRESS_STALL_STOP_MS,
  SYNC_PROGRESS_STALL_WARNING_MS,
  canRetryContextOnly,
  currentModeError,
  formatClock,
  formatDuration,
  operationProgress,
  progressState,
  syncDataOverview,
  syncHistoryReadErrorTitle,
  syncProgressMonitorSignature,
  syncStatusForDisplay,
} from './utils';

export function useOperationLog() {
  const [logs, setLogs] = useState<OperationLogEntry[]>([
    {
      time: formatClock(),
      tone: 'info',
      message: '官方操作已就绪。请选择要执行的操作。',
    },
  ]);

  const appendLog = useCallback((tone: OperationLogEntry['tone'], message: string) => {
    setLogs((previous) => [
      ...previous.slice(-(MAX_LOG_ROWS - 1)),
      { time: formatClock(), tone, message },
    ]);
  }, []);

  return {
    logs,
    setLogs,
    appendLog,
  };
}

interface CheckResultsResponse {
  items?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
  count?: number;
  ok?: boolean;
  data?: CheckResultsResponse;
}

export function useOfficialOperationsState() {
  const [mode, setMode] = useState<OperationMode>('idle');
  const [syncJobId, setSyncJobId] = useState('');
  const [syncStatus, setSyncStatus] = useState<JobStatus | null>(null);
  const [syncRunning, setSyncRunning] = useState(false);
  const [syncRange, setSyncRange] = useState<SyncRange>('all');
  const [contextOnlyMode, setContextOnlyMode] = useState(false);
  const [stoppingSinceMs, setStoppingSinceMs] = useState(0);
  const [stoppingNowMs, setStoppingNowMs] = useState(0);

  const syncPollInFlightRef = useRef(false);
  const activeSyncJobIdRef = useRef('');
  const syncPollGenerationRef = useRef(0);
  const syncPollFailureCountRef = useRef(0);
  const syncProgressMonitorRef = useRef<SyncProgressMonitorState>({
    jobId: '',
    signature: '',
    sinceMs: 0,
    warned: false,
    interrupting: false,
  });
  const syncRecoveryAttemptedRef = useRef(false);
  const autoStartConsumedRef = useRef(false);
  const stopRetryStartedAtRef = useRef(0);

  const syncStartApi = useApi<{ job_id?: string; task_id?: string; status_url?: string }>();
  const syncStatusApi = useApi<JobStatus>();
  const syncCancelApi = useApi();
  const readinessApi = useApi<SubmitReadinessResponse>();
  const checkResultsApi = useApi<CheckResultsResponse>();

  const updateSyncJobId = useCallback((jobId: string) => {
    activeSyncJobIdRef.current = jobId;
    syncPollGenerationRef.current += 1;
    syncPollInFlightRef.current = false;
    setSyncJobId(jobId);
  }, []);

  const resetSyncProgressMonitor = useCallback(() => {
    syncProgressMonitorRef.current = {
      jobId: '',
      signature: '',
      sinceMs: 0,
      warned: false,
      interrupting: false,
    };
  }, []);

  const inspectSyncProgressMonitor = useCallback(
    (result: JobStatus) => {
      const jobId = String(result?.job_id || result?.task_id || syncJobId || '');
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
          level: 'stop' as const,
          message: `扫描指标已 ${formatDuration(stalledMs / 1000)} 未更新，状态不明确，已自动停止本次刷新。请稍后重试或缩小同步范围。`,
        };
      }
      if (stalledMs >= SYNC_PROGRESS_STALL_WARNING_MS && !previous.warned) {
        syncProgressMonitorRef.current = { ...previous, warned: true };
        return {
          level: 'warning' as const,
          message: `扫描指标已 ${formatDuration(stalledMs / 1000)} 未更新；系统会继续监控，若继续不变将自动停止本次刷新。`,
        };
      }
      return null;
    },
    [resetSyncProgressMonitor, syncJobId]
  );

  return {
    mode,
    setMode,
    syncJobId,
    setSyncJobId,
    syncStatus,
    setSyncStatus,
    syncRunning,
    setSyncRunning,
    syncRange,
    setSyncRange,
    contextOnlyMode,
    setContextOnlyMode,
    stoppingSinceMs,
    setStoppingSinceMs,
    stoppingNowMs,
    setStoppingNowMs,
    syncPollInFlightRef,
    activeSyncJobIdRef,
    syncPollGenerationRef,
    syncPollFailureCountRef,
    syncProgressMonitorRef,
    syncRecoveryAttemptedRef,
    autoStartConsumedRef,
    stopRetryStartedAtRef,
    syncStartApi,
    syncStatusApi,
    syncCancelApi,
    readinessApi,
    checkResultsApi,
    updateSyncJobId,
    resetSyncProgressMonitor,
    inspectSyncProgressMonitor,
  };
}

interface UseOfficialOperationsProps {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
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

export function useOfficialOperations({
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
}: UseOfficialOperationsProps) {
  const logHook = useOperationLog();
  const stateHook = useOfficialOperationsState();
  const { logs, setLogs, appendLog } = logHook;

  const {
    mode,
    setMode,
    syncJobId,
    syncStatus,
    syncRunning,
    syncRange,
    setSyncRange,
    contextOnlyMode,
    stoppingSinceMs,
    stoppingNowMs,
    syncPollInFlightRef,
    activeSyncJobIdRef,
    syncPollGenerationRef,
    syncPollFailureCountRef,
    syncRecoveryAttemptedRef,
    autoStartConsumedRef,
    stopRetryStartedAtRef,
    syncStartApi,
    syncStatusApi,
    syncCancelApi,
    readinessApi,
    checkResultsApi,
    updateSyncJobId,
    resetSyncProgressMonitor,
    inspectSyncProgressMonitor,
    setSyncStatus,
    setSyncRunning,
    setContextOnlyMode,
    setStoppingSinceMs,
    setStoppingNowMs,
  } = stateHook;

  useSyncRecovery({
    setMode,
    setSyncStatus,
    setSyncRunning,
    setContextOnlyMode,
    syncPollFailureCountRef,
    syncRecoveryAttemptedRef,
    syncStatusApi,
    updateSyncJobId,
    resetSyncProgressMonitor,
    appendLog,
    notify,
  });

  const { interruptOfficialContextRefresh, stopOfficialContextRefresh } = useSyncStop({
    syncJobId,
    setSyncStatus,
    setSyncRunning,
    stoppingSinceMs,
    setStoppingSinceMs,
    setStoppingNowMs,
    syncPollFailureCountRef,
    stopRetryStartedAtRef,
    syncCancelApi,
    resetSyncProgressMonitor,
    appendLog,
    notify,
    syncStatus,
  });

  const { startOfficialContextRefresh, startContextOnlyRefresh } = useSyncOperations({
    syncJobId,
    setSyncStatus,
    syncRunning,
    setSyncRunning,
    syncRange,
    setContextOnlyMode,
    stoppingSinceMs,
    setStoppingSinceMs,
    syncPollInFlightRef,
    activeSyncJobIdRef,
    syncPollGenerationRef,
    syncPollFailureCountRef,
    autoStartConsumedRef,
    syncStartApi,
    syncStatusApi,
    updateSyncJobId,
    resetSyncProgressMonitor,
    inspectSyncProgressMonitor,
    appendLog,
    notify,
    credentials,
    connectionReady,
    autoStart,
    onAutoStartConsumed,
    onSyncCompleted,
    setMode,
    interruptOfficialContextRefresh,
  });

  const { loadReadiness, loadChecks } = useReadinessChecks({
    setMode,
    readinessApi,
    checkResultsApi,
    appendLog,
    notify,
  });

  const currentProgress = operationProgress(
    mode,
    syncStatus,
    readinessApi.data,
    checkResultsApi.data
  );
  const currentError = currentModeError(mode, syncStatus, {
    syncStart: syncStartApi.error,
    syncStatus: syncStatusApi.error,
    readiness: readinessApi.error,
    checks: checkResultsApi.error,
  });
  const currentState = progressState(
    mode,
    syncRunning,
    syncStatus,
    readinessApi.loading,
    checkResultsApi.loading,
    currentError
  );
  const readiness = readinessApi.data;
  const checkRows = checkResultsApi.data?.items || checkResultsApi.data?.checks || [];
  const displaySyncStatus = syncStatusForDisplay(syncStatus, officialContextCache);
  const syncOverview = syncDataOverview(displaySyncStatus, syncRunning, cloudAlphaCache);
  const syncHistory = displaySyncStatus?.sync_history || [];
  const syncHistoryError = displaySyncStatus?.sync_history_error || '';
  const syncHistoryErrorTitle = syncHistoryError ? syncHistoryReadErrorTitle(syncHistoryError) : '';
  const canRetryContext = canRetryContextOnly(syncStatus);
  const syncState = classifyJobState(syncStatus);
  const displaySyncState = classifyJobState(displaySyncStatus);
  const syncNeedsRetry = syncState.failed || syncState.interrupted || syncState.missing;
  const refreshPanelTitle = contextOnlyMode ? '仅刷新官方能力集' : '刷新官方能力集';
  const refreshPanelDescription = contextOnlyMode
    ? '仅刷新官方字段、算子与 Dataset 上下文，不拉取云端 Alpha 快照。'
    : '同步云端 Alpha 快照，并刷新官方字段、算子与 Dataset 上下文。';
  const stoppingElapsedSeconds =
    syncStatus?.status === 'stopping' && stoppingSinceMs
      ? Math.max(0, Math.floor(((stoppingNowMs || Date.now()) - stoppingSinceMs) / 1000))
      : 0;

  return {
    mode,
    setMode,
    syncJobId,
    syncStatus,
    syncRunning,
    syncRange,
    setSyncRange,
    contextOnlyMode,
    stoppingSinceMs,
    stoppingNowMs,
    logs,
    setLogs,
    syncStartApi,
    syncStatusApi,
    syncCancelApi,
    readinessApi,
    checkResultsApi,
    currentProgress,
    currentError,
    currentState,
    readiness,
    checkRows,
    displaySyncStatus,
    syncOverview,
    syncHistory,
    syncHistoryError,
    syncHistoryErrorTitle,
    canRetryContext,
    syncState,
    displaySyncState,
    syncNeedsRetry,
    refreshPanelTitle,
    refreshPanelDescription,
    stoppingElapsedSeconds,
    officialContextCache,
    cloudAlphaCache,
    onReconnectRequested,
    onNavigateToCandidates,
    loadReadiness,
    loadChecks,
    startOfficialContextRefresh,
    startContextOnlyRefresh,
    stopOfficialContextRefresh,
    appendLog,
  };
}
