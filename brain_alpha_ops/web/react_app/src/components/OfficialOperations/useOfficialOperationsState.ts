import { useCallback, useRef, useState } from 'react';
import { useApi } from '@/hooks/useApi';
import type {
  JobStatus,
  SubmitReadinessResponse,
} from '@/types';
import type {
  OperationMode,
  SyncRange,
  SyncProgressMonitorState,
} from './utils';
import {
  SYNC_PROGRESS_STALL_WARNING_MS,
  SYNC_PROGRESS_STALL_STOP_MS,
  formatDuration,
  syncProgressMonitorSignature,
} from './utils';

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
