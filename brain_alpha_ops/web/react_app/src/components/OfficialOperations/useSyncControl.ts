/** OfficialOperations sync control hooks: recovery and stop. */

import { useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import type { ApiMeta } from '@/hooks/useApi';
import type { JobStatus } from '@/types';
import { isRecord } from '@/types';
import type { OperationLogEntry, OperationMode } from './utils';
import {
  STOP_RETRY_AFTER_MS,
  clearStoredSyncJobId,
  isSessionInvalidResult,
  isTerminalSyncStatus,
  loadStoredSyncJobId,
  operationFailureMessage,
  saveStoredSyncJobId,
  shortOperationId,
} from './utils';

interface UseSyncRecoveryDeps {
  setMode: Dispatch<SetStateAction<OperationMode>>;
  setSyncStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setSyncRunning: Dispatch<SetStateAction<boolean>>;
  setContextOnlyMode: Dispatch<SetStateAction<boolean>>;
  syncPollFailureCountRef: React.MutableRefObject<number>;
  syncRecoveryAttemptedRef: React.MutableRefObject<boolean>;
  syncStatusApi: {
    call: <R = JobStatus>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>;
    data: JobStatus | null;
    error: string | null;
    loading: boolean;
  };
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
    [
      appendLog,
      notify,
      resetSyncProgressMonitor,
      setContextOnlyMode,
      setMode,
      setSyncRunning,
      setSyncStatus,
      syncPollFailureCountRef,
      updateSyncJobId,
    ]
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
  }, [
    applyRecoveredSyncStatus,
    applySyncRecoveryFailure,
    callSyncStatus,
    setSyncStatus,
    syncRecoveryAttemptedRef,
  ]);

  return {
    applySyncRecoveryFailure,
    applyRecoveredSyncStatus,
  };
}

interface UseSyncStopDeps {
  syncJobId: string;
  setSyncStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setSyncRunning: Dispatch<SetStateAction<boolean>>;
  stoppingSinceMs: number;
  setStoppingSinceMs: Dispatch<SetStateAction<number>>;
  setStoppingNowMs: Dispatch<SetStateAction<number>>;
  syncPollFailureCountRef: React.MutableRefObject<number>;
  stopRetryStartedAtRef: React.MutableRefObject<number>;
  syncCancelApi: {
    call: <R = unknown>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>;
    reset: () => void;
    data: unknown;
    error: string | null;
    loading: boolean;
  };
  resetSyncProgressMonitor: () => void;
  appendLog: (tone: OperationLogEntry['tone'], message: string) => void;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  syncStatus: JobStatus | null;
}

