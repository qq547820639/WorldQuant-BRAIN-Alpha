/**
 * useJobSseConnection — SSE event processing and connection management.
 *
 * Constructs the SSE URL, processes incoming events (progress, terminal,
 * candidate, submission), and exposes connection state.
 *
 * @deprecated Phase 3.1: useJobSseConnection is deprecated. Its SSE event
 * handling and retry logic have been merged into useJobMonitor/useSseEventHandler.
 * This module is retained for the legacy useJobState → useJobStatus path; new
 * code should use the composable useJobMonitor aggregator instead.
 */

import { useCallback } from 'react';
import { useSSE } from '@/hooks/useSSE';
import { resolveJobEventState } from '@/helpers/runPayload';
import type { SSEEvent, SSECandidateEventData } from '@/types';
import { isSSECandidateData } from '@/types';
import { clearSavedJobId } from '@/hooks/useJobRecovery';

let warned = false;
function emitDeprecationWarning(): void {
  if (warned) return;
  warned = true;
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(
      'useJobSseConnection is deprecated; use useJobMonitor/useSseEventHandler for SSE.'
    );
  }
}

interface SseConnectionCallbacks {
  notify: (
    type: 'success' | 'error' | 'warning' | 'info',
    msg: string,
    action?: { label: string; onClick: () => void }
  ) => void;
  onTerminal: (event: SSEEvent, outcome: ReturnType<typeof resolveJobEventState>) => void;
  onProgress: (event: SSEEvent) => void;
  onCandidate: (alphaId: string) => void;
  onSubmission: (alphaId: string) => void;
  onExhausted: () => void;
  setPollFailures: (n: number | ((prev: number) => number)) => void;
  clearTransientProgressError: () => void;
}

export interface SseConnectionState {
  connected: boolean;
  reconnectAttempts: number;
  sseUrl: string | null;
}

export function useJobSseConnection(
  jobId: string | null,
  {
    notify,
    onTerminal,
    onProgress,
    onCandidate,
    onSubmission,
    onExhausted,
    setPollFailures,
    clearTransientProgressError,
  }: SseConnectionCallbacks
): SseConnectionState {
  emitDeprecationWarning();
  const sseUrl = jobId ? `/sse?job_id=${encodeURIComponent(jobId)}` : null;

  const handleSSEEvent = useCallback(
    (event: SSEEvent) => {
      const eventOutcome = resolveJobEventState(event, event.progress || event.data, {
        failed: '验证流程错误',
        interrupted: '验证流程已停止，结果未确认完成。',
        success: '验证流程已完成',
      });

      if (eventOutcome.terminal) {
        clearSavedJobId();
        onTerminal(event, eventOutcome);
      } else if (event.type === 'progress') {
        setPollFailures(0);
        clearTransientProgressError();
        onProgress(event);
      } else if (event.type === 'candidate') {
        const d = isSSECandidateData(event.data) ? event.data : ({} as SSECandidateEventData);
        onCandidate(String(d.alpha_id || '?'));
      } else if (event.type === 'submission') {
        const d = isSSECandidateData(event.data) ? event.data : ({} as SSECandidateEventData);
        onSubmission(String(d.alpha_id || '未知'));
      }
    },
    [
      notify,
      onTerminal,
      onProgress,
      onCandidate,
      onSubmission,
      setPollFailures,
      clearTransientProgressError,
    ]
  );

  const handleStreamExhausted = useCallback(() => {
    onExhausted();
  }, [onExhausted]);

  const { connected, reconnectAttempts } = useSSE(sseUrl, {
    onEvent: handleSSEEvent,
    onExhausted: handleStreamExhausted,
  });

  return { connected, reconnectAttempts, sseUrl };
}
