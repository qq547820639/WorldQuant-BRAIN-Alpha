/**
 * useJobWatchdog — Polling watchdog that detects stalled jobs.
 *
 * Only polls the backend when SSE is disconnected, avoiding redundant
 * network traffic while the event stream is healthy. Tracks consecutive
 * failures and triggers the disconnected state when the threshold is exceeded.
 */

import { useEffect, useCallback } from 'react';
import type { JobStatus } from '@/types';
import type { CancelReason } from '@/api/jobCancel';
import { classifyJobState, jobStatusMessage } from '@/helpers/runPayload';
import { saveResumeState } from '@/utils/resumeState';
import { clearSavedJobId } from '@/hooks/useJobRecovery';

const WATCHDOG_POLL_INTERVAL = 2000;

function sendCompletionNotification(title: string, body: string): void {
  try {
    if (document.hidden && Notification.permission === 'granted') {
      new Notification(title, { body });
    }
  } catch {
    console.warn('useJobState: Notification API not available');
  }
}

interface WatchdogCallbacks {
  pollFailures: number;
  setPollFailures: React.Dispatch<React.SetStateAction<number>>;
  callApi: <T>(url: string) => Promise<T | null>;
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  cancelAmbiguousJob: (
    reason: CancelReason,
    message: string,
    jobId?: string | null
  ) => Promise<unknown>;
  onTerminal: (status: JobStatus) => void;
  onProgressUpdate: (status: JobStatus) => void;
  clearTransientProgressError: () => void;
}

export function useJobWatchdog(
  running: boolean,
  jobId: string | null,
  sseConnected: boolean,
  {
    setPollFailures,
    callApi,
    notify,
    cancelAmbiguousJob,
    onTerminal,
    onProgressUpdate,
    clearTransientProgressError,
  }: WatchdogCallbacks
) {
  const recordStatusRefreshFailure = useCallback(
    (_message: string) => {
      setPollFailures((previous) => {
        const next = previous + 1;
        return next;
      });
    },
    [setPollFailures]
  );

  // Polling watchdog: only poll when SSE is disconnected
  useEffect(() => {
    if (!running || !jobId || sseConnected) return;
    const interval = setInterval(async () => {
      const result = await callApi<JobStatus>(
        `/api/production-validation/status?job_id=${encodeURIComponent(jobId)}`
      );
      const resultState = classifyJobState(result);
      if (result?.status && resultState.terminal) {
        clearSavedJobId();
        onTerminal(result);
        if (resultState.failed || resultState.missing || resultState.interrupted) {
          const msg = jobStatusMessage(
            result,
            resultState.interrupted ? '验证流程已停止，结果未确认完成。' : '验证流程失败。'
          );
          if (result.phase === 'watchdog_failed' || result.progress?.phase === 'watchdog_failed') {
            void cancelAmbiguousJob('watchdog_failed', msg, result.job_id || jobId);
          }
          saveResumeState({ lastError: msg, lastConnectionOk: false, lastPipelineJob: null });
          notify(resultState.interrupted ? 'warning' : 'error', msg);
        } else {
          saveResumeState({
            lastError: null,
            lastConnectionOk: true,
            lastPipelineJob: null,
            totalCyclesCompleted: (result.cycle ?? 0) > 0 ? result.cycle : undefined,
          });
          sendCompletionNotification('BRAIN Alpha Ops', '管线运行完成！');
        }
      } else if (result?.ok) {
        clearTransientProgressError();
        onProgressUpdate(result);
        setPollFailures(0);
      } else if (result) {
        recordStatusRefreshFailure(jobStatusMessage(result, '状态刷新失败'));
      } else {
        recordStatusRefreshFailure('状态刷新失败或网络中断');
      }
    }, WATCHDOG_POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [
    running,
    jobId,
    sseConnected,
    callApi,
    cancelAmbiguousJob,
    clearTransientProgressError,
    notify,
    recordStatusRefreshFailure,
    onTerminal,
    onProgressUpdate,
    setPollFailures,
  ]);
}