export function useSyncStop(deps: UseSyncStopDeps) {
  const {
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
  } = deps;

  const callSyncCancel = syncCancelApi.call;

  const interruptOfficialContextRefresh = useCallback(
    async (message: string) => {
      if (!syncJobId) return;
      setSyncRunning(false);
      setSyncStatus((previous) => ({
        ...(previous || { job_id: syncJobId, task_id: syncJobId, status: 'stopped' }),
        job_id: previous?.job_id || syncJobId,
        task_id: previous?.task_id || syncJobId,
        status: 'stopped',
        phase: 'stopped',
        error: message,
        progress: {
          ...(previous?.progress || {}),
          job_id: previous?.progress?.job_id || syncJobId,
          task_id: previous?.progress?.task_id || syncJobId,
          phase: 'stopped',
          phase_label: '已自动停止',
          status_message: message,
          percent_complete: 100,
        },
      }));
      const result = await callSyncCancel<{ stopping_since_ms?: number | string }>(
        '/api/sync_cancel',
        {
          method: 'POST',
          body: JSON.stringify({ job_id: syncJobId }),
        }
      );
      if (!result?.ok) {
        const cancelMessage = operationFailureMessage(
          result,
          '停止请求暂未确认。请稍后重新读取状态。'
        );
        appendLog('error', cancelMessage);
        notify('error', cancelMessage);
        return;
      }
      clearStoredSyncJobId();
      resetSyncProgressMonitor();
      appendLog('warning', message);
      notify('warning', message);
    },
    [
      appendLog,
      callSyncCancel,
      notify,
      resetSyncProgressMonitor,
      setSyncRunning,
      setSyncStatus,
      syncJobId,
    ]
  );

  const stopOfficialContextRefresh = useCallback(async () => {
    if (!syncJobId) return;
    const requestedAt = Date.now();
    setStoppingSinceMs(requestedAt);
    setStoppingNowMs(requestedAt);
    setSyncStatus((previous) => ({
      ...(previous || { job_id: syncJobId, task_id: syncJobId, status: 'stopping' }),
      job_id: previous?.job_id || syncJobId,
      task_id: previous?.task_id || syncJobId,
      status: 'stopping',
      phase: 'stopping',
      progress: {
        ...(previous?.progress || {}),
        job_id: previous?.progress?.job_id || syncJobId,
        task_id: previous?.progress?.task_id || syncJobId,
        phase: 'stopping',
        status_code: 'STOPPING',
        phase_label: '停止中',
        status_message: '停止请求已发送，等待当前官方接口返回后结束。',
        stopping_since_ms: requestedAt,
      },
    }));
    const result = await callSyncCancel<{ stopping_since_ms?: number | string }>(
      '/api/sync_cancel',
      {
        method: 'POST',
        body: JSON.stringify({ job_id: syncJobId }),
      }
    );
    if (!result?.ok) {
      const message = operationFailureMessage(result, '停止请求失败。请稍后重试。');
      appendLog('error', message);
      notify('error', message);
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
      ...(previous || { job_id: syncJobId, task_id: syncJobId, status: 'stopping' }),
      job_id: previous?.job_id || syncJobId,
      task_id: previous?.task_id || syncJobId,
      status: 'stopping',
      phase: 'stopping',
      progress: {
        ...(previous?.progress || {}),
        job_id: previous?.progress?.job_id || syncJobId,
        task_id: previous?.progress?.task_id || syncJobId,
        phase: 'stopping',
        phase_label: '停止中',
        status_message: '停止请求已发送，等待当前官方接口返回后结束。',
        stopping_since_ms:
          Number.isFinite(serverStoppingSince) && serverStoppingSince > 0
            ? serverStoppingSince
            : requestedAt,
      },
    }));
    appendLog('warning', '已发送停止请求，系统会在当前官方接口返回后结束。');
    notify('info', '停止请求已发送');
  }, [
    appendLog,
    callSyncCancel,
    notify,
    resetSyncProgressMonitor,
    setStoppingSinceMs,
    setStoppingNowMs,
    setSyncStatus,
    syncJobId,
    syncPollFailureCountRef,
  ]);

  useEffect(() => {
    if (syncStatus?.status !== 'stopping') return;
    const timer = window.setInterval(() => setStoppingNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [syncStatus?.status, setStoppingNowMs]);

  useEffect(() => {
    if (syncStatus?.status !== 'stopping' || !syncJobId || !stoppingSinceMs) return;
    const waitMs = Math.max(0, STOP_RETRY_AFTER_MS - (Date.now() - stoppingSinceMs));
    const timer = window.setTimeout(() => {
      if (stopRetryStartedAtRef.current >= stoppingSinceMs) return;
      stopRetryStartedAtRef.current = stoppingSinceMs;
      appendLog('warning', '停止等待超过 60 秒，正在重新发送停止请求。');
      void callSyncCancel('/api/sync_cancel', {
        method: 'POST',
        body: JSON.stringify({ job_id: syncJobId }),
      });
    }, waitMs);
    return () => window.clearTimeout(timer);
  }, [
    appendLog,
    callSyncCancel,
    stoppingSinceMs,
    stopRetryStartedAtRef,
    syncJobId,
    syncStatus?.status,
  ]);

  return {
    interruptOfficialContextRefresh,
    stopOfficialContextRefresh,
  };
}
