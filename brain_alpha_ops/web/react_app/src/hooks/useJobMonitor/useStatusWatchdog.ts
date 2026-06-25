import { useCallback, useEffect } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { classifyJobState, jobStatusMessage } from '@/helpers/runPayload';
import type { JobStatus } from '@/types';
import { useApi } from '@/hooks/useApi';
import type { CancelReason } from '@/api/jobCancel';
import type { NotifyFn } from './types';

type ApiInstance = ReturnType<typeof useApi>;

export interface UseStatusWatchdogOptions {
  running: boolean;
  jobId: string | null;
  api: ApiInstance;
  notify: NotifyFn;
  setStatus: Dispatch<SetStateAction<JobStatus | null>>;
  setRunning: Dispatch<SetStateAction<boolean>>;
  setJobId: Dispatch<SetStateAction<string | null>>;
  setProgressError: Dispatch<SetStateAction<string | null>>;
  setEvents: Dispatch<SetStateAction<string[]>>;
  setPollFailures: Dispatch<SetStateAction<number>>;
  clearTransientProgressError: () => void;
  failMonitor: (message: string, phase?: string) => void;
  cancelAmbiguousJob: (
    reason: CancelReason,
    message: string,
    targetJobId?: string | null
  ) => Promise<unknown>;
}

export function useStatusWatchdog({
  running,
  jobId,
  api,
  notify,
  setStatus,
  setRunning,
  setJobId,
  setProgressError,
  setEvents,
  setPollFailures,
  clearTransientProgressError,
  failMonitor,
  cancelAmbiguousJob,
}: UseStatusWatchdogOptions) {
  const recordStatusRefreshFailure = useCallback(
    (message: string) => {
      setPollFailures((previous) => {
        const next = previous + 1;
        if (next >= 12) {
          const failure = `状态连续刷新失败，本次验证状态不明确，正在请求自动中断: ${message}`;
          failMonitor(failure);
          void cancelAmbiguousJob('status_failed', failure);
          notify('error', failure);
        } else {
          setProgressError(`状态刷新失败: ${message}`);
          setEvents((prev) => [...prev.slice(-50), `状态刷新失败: ${message}`]);
        }
        return next;
      });
    },
    [cancelAmbiguousJob, failMonitor, notify]
  );

  useEffect(() => {
    if (!running || !jobId) return;
    const interval = setInterval(async () => {
      const result = await api.call<JobStatus>(
        `/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`
      );
      const resultState = classifyJobState(result);
      if (result?.status && resultState.terminal) {
        setStatus(result);
        setPollFailures(0);
        setRunning(false);
        if (resultState.failed || resultState.missing || resultState.interrupted) {
          const msg = jobStatusMessage(
            result,
            resultState.interrupted ? '验证流程已停止，结果未确认完成。' : '验证流程失败。'
          );
          setProgressError(msg);
          setEvents((prev) => [...prev.slice(-50), `验证流程失败: ${msg}`]);
          if (result.phase === 'watchdog_failed' || result.progress?.phase === 'watchdog_failed')
            void cancelAmbiguousJob('watchdog_failed', msg, result.job_id || jobId);
          notify(resultState.interrupted ? 'warning' : 'error', msg);
        } else {
          setProgressError(null);
        }
        setJobId(null);
      } else if (result?.ok) {
        clearTransientProgressError();
        setStatus(result);
        setPollFailures(0);
      } else if (result) {
        recordStatusRefreshFailure(jobStatusMessage(result, '状态刷新失败'));
      } else {
        recordStatusRefreshFailure('状态刷新失败或网络中断');
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [
    running,
    jobId,
    api,
    cancelAmbiguousJob,
    clearTransientProgressError,
    failMonitor,
    notify,
    recordStatusRefreshFailure,
  ]);
}
