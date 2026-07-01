/**
 * @deprecated Use useJobControl from './useJobControl' instead.
 */

import { useRef, useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { requestJobCancel, cancelResultEventMessage, type CancelReason } from '@/api/jobCancel';

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
