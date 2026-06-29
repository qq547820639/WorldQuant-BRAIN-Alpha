/**
 * @deprecated Phase 3.1: useJobCancellation has been merged into useJobControl.
 * This module re-exports the merged hook's cancellation surface for backward
 * compatibility. Import useJobControl from './useJobControl' instead.
 *
 * The standalone useJobCancellation hook shape is preserved so existing callers
 * can keep wiring cancelAmbiguousJob / clearAutoCancelRequests while the
 * migration completes. A console.warn DeprecationWarning is emitted on first use.
 */

import { useRef, useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { requestJobCancel, cancelResultEventMessage, type CancelReason } from '@/api/jobCancel';

let warned = false;
function emitDeprecationWarning(): void {
  if (warned) return;
  warned = true;
  if (typeof console !== 'undefined' && typeof console.warn === 'function') {
    console.warn(
      'useJobCancellation is deprecated and merged into useJobControl. ' +
        'Import useJobControl from "@/hooks/useJobMonitor/useJobControl" instead.'
    );
  }
}

export interface UseJobCancellationOptions {
  jobId: string | null;
  statusJobId: string | undefined;
  setEvents: Dispatch<SetStateAction<string[]>>;
}

export interface JobCancellation {
  cancelAmbiguousJob: (
    reason: CancelReason,
    message: string,
    targetJobId?: string | null
  ) => Promise<unknown>;
  clearAutoCancelRequests: () => void;
}

export function useJobCancellation({
  jobId,
  statusJobId,
  setEvents,
}: UseJobCancellationOptions): JobCancellation {
  emitDeprecationWarning();
  const autoCancelRequests = useRef<Set<string>>(new Set());

  const cancelAmbiguousJob = useCallback(
    async (reason: CancelReason, message: string, targetJobId?: string | null) => {
      const id = targetJobId || jobId || statusJobId;
      if (!id) return null;
      const key = `${id}:${reason}`;
      if (autoCancelRequests.current.has(key)) return null;
      autoCancelRequests.current.add(key);
      const result = await requestJobCancel({ jobId: id, reason, message });
      setEvents((prev) => [...prev.slice(-50), cancelResultEventMessage(result)]);
      return result;
    },
    [jobId, statusJobId, setEvents]
  );

  const clearAutoCancelRequests = useCallback(() => {
    autoCancelRequests.current.clear();
  }, []);

  return { cancelAmbiguousJob, clearAutoCancelRequests };
}
