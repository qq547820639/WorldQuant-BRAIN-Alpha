import { useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import type { ApiMeta } from '@/hooks/useApi';
import type { JobStatus } from '@/types';
import { isRecord } from '@/types';
import type { OperationMode } from './constants';
import type { OperationLogEntry } from './utils';
import {
  shortOperationId,
  saveStoredSyncJobId,
  loadStoredSyncJobId,
  clearStoredSyncJobId,
  isTerminalSyncStatus,
  operationFailureMessage,
  isSessionInvalidResult,
} from './utils';

interface UseSyncRecoveryDeps {
  setMode: Dispatch<SetStateAction<OperationMode>>;
  setSyncStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setSyncRunning: Dispatch<SetStateAction<boolean>>;
  setContextOnlyMode: Dispatch<SetStateAction<boolean>>;
  syncPollFailureCountRef: React.MutableRefObject<number>;
  syncRecoveryAttemptedRef: React.MutableRefObject<boolean>;
  syncStatusApi: { call: <R = JobStatus>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>; data: JobStatus | null; error: string | null; loading: boolean };
  updateSyncJobId: (jobId: string) => void;
  resetSyncProgressMonitor: () => void;
  appendLog: (tone: OperationLogEntry['tone'], message: string) => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
}

export function useSyncRecovery(deps: UseSyncRecoveryDeps) {
  const {
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
  } = deps;

  const callSyncStatus = syncStatusApi.call;

  const applySyncRecoveryFailure = useCallback(
    (jobId: string, result: JobStatus | null) => {
      const message = operationFailureMessage(
        result,
        '本地会话已失效，无法读取正在运行的官方同步状态。请前往运行总览重新测试连接后恢复监控。'
      );
      setMode('context_refresh');
      setContextOnlyMode(false);
      updateSyncJobId(jobId);
      setSyncRunning(false);
      setSyncStatus({
        job_id: jobId,
        task_id: jobId || undefined,
        status: 'missing',
        phase: 'session_invalid',
        error: message,
        progress: {
          job_id: jobId || undefined,
          task_id: jobId || undefined,
          phase: 'session_invalid',
          status_code: 'SESSION_INVALID',
          phase_label: '需要重新连接',
          status_message: message,
        },
      });
      appendLog('warning', message);
      notify('warning', message);
      return true;
    },
    [appendLog, notify, setContextOnlyMode, setMode, setSyncRunning, setSyncStatus, updateSyncJobId]
  );

  const applyRecoveredSyncStatus = useCallback(
    (result: JobStatus) => {
      const jobId = String(result?.job_id || result?.task_id || '');
      if (!jobId) return false;
      const terminal = isTerminalSyncStatus(result);
      setMode('context_refresh');
      setContextOnlyMode(
        Boolean(
          result?.progress?.context_only ||
          (isRecord(result?.result) ? result.result.context_only : undefined)
        )
      );
      updateSyncJobId(jobId);
      setSyncStatus(result);
      setSyncRunning(!terminal);
      syncPollFailureCountRef.current = 0;
      if (terminal) {
        resetSyncProgressMonitor();
        clearStoredSyncJobId();
        appendLog('info', `已恢复最近官方刷新结果: ${shortOperationId(jobId)}`);
      } else {
        saveStoredSyncJobId(jobId);
        appendLog('info', `已恢复正在运行的官方刷新: ${shortOperationId(jobId)}`);
        notify('info', '已恢复正在运行的官方上下文刷新');
      }
      return true;
    },
    [appendLog, notify, resetSyncProgressMonitor, setContextOnlyMode, setMode, setSyncRunning, setSyncStatus, syncPollFailureCountRef, updateSyncJobId]
  );

  useEffect(() => {
    if (syncRecoveryAttemptedRef.current) return;
    syncRecoveryAttemptedRef.current = true;
    let active = true;
    void (async () => {
      const storedJobId = loadStoredSyncJobId();
      let storedTerminalStatus: JobStatus | null = null;
      if (storedJobId) {
        const stored = await callSyncStatus<JobStatus>(
          `/api/sync_status?job_id=${encodeURIComponent(storedJobId)}&compact=1`
        );
        if (!active) return;
        if (isSessionInvalidResult(stored)) {
          applySyncRecoveryFailure(storedJobId, stored);
          return;
        }
        if (stored?.ok && !isTerminalSyncStatus(stored) && applyRecoveredSyncStatus(stored)) return;
        clearStoredSyncJobId();
        if (stored?.ok && isTerminalSyncStatus(stored)) storedTerminalStatus = stored;
      }
      const current = await callSyncStatus<JobStatus>('/api/sync_status?compact=1');
      if (!active) return;
      if (isSessionInvalidResult(current)) {
        applySyncRecoveryFailure('', current);
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
  }, [applyRecoveredSyncStatus, applySyncRecoveryFailure, callSyncStatus, setSyncStatus, syncRecoveryAttemptedRef]);

  return {
    applySyncRecoveryFailure,
    applyRecoveredSyncStatus,
  };
}
