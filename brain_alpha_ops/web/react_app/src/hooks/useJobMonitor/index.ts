import { useState, useEffect, useCallback, useRef } from 'react';
import type { JobStatus } from '@/types';
import { useSSE } from '@/hooks/useSSE';
import { useApi } from '@/hooks/useApi';
import { TRANSIENT_STATUS_REFRESH_PREFIX } from './constants';
import type { UseJobMonitorOptions, UseJobMonitorResult } from './types';
import { useJobCancellation } from './useJobCancellation';
import { useSseRetryState } from './useSseRetryState';
import { useSseEventHandler } from './useSseEventHandler';
import { useJobControl } from './useJobControl';
import { useStatusWatchdog } from './useStatusWatchdog';

export function useJobMonitor({ notify, credentials }: UseJobMonitorOptions): UseJobMonitorResult {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<string[]>([]);
  const [progressError, setProgressError] = useState<string | null>(null);
  const [, setPollFailures] = useState(0);

  const api = useApi();
  const startJobRef = useRef<((resume?: boolean) => Promise<void>) | null>(null);

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

  const { cancelAmbiguousJob, clearAutoCancelRequests } = useJobCancellation({
    jobId,
    statusJobId: status?.job_id,
    setEvents,
  });

  const onResume = useCallback(() => {
    void startJobRef.current?.(true);
  }, []);

  const onExhausted = useCallback(
    (message: string) => {
      failMonitor(message);
      void cancelAmbiguousJob('sse_exhausted', message);
    },
    [failMonitor, cancelAmbiguousJob]
  );

  const sseRetry = useSseRetryState({ notify, onResume, onExhausted });

  const handleSSEEvent = useSseEventHandler({
    notify,
    setStatus,
    setRunning,
    setJobId,
    setProgressError,
    setEvents,
    setPollFailures,
    clearTransientProgressError,
  });

  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;
  const { connected, reconnectAttempts } = useSSE(sseUrl, {
    onEvent: handleSSEEvent,
    onExhausted: sseRetry.handleStreamExhausted,
  });

  const { startJob, stopJob } = useJobControl({
    notify,
    credentials,
    api,
    jobId,
    setStatus,
    setRunning,
    setJobId,
    setProgressError,
    setEvents,
    setPollFailures,
    clearAutoCancelRequests,
    resetSseRetryState: sseRetry.resetSseRetryState,
  });

  startJobRef.current = startJob;

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
      sseRetry.clearSseRetryTimers();
    };
  }, [sseRetry.clearSseRetryTimers]);

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
    sseRetryExhausted: sseRetry.sseRetryExhausted,
    sseRetryCountdown: sseRetry.sseRetryCountdown,
    startJob,
    stopJob,
    onSseExhaustedRetry: sseRetry.handleSseExhaustedManualRetry,
  };
}
