/**
 * useJobMonitor — composition root for non-submission pipeline job monitoring.
 *
 * Aggregates SSE event handling, job control (start/stop/cancel), and the
 * status watchdog into a single hook. Constants and shared types live here;
 * sub-hooks live in `./useJobControl` and `./useSseEventHandler`.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import type { BrainCredentials, JobStatus, UnifiedProgress } from '@/types';
import { useSSE } from '@/hooks/useSSE';
import { useApi } from '@/hooks/useApi';
import type { CancelReason } from '@/api/jobCancel';
import { useSseEventHandler } from './useSseEventHandler';
import { useJobControl } from './useJobControl';
import { useStatusWatchdog } from './useSseEventHandler';

// ──────────────────────────────────────────────────────────────────────────
// constants
// ──────────────────────────────────────────────────────────────────────────

export const TRANSIENT_STATUS_REFRESH_PREFIX = '状态刷新失败:';
export const SSE_RETRY_DELAYS = [5000, 10000, 20000];
export const SSE_MAX_RETRIES = SSE_RETRY_DELAYS.length;

// ──────────────────────────────────────────────────────────────────────────
// types
// ──────────────────────────────────────────────────────────────────────────

export type NotifyFn = (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;

export interface UseJobMonitorOptions {
  notify: NotifyFn;
  credentials?: BrainCredentials;
}

export interface UseJobMonitorResult {
  jobId: string | null;
  status: JobStatus | null;
  running: boolean;
  connected: boolean;
  progress: UnifiedProgress | null;
  error: string | null;
  events: string[];
  loading: boolean;
  reconnectAttempts: number;
  sseRetryExhausted: boolean;
  sseRetryCountdown: number;
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
  onSseExhaustedRetry: () => void;
}

// ──────────────────────────────────────────────────────────────────────────
// useJobMonitor — composition root
// ──────────────────────────────────────────────────────────────────────────

export function useJobMonitor({ notify, credentials }: UseJobMonitorOptions): UseJobMonitorResult {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);
  const [, setPollFailures] = useState(0);

  const api = useApi();
  // Refs to break the circular dependency between useSseEventHandler (needs
  // onExhausted → cancelAmbiguousJob / onResume → startJob) and useJobControl
  // (needs resetSseRetryState). Each hook is called unconditionally; the refs
  // are populated right after the hook that owns the value returns.
  const startJobRef = useRef<((resume?: boolean) => Promise<void>) | null>(null);
  const cancelAmbiguousJobRef = useRef<
    | ((reason: CancelReason, message: string, targetJobId?: string | null) => Promise<unknown>)
    | null
  >(null);
  const resetSseRetryStateRef = useRef<(() => void) | null>(null);

  const clearTransientProgressError = useCallback(() => {
    setProgressError((current) =>
      current?.startsWith(TRANSIENT_STATUS_REFRESH_PREFIX) ? null : current
    );
  }, []);

  const failMonitor = useCallback((message: string, phase = 'watchdog_failed') => {
    setRunning(false);
    setProgressError(message);
    setStatus((prev) =>
      prev
        ? {
            ...prev,
            status: 'failed',
            phase,
            error: message,
            progress: {
              ...(prev.progress || {}),
              phase,
              status_message: message,
              percent_complete: 100,
            },
          }
        : prev
    );
    setEvents((prev) => [...prev.slice(-50), message]);
  }, []);

  const onResume = useCallback(() => {
    void startJobRef.current?.(true);
  }, []);

  const onExhausted = useCallback(
    (message: string) => {
      failMonitor(message);
      void cancelAmbiguousJobRef.current?.('sse_exhausted', message);
    },
    [failMonitor]
  );

  const {
    handleSSEEvent,
    sseRetryCountdown,
    sseRetryExhausted,
    clearSseRetryTimers,
    resetSseRetryState,
    handleStreamExhausted,
    handleSseExhaustedManualRetry,
  } = useSseEventHandler({
    notify,
    onResume,
    onExhausted,
    setStatus,
    setRunning,
    setJobId,
    setProgressError,
    setEvents,
    setPollFailures,
    clearTransientProgressError,
  });

  resetSseRetryStateRef.current = resetSseRetryState;
  const resetSseRetryStateWrapper = useCallback(() => {
    resetSseRetryStateRef.current?.();
  }, []);

  const { startJob, stopJob, cancelAmbiguousJob, clearAutoCancelRequests } = useJobControl({
    notify,
    credentials,
    api,
    jobId,
    statusJobId: status?.job_id,
    setStatus,
    setRunning,
    setJobId,
    setProgressError,
    setEvents,
    setPollFailures,
    resetSseRetryState: resetSseRetryStateWrapper,
  });

  startJobRef.current = startJob;
  cancelAmbiguousJobRef.current = cancelAmbiguousJob;
  // clearAutoCancelRequests is wired into useJobControl's startJob; reference
  // kept to avoid unused-var lint and to preserve the public surface shape.
  void clearAutoCancelRequests;

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const { connected, reconnectAttempts } = useSSE(sseUrl, {
    onEvent: handleSSEEvent,
    onExhausted: handleStreamExhausted,
  });

  useStatusWatchdog({
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
  });

  useEffect(() => {
    return () => {
      clearSseRetryTimers();
    };
  }, [clearSseRetryTimers]);

  const cycleProgress =
    status?.cycle && status?.max_cycles ? Math.round((status.cycle / status.max_cycles) * 100) : 0;
  const progress = status?.progress || {
    phase: status?.phase,
    percent_complete: status?.percent_complete ?? cycleProgress,
    eta_seconds: status?.eta_seconds,
    status_message: status?.status_message,
  };

  return {
    jobId,
    status,
    running,
    connected,
    progress,
    error: progressError,
    events,
    loading: api.loading,
    reconnectAttempts,
    sseRetryExhausted,
    sseRetryCountdown,
    startJob,
    stopJob,
    onSseExhaustedRetry: handleSseExhaustedManualRetry,
  };
}
