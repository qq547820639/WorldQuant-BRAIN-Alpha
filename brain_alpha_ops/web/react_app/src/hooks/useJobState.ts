/**
 * useJobState — App-level job state hook
 *
 * Lifts job monitoring state out of JobMonitor so it persists across page navigation.
 * The TopBar can display a running minibar, and any page can check job progress.
 *
 * Persistence: jobId is saved to sessionStorage so that page refresh or accidental
 * tab close can recover the running job when the page reopens (within the same
 * browser session).
 *
 * P0-2: When SSE stream exhausts or the polling watchdog fires, the hook now
 * sets a "disconnected" state instead of immediately cancelling the BRAIN job.
 * The user is shown a persistent toast with [继续等待] / [终止重试] buttons.
 * If the user takes no action within 5 minutes, auto-cancellation takes effect.
 */

import type { BrainCredentials, JobStatus, UnifiedProgress } from "@/types";
import { useJobStatus } from "./useJobStatusHook";
import { useJobLifecycle } from "./useJobLifecycle";
import { useJobNotifications } from "./useJobNotifications";

export interface JobState {
  jobId: string | null;
  running: boolean;
  status: JobStatus | null;
  progress: UnifiedProgress | null;
  error: string | null;
  connected: boolean;
  events: string[];
  recovering: boolean;
  reconnectAttempts: number;
  disconnected: boolean;
  startJob: (resume?: boolean) => Promise<void>;
  stopJob: () => Promise<void>;
  resumeWatchdog: () => void;
  forceCancelDisconnected: () => void;
}

export function useJobState(
  notify: (
    type: "success" | "error" | "warning" | "info",
    msg: string,
    action?: { label: string; onClick: () => void },
    secondaryAction?: { label: string; onClick: () => void },
  ) => void,
  credentials?: BrainCredentials,
): JobState {
  const status = useJobStatus({ notify, credentials });
  const lifecycle = useJobLifecycle({
    notify,
    credentials,
    jobId: status.jobId,
    setJobId: status.setJobId,
    setRunning: status.setRunning,
    setStatus: status.setStatus,
    setProgressError: status.setProgressError,
    setPollFailures: status.setPollFailures,
    clearDisconnectedTimer: status.clearDisconnectedTimer!,
    setDisconnected: status.setDisconnected!,
    addEventSlice: status.addEventSlice,
    api: status.api,
  });
  useJobNotifications();

  return {
    jobId: status.jobId,
    running: status.running,
    status: status.status,
    progress: status.progress,
    error: status.error,
    connected: status.connected,
    events: status.events,
    recovering: status.recovering,
    reconnectAttempts: status.reconnectAttempts,
    disconnected: status.disconnected,
    startJob: lifecycle.startJob,
    stopJob: lifecycle.stopJob,
    resumeWatchdog: status.resumeWatchdog,
    forceCancelDisconnected: status.forceCancelDisconnected,
  };
}
