import { useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import type { ApiMeta } from '@/hooks/useApi';
import type { JobStatus } from '@/types';
import type { OperationLogEntry } from './utils';
import {
  STOP_RETRY_AFTER_MS,
  clearStoredSyncJobId,
  operationFailureMessage,
} from './utils';

interface UseSyncStopDeps {
  syncJobId: string;
  setSyncStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setSyncRunning: Dispatch<SetStateAction<boolean>>;
  stoppingSinceMs: number;
  setStoppingSinceMs: Dispatch<SetStateAction<number>>;
  setStoppingNowMs: Dispatch<SetStateAction<number>>;
  syncPollFailureCountRef: React.MutableRefObject<number>;
  stopRetryStartedAtRef: React.MutableRefObject<number>;
  syncCancelApi: { call: <R = unknown>(url: string, options?: RequestInit) => Promise<(R & ApiMeta) | null>; reset: () => void; data: unknown | null; error: string | null; loading: boolean };
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
    [appendLog, callSyncCancel, notify, resetSyncProgressMonitor, setSyncRunning, setSyncStatus, syncJobId]
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
  }, [appendLog, callSyncCancel, notify, resetSyncProgressMonitor, setStoppingSinceMs, setStoppingNowMs, setSyncStatus, syncJobId, syncPollFailureCountRef]);

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
  }, [appendLog, callSyncCancel, stoppingSinceMs, stopRetryStartedAtRef, syncJobId, syncStatus?.status]);

  return {
    interruptOfficialContextRefresh,
    stopOfficialContextRefresh,
  };
}
