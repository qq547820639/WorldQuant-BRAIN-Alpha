import { classifyJobState } from '@/helpers/runPayload';
import type {
  BrainCredentials,
  CloudAlphaCache,
  OfficialContextCache,
  SubmitReadinessResponse,
} from '@/types';
import {
  syncStatusForDisplay,
  syncDataOverview,
  operationProgress,
  progressState,
  currentModeError,
  canRetryContextOnly,
  syncHistoryReadErrorTitle,
} from './utils';
import { useOperationLog } from './useOperationLog';
import { useOfficialOperationsState } from './useOfficialOperationsState';
import { useSyncRecovery } from './useSyncRecovery';
import { useSyncStop } from './useSyncStop';
import { useSyncOperations } from './useSyncOperations';
import { useReadinessChecks } from './useReadinessChecks';

interface CheckResultsResponse {
  items?: Array<Record<string, unknown>>;
  checks?: Array<Record<string, unknown>>;
  count?: number;
  ok?: boolean;
  data?: CheckResultsResponse;
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
    readinessApi.data as SubmitReadinessResponse | undefined,
    checkResultsApi.data as CheckResultsResponse | undefined
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
